# file: macula/server.py

"""HTTP handler and threaded TCP server for macula."""
import fnmatch
import http.server
import io
import json
import os
import re
import shutil
import socketserver
import tarfile
import tempfile
import time
import zipfile
from pathlib import Path
from urllib.parse import urlparse, parse_qs, unquote, quote as url_quote

from . import __version__, HANDBOOK_FILE, VALID_FORMATS
from .renderers import (render_clipboard_html, render_handbook_html,
                        render_html, render_json, render_text)
from .tree import (build_listing_tree,
                   build_listing_tree_and_fp,
                   build_virtual_root_tree,
                   build_virtual_root_tree_and_fp,
                   file_fingerprint)
from .utils import count_upload_files, human_size, safe_filename


_STREAM_CHUNK       = 64 * 1024
_RENDER_MAX_BYTES   = 5 * 1024 * 1024

# Multipart parts up to this size stay in RAM; larger parts spill to a
# temporary file. Peak upload memory is then bounded by the *smaller* of
# the largest single part and this threshold, instead of the whole body.
_MULTIPART_SPOOL_BYTES = 8 * 1024 * 1024

# translate_path() returns this sentinel when no mount matches. A NUL
# byte is guaranteed to make Path.resolve() raise on every supported
# platform, so _safe_resolve() rejects the path and the request 404s.
_MISSING_MOUNT_SENTINEL = "\x00macula-no-mount\x00"


# ---------------------------------------------------------------------------
# Upload path helpers
# ---------------------------------------------------------------------------
def _sanitize_upload_path(raw_name):
    """Sanitize a caller-supplied filename into a relative POSIX path.

    Rejects:
      - empty / null input
      - absolute POSIX paths (leading '/')
      - absolute Windows paths (leading '\\\\' or 'X:')
      - segments that are exactly '.' or '..'

    Returns None on any rejection.
    """
    if not raw_name:
        return None
    s = str(raw_name)
    if s.startswith("/") or s.startswith("\\"):
        return None
    if len(s) >= 2 and s[1] == ":" and s[0].isalpha():
        return None
    s = s.replace("\\", "/")
    raw_parts = [p for p in s.split("/") if p]
    if not raw_parts:
        return None
    safe_parts = []
    for p in raw_parts:
        if p in (".", ".."):
            return None
        sp = safe_filename(p)
        if not sp:
            return None
        safe_parts.append(sp)
    return "/".join(safe_parts)


# ---------------------------------------------------------------------------
# Streaming multipart parser
#
# The stdlib `email` package buffers the entire message before parsing,
# which for a multi-gigabyte upload means multi-gigabyte RAM usage. The
# parser below reads the body in chunks and streams each part's payload
# to a SpooledTemporaryFile, so peak memory is bounded by the spool
# threshold regardless of total request size.
#
# The grammar implemented is the RFC 2046 subset used by browsers:
#   body        := "--" boundary CRLF part *(CRLF "--" boundary CRLF part)
#                  CRLF "--" boundary "--" [CRLF]
#   part        := *(header CRLF) CRLF payload
#   payload     := *OCTET  (until the boundary marker)
# ---------------------------------------------------------------------------
class _MultipartError(Exception):
    """Raised when a multipart body is malformed."""


def _extract_boundary(content_type):
    """Extract the boundary parameter from a Content-Type header."""
    m = re.search(r'boundary\s*=\s*(?:"([^"]+)"|([^;\s]+))',
                  content_type, re.IGNORECASE)
    if not m:
        return None
    raw = m.group(1) if m.group(1) is not None else m.group(2)
    return raw.encode("ascii", "replace")


class _BodyReader:
    """Buffered reader over a request body of known length.

    The body is streamed from `source` (typically `self.rfile`); nothing
    is accumulated beyond what's needed to satisfy the current call.
    """

    def __init__(self, source, length):
        self._source = source
        self._remaining = length
        self._buffer = bytearray()
        self._eof = False

    def _fill_to(self, target):
        while len(self._buffer) < target and not self._eof:
            want = min(_STREAM_CHUNK, self._remaining)
            if want <= 0:
                self._eof = True
                return
            chunk = self._source.read(want)
            if not chunk:
                self._eof = True
                return
            self._buffer.extend(chunk)
            self._remaining -= len(chunk)

    def read_line(self, limit=8192):
        """Read one CRLF/LF-terminated line (terminator included)."""
        while True:
            idx = self._buffer.find(b"\n")
            if idx != -1:
                line = bytes(self._buffer[:idx + 1])
                del self._buffer[:idx + 1]
                return line
            if self._eof:
                if not self._buffer:
                    return b""
                line = bytes(self._buffer)
                self._buffer.clear()
                return line
            if len(self._buffer) > limit:
                raise _MultipartError("header line too long")
            self._fill_to(len(self._buffer) + 1)

    def read_exact(self, n):
        """Read exactly n bytes or raise if EOF first."""
        self._fill_to(n)
        if len(self._buffer) < n:
            raise _MultipartError(
                f"unexpected EOF: wanted {n} bytes, got {len(self._buffer)}")
        result = bytes(self._buffer[:n])
        del self._buffer[:n]
        return result

    def stream_until(self, terminator, sink):
        """Copy bytes from the stream to `sink` until `terminator` is
        encountered. The terminator itself is consumed but not written."""
        tlen = len(terminator)
        while True:
            idx = self._buffer.find(terminator)
            if idx != -1:
                sink.write(bytes(self._buffer[:idx]))
                del self._buffer[:idx + tlen]
                return
            if self._eof:
                raise _MultipartError("boundary not found before EOF")
            # Emit everything except the last (tlen - 1) bytes: the
            # terminator may straddle the next chunk boundary.
            if len(self._buffer) > tlen:
                emit = len(self._buffer) - (tlen - 1)
                sink.write(bytes(self._buffer[:emit]))
                del self._buffer[:emit]
            self._fill_to(len(self._buffer) + _STREAM_CHUNK)


def _parse_part_headers(header_bytes):
    """Parse a single part's MIME headers into a lowercase dict."""
    headers = {}
    for line in header_bytes.split(b"\r\n"):
        if not line or b":" not in line:
            continue
        name, _, value = line.partition(b":")
        headers[name.strip().lower().decode("ascii", "replace")] = \
            value.strip().decode("utf-8", "replace")
    return headers


def _parse_content_disposition(value):
    """Extract (name, filename) from a Content-Disposition header value."""
    name = None
    filename = None
    m = re.search(r'\bname\s*=\s*(?:"([^"]*)"|([^;\s]+))',
                  value, re.IGNORECASE)
    if m:
        name = m.group(1) if m.group(1) is not None else m.group(2)
    m = re.search(r'\bfilename\s*=\s*(?:"([^"]*)"|([^;\s]+))',
                  value, re.IGNORECASE)
    if m:
        filename = m.group(1) if m.group(1) is not None else m.group(2)
    return name, filename


def _iter_multipart_parts(source, boundary, length):
    """Yield (filename, body_stream) for each part.

    Non-file parts are yielded with filename=None; the caller decides
    whether to keep them. `body_stream` is a SpooledTemporaryFile
    positioned at offset 0. The caller is responsible for closing it
    before the next iteration begins.

    Raises _MultipartError on malformed input.
    """
    reader = _BodyReader(source, length)
    opening = b"--" + boundary
    terminator = b"\r\n" + opening

    first = reader.read_line()
    if first.rstrip(b"\r\n") != opening:
        raise _MultipartError("missing opening boundary")

    while True:
        # ---- headers ----
        header_bytes = bytearray()
        while True:
            line = reader.read_line()
            if not line:
                raise _MultipartError("unexpected EOF in part headers")
            if line in (b"\r\n", b"\n"):
                break
            header_bytes.extend(line)

        headers = _parse_part_headers(bytes(header_bytes))
        cd = headers.get("content-disposition", "")
        _, filename = _parse_content_disposition(cd)

        # ---- body ----
        body = tempfile.SpooledTemporaryFile(max_size=_MULTIPART_SPOOL_BYTES)
        try:
            reader.stream_until(terminator, body)
            body.seek(0)
            tail = reader.read_exact(2)
        except Exception:
            body.close()
            raise

        try:
            yield filename, body
        finally:
            # The caller is expected to have read the body by the time
            # the generator resumes. Closing here is safe (a double
            # close is a no-op) and guarantees no descriptor leak even
            # if the caller raises.
            body.close()

        if tail == b"--":
            # Closing boundary. Consume any trailing CRLF.
            try:
                reader.read_line()
            except _MultipartError:
                pass
            return
        if tail == b"\r\n":
            continue
        raise _MultipartError(f"unexpected bytes after boundary: {tail!r}")


class MaculaHandler(http.server.SimpleHTTPRequestHandler):
    server_version = f"Macula/{__version__}"

    # -------------------------------------------------- response header hooks
    def send_response(self, *args, **kwargs):
        # Reset the nosniff marker on every new response so the header is
        # injected exactly once per response, including ones built by
        # send_error(), 301 redirects and 204 replies.
        self._nosniff_injected = False
        super().send_response(*args, **kwargs)

    def end_headers(self):
        if not getattr(self, "_nosniff_injected", False):
            self.send_header("X-Content-Type-Options", "nosniff")
            self._nosniff_injected = True
        super().end_headers()

    # ------------------------------------------------------------------ path
    def translate_path(self, path):
        url_path = unquote(path.split('?', 1)[0].split('#', 1)[0])
        for m in self.server.mounts:
            prefix = m["prefix"]; root = m["root"]
            if prefix == '/':
                rel = url_path.lstrip('/')
                return str(root / rel) if rel else str(root)
            stripped = prefix.rstrip('/')
            if url_path == stripped or url_path == prefix:
                return str(root)
            if url_path.startswith(prefix):
                rel = url_path[len(prefix):]
                return str(root / rel) if rel else str(root)
        # No mount matched. Return a path that is guaranteed to be
        # rejected: the embedded NUL byte makes Path.resolve() raise,
        # which _safe_resolve() turns into a 404. This is more explicit
        # than poking around in the filesystem root hoping to miss.
        return _MISSING_MOUNT_SENTINEL + url_path

    def _safe_resolve(self, local_path):
        if local_path.startswith(_MISSING_MOUNT_SENTINEL):
            return None
        # ValueError covers "embedded null character in path" raised by
        # Path.resolve() -> os.lstat() on some platforms (Python >= 3.9).
        try:
            resolved = Path(local_path).resolve()
        except (OSError, RuntimeError, ValueError):
            return None
        for m in self.server.mounts:
            try:
                resolved.relative_to(m["root"].resolve()); return resolved
            except (ValueError, OSError):
                continue
        return None

    def _mount_for(self, path_obj):
        try:
            p = Path(path_obj).resolve()
        except (OSError, RuntimeError, ValueError):
            return None, None
        best_root = None
        best_mount = None
        best_len = -1
        for m in self.server.mounts:
            try:
                r = m["root"].resolve()
            except (OSError, RuntimeError, ValueError):
                continue
            try:
                p.relative_to(r)
            except (ValueError, OSError):
                continue
            rlen = len(str(r))
            if rlen > best_len:
                best_len = rlen
                best_root = r
                best_mount = m
        if best_root is None:
            return None, None
        return best_root, best_mount

    # ------------------------------------------------------------- utilities
    def _bindings_for_render(self):
        scheme = getattr(self.server, "scheme", "http")
        port = self.server.server_port
        return [
            {"ip": ip, "source": source,
             "url": f"{scheme}://{ip}:{port}"}
            for ip, source in getattr(self.server, "bindings", [])
        ]

    def _host_base(self):
        host = self.headers.get("Host") or \
            f"{self.server.server_ip}:{self.server.server_port}"
        scheme = getattr(self.server, "scheme", "http")
        return f"{scheme}://{host}"

    def _build_breadcrumbs(self, mount_entry, rel_path):
        crumbs = [{"label": "Home", "url": "/"}]
        if mount_entry is not None and getattr(self.server, "multi", False):
            prefix = mount_entry["prefix"]
            if prefix != "/":
                crumbs.append({
                    "label": mount_entry.get("display") or mount_entry["name"],
                    "url": prefix,
                })
        if rel_path:
            if mount_entry is not None and mount_entry["prefix"] != "/":
                acc = mount_entry["prefix"].rstrip("/") + "/"
            else:
                acc = "/"
            for p in [x for x in rel_path.split("/") if x]:
                acc = acc + url_quote(p) + "/"
                crumbs.append({"label": p, "url": acc})
        for i, c in enumerate(crumbs):
            c["current"] = (i == len(crumbs) - 1)
        return crumbs

    def _base_url_for(self, path_obj, request_path):
        host = self.headers.get("Host") or \
            f"{self.server.server_ip}:{self.server.server_port}"
        scheme = getattr(self.server, "scheme", "http")
        rp = request_path
        if not rp.endswith("/"):
            rp += "/"
        return f"{scheme}://{host}{rp.rstrip('/')}"

    def _send_body(self, body, content_type, status=200, extra_headers=None):
        data = body.encode("utf-8") if isinstance(body, str) else body
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        if extra_headers:
            for k, v in extra_headers.items():
                self.send_header(k, v)
        self.end_headers()
        if getattr(self, "_head_only", False):
            return
        try:
            self.wfile.write(data)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def _send_json(self, obj, status=200):
        self._send_body(json.dumps(obj, indent=2),
                        "application/json; charset=utf-8", status=status)

    def _send_json_error(self, status, message):
        self._send_json({"ok": False, "error": message}, status=status)

    def _send_format_error(self, requested, available=None):
        avail = available if available is not None else VALID_FORMATS
        body = (f"[!] Invalid format: {requested!r}\n"
                f"Available formats: {', '.join(avail)}\n")
        self._send_body(body, "text/plain; charset=utf-8", status=400)

    def _upload_count(self):
        up = getattr(self.server, "upload_dir", None)
        return count_upload_files(up) if up else 0

    def _stream_file(self, path, size, content_type, extra_headers=None):
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(size))
        if extra_headers:
            for k, v in extra_headers.items():
                self.send_header(k, v)
        self.end_headers()
        if getattr(self, "_head_only", False):
            return
        try:
            with open(path, "rb") as f:
                shutil.copyfileobj(f, self.wfile, _STREAM_CHUNK)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def _read_request_body(self, limit):
        try:
            length = int(self.headers.get("Content-Length", 0) or 0)
        except (ValueError, TypeError):
            length = 0
        if length <= 0:
            return ""
        if length > limit:
            raise ValueError(
                f"body too large: {length} bytes (max {limit})"
            )
        raw = self.rfile.read(length)
        try:
            return raw.decode("utf-8")
        except UnicodeDecodeError:
            return raw.decode("utf-8", "replace")

    def _drain_request_body(self):
        """Consume any pending body bytes so a keep-alive client is not
        desynchronised by a request whose body we chose to ignore."""
        try:
            length = int(self.headers.get("Content-Length", 0) or 0)
        except (ValueError, TypeError):
            length = 0
        if length > 0:
            try:
                self.rfile.read(length)
            except (OSError, ValueError):
                self.close_connection = True

    # ------------------------------------------------------------- responders
    def _send_file(self, path_obj, mode):
        if mode == "render":
            if path_obj.suffix.lower() not in (".md", ".markdown"):
                self.send_error(
                    400, "Render mode is only supported for .md files")
                return
            try:
                size = path_obj.stat().st_size
            except OSError as e:
                self.send_error(404, f"Cannot stat file: {e}"); return
            if size > _RENDER_MAX_BYTES:
                self.send_error(
                    413,
                    f"File too large to render "
                    f"({human_size(size)} > {human_size(_RENDER_MAX_BYTES)})")
                return
            try:
                raw = path_obj.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError) as e:
                self.send_error(500, f"Cannot read file: {e}"); return
            base_path = self.path.split("?", 1)[0]
            text_url = base_path + "?mode=view"
            body = render_handbook_html(raw, path_obj.name, text_url)
            self._send_body(body, "text/html; charset=utf-8")
            return

        try:
            size = path_obj.stat().st_size
        except OSError as e:
            self.send_error(404, f"Cannot stat file: {e}"); return
        if not path_obj.is_file():
            self.send_error(404, "Not a regular file"); return
        ctype = self.guess_type(str(path_obj)) or "application/octet-stream"
        if mode == "download":
            fname = safe_filename(path_obj.name)
            extra = {"Content-Disposition": f'attachment; filename="{fname}"'}
        else:
            extra = {"Content-Disposition": "inline"}
        self._stream_file(path_obj, size, ctype, extra)

    def _send_file_json(self, path_obj):
        try:
            st = path_obj.stat()
        except OSError as e:
            self._send_json_error(404, f"Cannot stat file: {e}"); return
        ctype = self.guess_type(str(path_obj)) or "application/octet-stream"
        base_path = self.path.split("?", 1)[0]
        payload = {
            "name":       path_obj.name,
            "path":       str(path_obj),
            "size":       st.st_size,
            "size_human": human_size(st.st_size),
            "mtime":      int(st.st_mtime),
            "mime":       ctype,
            "view_url":     base_path + "?mode=view",
            "download_url": base_path + "?mode=download",
        }
        if path_obj.suffix.lower() in (".md", ".markdown"):
            payload["render_url"] = base_path + "?mode=render"
        self._send_json(payload)

    # --------------------------------------------------- fingerprint endpoint
    def _send_stat(self, parsed, query):
        multi = getattr(self.server, "multi", False)
        if multi and parsed.path in ("/", ""):
            _, fp = build_virtual_root_tree_and_fp(
                self.server.mounts, self.server.filters, None)
        else:
            local_path = self.translate_path(parsed.path)
            resolved = self._safe_resolve(local_path)
            if resolved is None or not resolved.exists():
                self._send_json_error(404, "Not found"); return
            if resolved.is_file():
                fp = file_fingerprint(resolved)
            else:
                mount_root, _ = self._mount_for(resolved)
                _, fp = build_listing_tree_and_fp(
                    resolved, self.server.filters, None,
                    share_root=mount_root)
        self._send_json({"fingerprint": fp})

    # ------------------------------------------------------ source endpoints
    def _project_root(self):
        return Path(__file__).resolve().parent.parent

    def _iter_project_files(self):
        root = self._project_root()
        entry = root / "macula.py"
        if entry.is_file() and not entry.is_symlink():
            yield entry, "macula.py"
        pkg = root / "macula"
        if pkg.is_dir():
            for p in pkg.rglob("*"):
                if p.is_symlink():
                    continue
                if "__pycache__" in p.parts:
                    continue
                if p.is_file():
                    yield p, str(p.relative_to(root))

    def _send_source(self, query):
        base = self.path.split('?', 1)[0]
        if "format" not in query:
            msg = (
                "[!] Missing ?format parameter.\n"
                f"    Use {base}?format=zip\n"
                f"    or  {base}?format=tgz\n"
            )
            self._send_body(msg, "text/plain; charset=utf-8", status=400)
            return
        fmt = (query["format"][0] or "").lower()
        if fmt == "zip":
            self._send_source_zip()
        elif fmt in ("tgz", "tar.gz", "targz"):
            self._send_source_targz()
        else:
            self._send_body(
                f"[!] Invalid source format: {fmt!r}. Use 'zip' or 'tgz'.\n",
                "text/plain; charset=utf-8", status=400)

    def _send_source_zip(self):
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
            for path, arcname in self._iter_project_files():
                try:
                    zf.write(path, arcname=arcname)
                except OSError:
                    continue
        data = buffer.getvalue()
        self._send_body(data, "application/zip", extra_headers={
            "Content-Disposition": 'attachment; filename="macula.zip"',
        })

    def _send_source_targz(self):
        buffer = io.BytesIO()
        with tarfile.open(fileobj=buffer, mode="w:gz") as tf:
            for path, arcname in self._iter_project_files():
                try:
                    tf.add(path, arcname=arcname)
                except OSError:
                    continue
        data = buffer.getvalue()
        self._send_body(data, "application/gzip", extra_headers={
            "Content-Disposition": 'attachment; filename="macula.tar.gz"',
        })

    # ---------------------------------------------------- handbook endpoint
    def _send_handbook(self, query):
        handbook = self._project_root() / HANDBOOK_FILE
        if not handbook.is_file() or handbook.is_symlink():
            self.send_error(404, f"{HANDBOOK_FILE} not found"); return
        try:
            raw = handbook.read_text(encoding="utf-8")
        except OSError as e:
            self.send_error(500, f"Cannot read {HANDBOOK_FILE}: {e}"); return

        view = (query.get("view", ["html"])[0] or "html").lower()
        handbook_endpoint = getattr(self.server, "handbook_endpoint",
                                    "/handbook.md")

        if view == "text":
            self._send_body(raw, "text/plain; charset=utf-8")
        elif view == "html":
            text_url = f"{handbook_endpoint}?view=text"
            body = render_handbook_html(raw, HANDBOOK_FILE, text_url)
            self._send_body(body, "text/html; charset=utf-8")
        else:
            self._send_body(
                f"[!] Invalid view: {view!r}. Use 'html' or 'text'.\n",
                "text/plain; charset=utf-8", status=400)

    # ------------------------------------------------------ clipboard endpoint
    def _send_clipboard(self, parsed, query):
        store = getattr(self.server, "clipboard", None)
        if store is None:
            self._send_json_error(404, "Clipboard disabled"); return

        cb_ep = getattr(self.server, "clipboard_endpoint", None) or "/clipboard"
        host_base = self._host_base()
        base = host_base + cb_ep

        def _decorate(room_meta):
            rid = room_meta["id"]
            out = dict(room_meta)
            out["url_html"] = f"{base}?id={rid}"
            out["url_json"] = f"{base}?format=json&id={rid}"
            out["url_text"] = f"{base}?format=text&id={rid}"
            out["url_raw"]  = f"{base}?format=raw&id={rid}"
            return out

        # ---------------------------------------------------------- GET
        # HEAD is handled here too: do_HEAD sets `_head_only` and delegates
        # to do_GET; every writer below honors the flag, so a HEAD request
        # produces the same status and headers as GET, without a body.
        if self.command in ("GET", "HEAD"):
            fmt = (query.get("format", ["html"])[0] or "html").lower()
            rid_raw = query.get("id", [None])[0]

            if fmt == "raw":
                if rid_raw is None:
                    self._send_body(
                        "[!] format=raw requires &id=N\n",
                        "text/plain; charset=utf-8", status=400)
                    return
                try:
                    rid = int(rid_raw)
                except (ValueError, TypeError):
                    self._send_body(
                        "[!] Invalid id\n",
                        "text/plain; charset=utf-8", status=400)
                    return
                room = store.get_room(rid)
                if room is None:
                    self._send_body(
                        f"[!] No such room: {rid}\n",
                        "text/plain; charset=utf-8", status=404)
                    return
                self._send_body(room["text"], "text/plain; charset=utf-8")
                return

            if fmt == "json":
                if rid_raw is not None:
                    try:
                        rid = int(rid_raw)
                    except (ValueError, TypeError):
                        self._send_json_error(400, "Invalid id"); return
                    room = store.get_room(rid)
                    if room is None:
                        self._send_json_error(404, "No such room"); return
                    self._send_json({
                        "ok": True,
                        "room": _decorate({
                            "id": room["id"],
                            "size": room["size"],
                            "ts": room["ts"],
                            "text": room["text"],
                        }),
                    })
                    return

                q = query.get("q", [None])[0]
                use_regex = query.get("regex") == ["1"]
                match_ids = store.search(q, use_regex) if q else None
                rooms = store.list_rooms()
                if match_ids is not None:
                    rooms = [r for r in rooms if r["id"] in match_ids]

                list_urls = {
                    "list_html": base,
                    "list_json": base + "?format=json",
                    "list_text": base + "?format=text",
                }
                if q:
                    qs = "&q=" + url_quote(q) + ("&regex=1" if use_regex else "")
                    list_urls["list_html_filtered"] = base + "?" + qs[1:]
                    list_urls["list_json_filtered"] = (
                        base + "?format=json" + qs)
                    list_urls["list_text_filtered"] = (
                        base + "?format=text" + qs)

                self._send_json({
                    "ok": True,
                    "count": len(rooms),
                    "filtered": match_ids is not None,
                    "query": q if q else None,
                    "regex": bool(use_regex) if q else None,
                    "urls": list_urls,
                    "rooms": [_decorate(r) for r in rooms],
                })
                return

            if fmt == "text":
                if rid_raw is not None:
                    try:
                        rid = int(rid_raw)
                    except (ValueError, TypeError):
                        self._send_body(
                            "[!] Invalid id\n",
                            "text/plain; charset=utf-8", status=400)
                        return
                    room = store.get_room(rid)
                    if room is None:
                        self._send_body(
                            f"[!] No such room: {rid}\n",
                            "text/plain; charset=utf-8", status=404)
                        return
                    ts = time.strftime("%Y-%m-%d %H:%M:%S",
                                       time.localtime(room["ts"]))
                    out = (
                        f"# id        {room['id']}\n"
                        f"# size      {room['size']} B\n"
                        f"# updated   {ts}\n"
                        f"# json      {base}?format=json&id={room['id']}\n"
                        f"# text      {base}?format=text&id={room['id']}\n"
                        f"# raw       {base}?format=raw&id={room['id']}\n"
                        f"#\n"
                    )
                    self._send_body(out + room["text"] + "\n",
                                    "text/plain; charset=utf-8")
                    return

                q = query.get("q", [None])[0]
                use_regex = query.get("regex") == ["1"]
                match_ids = store.search(q, use_regex) if q else None
                rooms = store.list_rooms()
                if match_ids is not None:
                    rooms = [r for r in rooms if r["id"] in match_ids]

                header = f"# Clipboard — {len(rooms)} "
                header += "room" if len(rooms) == 1 else "rooms"
                if q:
                    mode = "/regex/" if use_regex else "filter"
                    header += f"  [{mode}: {q}]"
                out = [header]
                if not rooms:
                    out.append("# (no rooms)")
                else:
                    for r in rooms:
                        prev = r["preview"] or "(empty)"
                        out.append(
                            f"#{r['id']:<4} {r['size']:>8}B  {prev}"
                        )
                        out.append(
                            f"      {base}?id={r['id']}"
                        )
                self._send_body("\n".join(out) + "\n",
                                "text/plain; charset=utf-8")
                return

            if fmt != "html":
                self._send_format_error(fmt); return

            initial_id = None
            if rid_raw is not None:
                try:
                    initial_id = int(rid_raw)
                except (ValueError, TypeError):
                    initial_id = None

            body = render_clipboard_html(
                endpoint=cb_ep,
                version=__version__,
                initial_id=initial_id,
            )
            self._send_body(body, "text/html; charset=utf-8")
            return

        # --------------------------------------------------------- POST
        if self.command == "POST":
            action = (query.get("action", [None])[0] or "").lower()

            if action == "create":
                try:
                    text = self._read_request_body(store.max_bytes_per_room)
                except ValueError as e:
                    self.close_connection = True
                    self._send_json_error(413, str(e)); return
                try:
                    rid = store.create_room(text)
                except ValueError as e:
                    self._send_json_error(413, str(e)); return
                self._send_json({
                    "ok": True, "id": rid,
                    "urls": {
                        "url_html": f"{base}?id={rid}",
                        "url_json": f"{base}?format=json&id={rid}",
                        "url_text": f"{base}?format=text&id={rid}",
                        "url_raw":  f"{base}?format=raw&id={rid}",
                    },
                })
                return

            if action == "update":
                rid_raw = query.get("id", [None])[0]
                try:
                    rid = int(rid_raw)
                except (ValueError, TypeError):
                    self._drain_request_body()
                    self._send_json_error(400, "Invalid id"); return
                try:
                    text = self._read_request_body(store.max_bytes_per_room)
                except ValueError as e:
                    self.close_connection = True
                    self._send_json_error(413, str(e)); return
                try:
                    ok = store.update_room(rid, text)
                except ValueError as e:
                    self._send_json_error(413, str(e)); return
                if not ok:
                    self._send_json_error(404, "No such room"); return
                self._send_json({"ok": True})
                return

            if action == "clear":
                rid_raw = query.get("id", [None])[0]
                # These three actions carry no body by contract; drain any
                # bytes a misbehaving client may have sent so keep-alive
                # is not desynchronised.
                self._drain_request_body()
                try:
                    rid = int(rid_raw)
                except (ValueError, TypeError):
                    self._send_json_error(400, "Invalid id"); return
                ok = store.clear_room(rid)
                self._send_json({"ok": ok})
                return

            if action == "delete":
                rid_raw = query.get("id", [None])[0]
                self._drain_request_body()
                try:
                    rid = int(rid_raw)
                except (ValueError, TypeError):
                    self._send_json_error(400, "Invalid id"); return
                ok = store.delete_room(rid)
                self._send_json({"ok": ok})
                return

            if action == "clear_all":
                self._drain_request_body()
                store.clear_all()
                self._send_json({"ok": True})
                return

            self._drain_request_body()
            self._send_json_error(
                400,
                "Missing or invalid ?action "
                "(create / update / clear / delete / clear_all)")
            return

        self._drain_request_body()
        self._send_json_error(405, "Method not allowed")

    # ------------------------------------------------------- listing renderers
    def _send_virtual_root(self, query, request_path):
        base_url = self._base_url_for(None, request_path)
        host_base = self._host_base()

        dl = set(query.get("download", []))
        pattern = query.get("match", [None])[0]
        if "zip" in dl or query.get("zip") == ["1"]:
            self._send_virtual_root_zip(pattern); return
        if "tgz" in dl or "targz" in dl or "tar.gz" in dl:
            self._send_virtual_root_targz(pattern); return

        fmt_raw = query.get("format", [None])[0]
        fmt = (fmt_raw or "html").lower()
        if fmt not in VALID_FORMATS:
            self._send_format_error(fmt_raw); return

        display_depth = self.server.max_depth
        if "depth" in query:
            try:
                display_depth = max(0, int(query["depth"][0]))
            except (ValueError, IndexError):
                pass
        elif fmt == "html" and self.server.max_depth is None:
            display_depth = 0

        upload_path = getattr(self.server, "upload_dir", None)
        upload_endpoint = getattr(self.server, "upload_endpoint", None)
        source_endpoint = getattr(self.server, "source_endpoint", None)
        handbook_endpoint = getattr(self.server, "handbook_endpoint", None)
        clipboard_endpoint = getattr(self.server, "clipboard_endpoint", None)
        clip_store = getattr(self.server, "clipboard", None)
        cb_count = clip_store.count() if clip_store else 0
        repo_url = getattr(self.server, "repo_url", None)
        token = getattr(self.server, "token", None)
        mounts_desc = list(self.server.mounts)
        up_count = self._upload_count()
        bindings = self._bindings_for_render()
        crumbs = self._build_breadcrumbs(None, "")
        ui_clipboard_endpoint = clipboard_endpoint if clip_store else None

        if fmt == "json":
            tree = build_virtual_root_tree(self.server.mounts,
                                           self.server.filters, display_depth)
            body = render_json(tree, "/ (virtual root)", base_url,
                               self.server.filters, display_depth,
                               upload_path=upload_path,
                               upload_endpoint=upload_endpoint,
                               source_endpoint=source_endpoint,
                               handbook_endpoint=handbook_endpoint,
                               clipboard_endpoint=ui_clipboard_endpoint,
                               repo_url=repo_url,
                               token=token,
                               max_upload_size=self.server.max_upload_size,
                               mounts=mounts_desc, upload_count=up_count,
                               bindings=bindings)
            self._send_body(body, "application/json; charset=utf-8")
        elif fmt == "text":
            tree = build_virtual_root_tree(self.server.mounts,
                                           self.server.filters, display_depth)
            body = render_text(tree, "/ (virtual root)", base_url,
                               self.server.filters, display_depth,
                               upload_path=upload_path,
                               upload_endpoint=upload_endpoint,
                               source_endpoint=source_endpoint,
                               handbook_endpoint=handbook_endpoint,
                               clipboard_endpoint=ui_clipboard_endpoint,
                               repo_url=repo_url,
                               token=token,
                               mounts=mounts_desc)
            self._send_body(body, "text/plain; charset=utf-8")
        else:
            tree, fingerprint = build_virtual_root_tree_and_fp(
                self.server.mounts, self.server.filters, display_depth)
            stat_url = (request_path or "/") + "?format=json&stat=1"
            body = render_html(tree, "/ (virtual root)", base_url,
                               self.server.filters, display_depth,
                               rel_path="", upload_path=upload_path,
                               upload_endpoint=upload_endpoint,
                               source_endpoint=source_endpoint,
                               handbook_endpoint=handbook_endpoint,
                               clipboard_endpoint=ui_clipboard_endpoint,
                               repo_url=repo_url,
                               max_upload_size=self.server.max_upload_size,
                               is_virtual_root=True,
                               upload_count=up_count,
                               clipboard_count=cb_count,
                               bindings=bindings, mounts=mounts_desc,
                               breadcrumbs=crumbs,
                               host_base=host_base,
                               fingerprint=fingerprint,
                               stat_url=stat_url)
            self._send_body(body, "text/html; charset=utf-8")

    def _send_listing(self, path_obj, fmt, request_path, query):
        base_url = self._base_url_for(path_obj, request_path)
        host_base = self._host_base()
        mount_root, mount_entry = self._mount_for(path_obj)

        display_depth = self.server.max_depth
        if "depth" in query:
            try:
                display_depth = max(0, int(query["depth"][0]))
            except (ValueError, IndexError):
                pass
        elif fmt == "html" and self.server.max_depth is None:
            display_depth = 0

        upload_path = getattr(self.server, "upload_dir", None)
        upload_endpoint = getattr(self.server, "upload_endpoint", None)
        source_endpoint = getattr(self.server, "source_endpoint", None)
        handbook_endpoint = getattr(self.server, "handbook_endpoint", None)
        clipboard_endpoint = getattr(self.server, "clipboard_endpoint", None)
        clip_store = getattr(self.server, "clipboard", None)
        cb_count = clip_store.count() if clip_store else 0
        repo_url = getattr(self.server, "repo_url", None)
        token = getattr(self.server, "token", None)
        mounts_desc = list(self.server.mounts)
        up_count = self._upload_count()
        bindings = self._bindings_for_render()
        ui_clipboard_endpoint = clipboard_endpoint if clip_store else None

        rel_path = ""
        if mount_root is not None:
            try:
                rel = Path(path_obj).resolve().relative_to(mount_root)
                rel_path = "" if str(rel) == "." else rel.as_posix()
            except (ValueError, OSError):
                pass
        crumbs = self._build_breadcrumbs(mount_entry, rel_path)

        if fmt == "json":
            tree = build_listing_tree(path_obj, self.server.filters,
                                      display_depth, share_root=mount_root)
            body = render_json(tree, path_obj, base_url,
                               self.server.filters, display_depth,
                               upload_path=upload_path,
                               upload_endpoint=upload_endpoint,
                               source_endpoint=source_endpoint,
                               handbook_endpoint=handbook_endpoint,
                               clipboard_endpoint=ui_clipboard_endpoint,
                               repo_url=repo_url,
                               token=token,
                               max_upload_size=self.server.max_upload_size,
                               mounts=mounts_desc, upload_count=up_count,
                               bindings=bindings)
            self._send_body(body, "application/json; charset=utf-8")
        elif fmt == "text":
            tree = build_listing_tree(path_obj, self.server.filters,
                                      display_depth, share_root=mount_root)
            body = render_text(tree, path_obj, base_url,
                               self.server.filters, display_depth,
                               upload_path=upload_path,
                               upload_endpoint=upload_endpoint,
                               source_endpoint=source_endpoint,
                               handbook_endpoint=handbook_endpoint,
                               clipboard_endpoint=ui_clipboard_endpoint,
                               repo_url=repo_url,
                               token=token,
                               mounts=mounts_desc)
            self._send_body(body, "text/plain; charset=utf-8")
        else:
            tree, fingerprint = build_listing_tree_and_fp(
                path_obj, self.server.filters, display_depth,
                share_root=mount_root)
            stat_url = request_path + "?format=json&stat=1"
            body = render_html(tree, path_obj, base_url,
                               self.server.filters, display_depth,
                               rel_path=rel_path, upload_path=upload_path,
                               upload_endpoint=upload_endpoint,
                               source_endpoint=source_endpoint,
                               handbook_endpoint=handbook_endpoint,
                               clipboard_endpoint=ui_clipboard_endpoint,
                               repo_url=repo_url,
                               max_upload_size=self.server.max_upload_size,
                               is_virtual_root=False,
                               upload_count=up_count,
                               clipboard_count=cb_count,
                               bindings=bindings, mounts=mounts_desc,
                               breadcrumbs=crumbs,
                               host_base=host_base,
                               fingerprint=fingerprint,
                               stat_url=stat_url)
            self._send_body(body, "text/html; charset=utf-8")

    # ------------------------------------------------------------- archives
    def _send_zip(self, folder_path, pattern=None):
        folder_path = Path(folder_path).resolve()
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".zip")
        tmp.close()
        try:
            try:
                with zipfile.ZipFile(tmp.name, "w", zipfile.ZIP_DEFLATED) as zf:
                    for root, _dirs, files in os.walk(folder_path):
                        root_path = Path(root)
                        for f in files:
                            if pattern and not fnmatch.fnmatch(
                                    f.lower(), pattern.lower()):
                                continue
                            full = root_path / f
                            if full.is_symlink():
                                continue
                            try:
                                rel = full.relative_to(folder_path)
                            except ValueError:
                                continue
                            try:
                                zf.write(full, arcname=rel.as_posix())
                            except OSError:
                                continue
            except Exception as e:
                self.send_error(500, f"Failed to build ZIP: {e}"); return
            size = os.path.getsize(tmp.name)
            fname = safe_filename(folder_path.name) + ".zip"
            self._stream_file(tmp.name, size, "application/zip", {
                "Content-Disposition": f'attachment; filename="{fname}"',
            })
        finally:
            try: os.unlink(tmp.name)
            except OSError: pass

    def _send_targz(self, folder_path, pattern=None):
        folder_path = Path(folder_path).resolve()
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".tar.gz")
        tmp.close()
        try:
            try:
                with tarfile.open(tmp.name, mode="w:gz") as tf:
                    for root, _dirs, files in os.walk(folder_path):
                        root_path = Path(root)
                        for f in files:
                            if pattern and not fnmatch.fnmatch(
                                    f.lower(), pattern.lower()):
                                continue
                            full = root_path / f
                            if full.is_symlink():
                                continue
                            try:
                                rel = full.relative_to(folder_path)
                            except ValueError:
                                continue
                            try:
                                tf.add(full, arcname=rel.as_posix())
                            except OSError:
                                continue
            except Exception as e:
                self.send_error(500, f"Failed to build TAR.GZ: {e}"); return
            size = os.path.getsize(tmp.name)
            fname = safe_filename(folder_path.name) + ".tar.gz"
            self._stream_file(tmp.name, size, "application/gzip", {
                "Content-Disposition": f'attachment; filename="{fname}"',
            })
        finally:
            try: os.unlink(tmp.name)
            except OSError: pass

    def _iter_virtual_root_files(self, pattern=None):
        for m in self.server.mounts:
            root = Path(m["root"]).resolve()
            prefix = m.get("name") or root.name or "mount"
            for r, _dirs, files in os.walk(root):
                rp = Path(r)
                for f in files:
                    if pattern and not fnmatch.fnmatch(
                            f.lower(), pattern.lower()):
                        continue
                    full = rp / f
                    if full.is_symlink():
                        continue
                    try:
                        rel = full.relative_to(root)
                    except ValueError:
                        continue
                    yield full, f"{prefix}/{rel.as_posix()}"

    def _send_virtual_root_zip(self, pattern=None):
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".zip")
        tmp.close()
        try:
            try:
                with zipfile.ZipFile(tmp.name, "w", zipfile.ZIP_DEFLATED) as zf:
                    for path, arcname in self._iter_virtual_root_files(pattern):
                        try:
                            zf.write(path, arcname=arcname)
                        except OSError:
                            continue
            except Exception as e:
                self.send_error(500, f"Failed to build ZIP: {e}"); return
            size = os.path.getsize(tmp.name)
            self._stream_file(tmp.name, size, "application/zip", {
                "Content-Disposition": 'attachment; filename="macula-root.zip"',
            })
        finally:
            try: os.unlink(tmp.name)
            except OSError: pass

    def _send_virtual_root_targz(self, pattern=None):
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".tar.gz")
        tmp.close()
        try:
            try:
                with tarfile.open(tmp.name, mode="w:gz") as tf:
                    for path, arcname in self._iter_virtual_root_files(pattern):
                        try:
                            tf.add(path, arcname=arcname)
                        except OSError:
                            continue
            except Exception as e:
                self.send_error(500, f"Failed to build TAR.GZ: {e}"); return
            size = os.path.getsize(tmp.name)
            self._stream_file(tmp.name, size, "application/gzip", {
                "Content-Disposition": 'attachment; filename="macula-root.tar.gz"',
            })
        finally:
            try: os.unlink(tmp.name)
            except OSError: pass

    # ------------------------------------------------------------------ HTTP
    def do_GET(self):
        parsed = urlparse(self.path)
        query = parse_qs(parsed.query)

        if parsed.path == "/favicon.ico":
            self.send_response(204)
            self.end_headers()
            return

        handbook_endpoint = getattr(self.server, "handbook_endpoint", None)
        if handbook_endpoint and parsed.path == handbook_endpoint:
            self._send_handbook(query); return

        source_endpoint = getattr(self.server, "source_endpoint", None)
        if source_endpoint and parsed.path == source_endpoint:
            self._send_source(query); return

        clipboard_endpoint = getattr(self.server, "clipboard_endpoint", None)
        if clipboard_endpoint and parsed.path == clipboard_endpoint:
            self._send_clipboard(parsed, query); return

        if query.get("stat") == ["1"]:
            self._send_stat(parsed, query); return

        if getattr(self.server, "multi", False) and parsed.path in ("/", ""):
            self._send_virtual_root(query, parsed.path or "/"); return

        local_path = self.translate_path(parsed.path)
        resolved = self._safe_resolve(local_path)
        if resolved is None:
            self.send_error(404, "Not found"); return

        if resolved.is_dir():
            if not parsed.path.endswith("/"):
                location = parsed.path + "/"
                if parsed.query:
                    location += "?" + parsed.query
                self.send_response(301)
                self.send_header("Location", location)
                self.end_headers(); return

            dl = set(query.get("download", []))
            pattern = query.get("match", [None])[0]
            if "zip" in dl or query.get("zip") == ["1"]:
                self._send_zip(resolved, pattern); return
            if "tgz" in dl or "targz" in dl or "tar.gz" in dl:
                self._send_targz(resolved, pattern); return

            fmt_raw = query.get("format", [None])[0]
            if fmt_raw is None:
                fmt = "html"
            else:
                fmt = fmt_raw.lower()
                if fmt not in VALID_FORMATS:
                    self._send_format_error(fmt_raw); return

            self._send_listing(resolved, fmt, parsed.path, query)
            return

        if resolved.is_file():
            fmt_raw = query.get("format", [None])[0]
            fmt_norm = (fmt_raw or "").lower() if fmt_raw is not None else ""
            if fmt_norm == "json":
                self._send_file_json(resolved); return
            if fmt_norm not in ("",):
                # On a file only `json` and "no format" are valid; `html`
                # and `text` are meaningful for directories only.
                self._send_format_error(fmt_raw, available=("json",)); return

            mode = (query.get("mode", ["view"])[0] or "view").lower()
            if mode not in ("view", "download", "render"):
                self._send_body(
                    f"[!] Invalid mode: {mode!r}. "
                    f"Use 'view', 'download' or 'render'.\n",
                    "text/plain; charset=utf-8", status=400)
                return
            self._send_file(resolved, mode)
            return

        self.send_error(404, "Not found")

    def do_HEAD(self):
        self._head_only = True
        try:
            self.do_GET()
        finally:
            self._head_only = False

    def do_POST(self):
        parsed = urlparse(self.path)
        query = parse_qs(parsed.query)

        clipboard_endpoint = getattr(self.server, "clipboard_endpoint", None)
        if clipboard_endpoint and parsed.path == clipboard_endpoint:
            self._send_clipboard(parsed, query); return

        upload_endpoint = getattr(self.server, "upload_endpoint", None)
        if not upload_endpoint or parsed.path.rstrip("/") != upload_endpoint:
            self._drain_request_body()
            self._send_json_error(404, "Not found"); return

        target = getattr(self.server, "upload_dir", None)
        if target is None:
            self._drain_request_body()
            self._send_json_error(403, "Uploads are disabled on this server"); return

        try:
            length = int(self.headers.get("Content-Length", 0))
        except (ValueError, TypeError):
            length = 0
        if length <= 0:
            self._send_json_error(400, "Empty request body"); return

        max_bytes = self.server.max_upload_size or 0
        if max_bytes and length > max_bytes:
            self.close_connection = True
            self._send_json_error(413,
                f"Payload too large: {human_size(length)} (max {human_size(max_bytes)})")
            return

        ctype = (self.headers.get("Content-Type") or "").lower()
        if ctype.startswith("multipart/form-data"):
            self._handle_multipart_upload(target, length)
        elif query.get("name"):
            raw_name = query["name"][0]
            body = self.rfile.read(length)
            self._save_uploaded_stream(target, raw_name, io.BytesIO(body))
        else:
            self._drain_request_body()
            self._send_json_error(400,
                "Unsupported upload. Use multipart/form-data, "
                "or add ?name=filename for raw body upload.")

    def _handle_multipart_upload(self, target_dir, length):
        ctype = self.headers.get("Content-Type", "")
        boundary = _extract_boundary(ctype)
        if not boundary:
            self._drain_request_body()
            self._send_json_error(400, "Malformed multipart: missing boundary")
            return

        saved, errors = [], []
        try:
            for filename, body in _iter_multipart_parts(self.rfile, boundary,
                                                        length):
                try:
                    if not filename:
                        # Part without a filename: skip it. Its body has
                        # already been spooled and is discarded on close.
                        continue
                    entry = self._save_uploaded_stream(target_dir, filename,
                                                       body, respond=False)
                    if entry:
                        saved.append(entry)
                    else:
                        errors.append(filename)
                finally:
                    body.close()
        except _MultipartError as e:
            self._send_json_error(400, f"Malformed multipart: {e}")
            return
        except (BrokenPipeError, ConnectionResetError):
            return

        if not saved:
            if errors:
                self._send_json_error(400, "; ".join(errors))
            else:
                self._send_json_error(400, "No files found in request")
            return

        self._send_json({"ok": True, "saved": saved,
                         "errors": errors, "target": str(target_dir)})

    def _save_uploaded_stream(self, target_dir, raw_name, body, respond=True):
        """Persist a streamed upload to `<target_dir>/<raw_name>`.

        Symlink safety:
          - the destination (final path component) is rejected if it is
            already a symlink, and re-checked after the parent chain is
            created (the parent could have been swapped concurrently);
          - the file is opened with O_NOFOLLOW where the platform
            supports it, so the final component is never followed;
          - the resolved path is verified to stay inside <target_dir>.
        """
        rel = _sanitize_upload_path(raw_name)
        if not rel:
            if respond:
                self._send_json_error(
                    400, "Invalid filename (empty, absolute, or '..' present)")
            return None

        base = Path(target_dir).resolve()
        candidate = base / rel

        # Reject a symlink at the destination BEFORE creating any parent
        # directories, so a pre-existing symlink is never followed.
        if candidate.is_symlink():
            if respond:
                self._send_json_error(
                    409, f"Refusing to overwrite symlink: {candidate}")
            return None

        try:
            resolved = candidate.resolve()
        except (OSError, RuntimeError, ValueError):
            if respond: self._send_json_error(500, "Cannot resolve path")
            return None
        try:
            resolved.relative_to(base)
        except ValueError:
            if respond:
                self._send_json_error(400, "Upload path escapes upload root")
            return None

        try:
            candidate.parent.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            if respond: self._send_json_error(500, f"Cannot create folder: {e}")
            return None

        # Re-check after mkdir: a concurrent process could have replaced
        # a parent directory with a symlink between resolve() and mkdir().
        if candidate.is_symlink():
            if respond:
                self._send_json_error(
                    409, f"Refusing to overwrite symlink: {candidate}")
            return None

        flags = (os.O_WRONLY | os.O_CREAT | os.O_TRUNC
                 | getattr(os, "O_NOFOLLOW", 0))
        try:
            fd = os.open(candidate, flags, 0o644)
        except OSError as e:
            if respond: self._send_json_error(500, f"Write failed: {e}")
            return None

        size = 0
        try:
            with os.fdopen(fd, "wb") as out:
                body.seek(0)
                while True:
                    chunk = body.read(_STREAM_CHUNK)
                    if not chunk:
                        break
                    out.write(chunk)
                    size += len(chunk)
        except OSError as e:
            if respond: self._send_json_error(500, f"Write failed: {e}")
            return None

        entry = {"name": rel, "size": size, "path": str(candidate)}
        print(f"[+] UPLOAD from {self.client_address[0]}: {rel} "
              f"({human_size(size)}) -> {candidate}")
        if respond:
            self._send_json({
                "ok": True,
                "saved": [entry],
                "errors": [],
                "target": str(target_dir),
            })
        return entry

    # Kept for compatibility with the raw-body branch above; delegates
    # to _save_uploaded_stream so both paths share the same safety checks.
    def _save_uploaded_file(self, target_dir, raw_name, data, respond=True):
        return self._save_uploaded_stream(target_dir, raw_name,
                                          io.BytesIO(data), respond=respond)

    def log_message(self, format, *args):
        print(f"[*] {self.client_address[0]} - {format % args}")


class MaculaServer(socketserver.ThreadingTCPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, server_address, RequestHandlerClass,
                 allowed_client=None, bind_and_activate=True):
        self.allowed_client = allowed_client
        super().__init__(server_address, RequestHandlerClass, bind_and_activate)

    def verify_request(self, request, client_address):
        client_ip = client_address[0]
        if self.allowed_client and client_ip != self.allowed_client:
            print(f"[!] BLOCKED: Dropped unauthorized connection from {client_ip}")
            return False
        return True