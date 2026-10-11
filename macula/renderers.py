# file: macula/renderers.py

"""Text, JSON, and HTML renderers plus static asset loading."""
import functools
import html as html_module
import json as json_module
from pathlib import Path
from string import Template

from . import (CLIPBOARD_AUTOSAVE_MS, CLIPBOARD_POLL_MS, __version__)
from .markdown import render_markdown
from .tree import count_tree
from .utils import (fmt_depth, fmt_filters, fmt_max_upload, url_quote_path)


# ---------------------------------------------------------------------------
# Inline SVG fragments
# ---------------------------------------------------------------------------
SVG_CHEVRON    = ('<svg class="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" '
                  'stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">'
                  '<path d="m9 18 6-6-6-6"/></svg>')
SVG_FOLDER_ICON = ('<svg class="icon icon-folder" viewBox="0 0 24 24" fill="none" '
                   'stroke="currentColor" stroke-width="2" stroke-linecap="round" '
                   'stroke-linejoin="round" aria-hidden="true">'
                   '<path d="M20 20a2 2 0 0 0 2-2V8a2 2 0 0 0-2-2h-7.9a2 2 0 0 1-1.69-.9'
                   'L9.6 3.9A2 2 0 0 0 7.93 3H4a2 2 0 0 0-2 2v13a2 2 0 0 0 2 2Z"/></svg>')
SVG_FILE_ICON  = ('<svg class="icon icon-file" viewBox="0 0 24 24" fill="none" '
                  'stroke="currentColor" stroke-width="2" stroke-linecap="round" '
                  'stroke-linejoin="round" aria-hidden="true">'
                  '<path d="M15 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7Z"/>'
                  '<path d="M14 2v5h5"/></svg>')
SVG_ZIP_ICON   = ('<svg class="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" '
                  'stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">'
                  '<path d="M21 8v13H3V8"/><rect x="1" y="3" width="22" height="5" rx="1"/>'
                  '<path d="M10 12h4"/></svg>')
SVG_TGZ_ICON   = ('<svg class="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" '
                  'stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">'
                  '<path d="M21 8v13H3V8"/><rect x="1" y="3" width="22" height="5" rx="1"/>'
                  '<path d="M9 12h6M9 16h6"/></svg>')
SVG_OPEN_ICON  = ('<svg class="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" '
                  'stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">'
                  '<path d="M15 3h6v6M10 14 21 3M21 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h6"/></svg>')
SVG_DOWNLOAD_MINI = ('<svg class="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" '
                     'stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">'
                     '<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>'
                     '<path d="m7 10 5 5 5-5"/><path d="M12 15V3"/></svg>')
SVG_UPLOAD_ICON = ('<svg class="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" '
                   'stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">'
                   '<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>'
                   '<path d="m17 8-5-5-5 5"/><path d="M12 3v12"/></svg>')
SVG_UPLOAD_BIG  = ('<svg class="dz-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" '
                   'stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">'
                   '<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>'
                   '<path d="m17 8-5-5-5 5"/><path d="M12 3v12"/></svg>')
SVG_SEARCH_INNER   = ('<svg class="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" '
                      'stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">'
                      '<circle cx="11" cy="11" r="8"/><path d="m21 21-4.3-4.3"/></svg>')
SVG_EXPAND_INNER   = ('<svg class="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" '
                      'stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">'
                      '<path d="M12 5v14M5 12h14"/></svg>')
SVG_COLLAPSE_INNER = ('<svg class="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" '
                      'stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">'
                      '<path d="M5 12h14"/></svg>')
SVG_HOME_INNER     = ('<svg class="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" '
                      'stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">'
                      '<path d="m3 9 9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/>'
                      '<path d="M9 22V12h6v10"/></svg>')
SVG_REFRESH_INNER  = ('<svg class="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" '
                      'stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">'
                      '<path d="M21 12a9 9 0 1 1-3-6.7L21 8"/><path d="M21 3v5h-5"/></svg>')
SVG_AUTO_INNER     = ('<svg class="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" '
                      'stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">'
                      '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/></svg>')
SVG_BACK           = ('<svg class="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" '
                      'stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">'
                      '<path d="M19 12H5M12 19l-7-7 7-7"/></svg>')
SVG_DOWNLOAD_INNER = ('<svg class="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" '
                      'stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">'
                      '<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>'
                      '<path d="m7 10 5 5 5-5"/><path d="M12 15V3"/></svg>')
SVG_CHEVRON_INNER  = ('<svg class="icon icon-chevron" viewBox="0 0 24 24" fill="none" stroke="currentColor" '
                      'stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">'
                      '<path d="m6 9 6 6 6-6"/></svg>')
SVG_HANDBOOK_INNER = ('<svg class="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" '
                      'stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">'
                      '<path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"/>'
                      '<path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z"/>'
                      '<path d="M9 7h7M9 11h7"/></svg>')
SVG_CLIPBOARD_INNER = ('<svg class="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" '
                       'stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">'
                       '<rect x="8" y="2" width="8" height="4" rx="1"/>'
                       '<path d="M16 4h2a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h2"/></svg>')
SVG_GITHUB         = ('<svg class="icon" viewBox="0 0 24 24" fill="currentColor" '
                      'aria-hidden="true">'
                      '<path d="M12 .3a12 12 0 0 0-3.8 23.4c.6.1.8-.3.8-.6v-2c-3.3.7-4-1.6-4-1.6'
                      '-.6-1.4-1.4-1.8-1.4-1.8-1.1-.7.1-.7.1-.7 1.2.1 1.9 1.3 1.9 1.3 1 1.8 '
                      '2.8 1.3 3.5 1 0-.8.4-1.3.8-1.6-2.7-.3-5.5-1.3-5.5-6a4.7 4.7 0 0 1 '
                      '1.2-3.2c0-.3-.5-1.5.2-3.2 0 0 1-.3 3.3 1.2a11.3 11.3 0 0 1 6 0c2.3-1.5 '
                      '3.3-1.2 3.3-1.2.7 1.7.2 2.9.1 3.2a4.7 4.7 0 0 1 1.3 3.2c0 4.7-2.9 5.7'
                      '-5.6 6 .4.4.8 1.1.8 2.2v3.3c0 .3.2.7.8.6A12 12 0 0 0 12 .3z"/></svg>')
SVG_CLOSE          = ('<svg class="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" '
                      'stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">'
                      '<path d="M18 6 6 18M6 6l12 12"/></svg>')
SVG_CODE_ICON      = ('<svg class="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" '
                      'stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">'
                      '<polyline points="16 18 22 12 16 6"/><polyline points="8 6 2 12 8 18"/></svg>')
SVG_TEXT_ICON      = ('<svg class="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" '
                      'stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">'
                      '<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>'
                      '<polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/>'
                      '<line x1="16" y1="17" x2="8" y2="17"/></svg>')
SVG_SOURCE_DL      = ('<svg class="icon icon-accent" viewBox="0 0 24 24" fill="none" stroke="currentColor" '
                      'stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">'
                      '<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>'
                      '<path d="m7 10 5 5 5-5"/><path d="M12 15V3"/></svg>')


_EMPTY_STATE = (
    '<div class="empty-state">'
    '<svg class="es-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" '
    'stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">'
    '<path d="M22 12h-6l-2 3h-4l-2-3H2"/>'
    '<path d="M5.45 5.11 2 12v6a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2v-6l-3.45-6.89A2 2 0 0 0 16.76 4H7.24a2 2 0 0 0-1.79 1.11z"/>'
    '</svg>'
    '<div class="es-title">Nothing to show here</div>'
    '<div class="es-sub">Adjust your filters or add files to the shared folder.</div>'
    '</div>'
)


# ---------------------------------------------------------------------------
# Static asset loading
#
# `functools.lru_cache` keeps the read thread-safe: concurrent first-time
# lookups all hit the same cache slot, so the file is read at most once
# per process. The previous hand-rolled dict was not thread-safe.
# ---------------------------------------------------------------------------
_STATIC_DIR = Path(__file__).parent / "static"


@functools.lru_cache(maxsize=None)
def _load_static(name):
    return (_STATIC_DIR / name).read_text(encoding="utf-8")


def _plural(n, singular, plural=None):
    if plural is None:
        plural = singular + "s"
    return f"{n} {singular if n == 1 else plural}"


def _esc(s):
    return html_module.escape(s or "", quote=True)


# ---------------------------------------------------------------------------
# Dropdown builders
#
# All dropdown HTML lives here, in one place. page.html only injects the
# resulting fragments. Every menu starts with a .label (mini heading)
# followed by its items — same structure used by the Export dropdown.
# ---------------------------------------------------------------------------
def _build_source_dropdown(source_endpoint):
    if not source_endpoint:
        return ""
    ep = _esc(source_endpoint)
    return (
        '<div class="dropdown">'
        '<button class="btn dropdown-toggle" type="button" '
        'title="Download macula source">'
        f'{SVG_SOURCE_DL} {SVG_CHEVRON_INNER}'
        '</button>'
        '<div class="dropdown-menu">'
        '<div class="label">Source code</div>'
        f'<a href="{ep}?format=zip">{SVG_ZIP_ICON} ZIP archive</a>'
        f'<a href="{ep}?format=tgz">{SVG_TGZ_ICON} TAR.GZ archive</a>'
        '</div>'
        '</div>'
    )


def _build_clipboard_dropdown(clipboard_endpoint):
    if not clipboard_endpoint:
        return ""
    cb = _esc(clipboard_endpoint)
    return (
        '<div class="dropdown">'
        '<button class="btn dropdown-toggle" type="button" '
        'title="Shared clipboard — text rooms between clients">'
        f'{SVG_CLIPBOARD_INNER} {SVG_CHEVRON_INNER}'
        '</button>'
        '<div class="dropdown-menu">'
        '<div class="label">Clipboard</div>'
        f'<a href="{cb}">{SVG_OPEN_ICON} HTML</a>'
        f'<a href="{cb}?format=json">{SVG_CODE_ICON} JSON</a>'
        f'<a href="{cb}?format=text">{SVG_TEXT_ICON} Text</a>'
        '</div>'
        '</div>'
    )


def _build_handbook_dropdown(handbook_endpoint):
    if not handbook_endpoint:
        return ""
    hb = _esc(handbook_endpoint)
    return (
        '<div class="dropdown">'
        '<button class="btn dropdown-toggle" type="button" '
        'title="Operational handbook">'
        f'{SVG_HANDBOOK_INNER} {SVG_CHEVRON_INNER}'
        '</button>'
        '<div class="dropdown-menu">'
        '<div class="label">Handbook</div>'
        f'<a href="{hb}?view=html">{SVG_OPEN_ICON} HTML</a>'
        f'<a href="{hb}?view=text">{SVG_TEXT_ICON} Text</a>'
        '</div>'
        '</div>'
    )


def _build_export_dropdown():
    return (
        '<div class="dropdown">'
        '<button class="btn btn-ghost dropdown-toggle" type="button">'
        f'{SVG_DOWNLOAD_INNER} Export {SVG_CHEVRON_INNER}'
        '</button>'
        '<div class="dropdown-menu">'
        '<div class="label">Current directory</div>'
        f'<a href="?download=zip">{SVG_ZIP_ICON} Download as ZIP</a>'
        f'<a href="?download=tgz">{SVG_TGZ_ICON} Download as TAR.GZ</a>'
        '<hr>'
        '<div class="label">Listing</div>'
        f'<a href="?format=json">{SVG_CODE_ICON} View as JSON</a>'
        f'<a href="?format=text">{SVG_TEXT_ICON} View as plain text</a>'
        '</div>'
        '</div>'
    )


# ---------------------------------------------------------------------------
# Plain-text renderer
# ---------------------------------------------------------------------------
def _render_text_tree(root, out, base_url):
    """Pre-order depth-first render, iterative.

    The previous implementation recursed once per directory level; very
    deep trees could exhaust the interpreter's recursion limit. A LIFO
    stack keeps the output identical while bounding the call depth.
    """
    stack = [(root, "", True, True)]
    while stack:
        node, prefix, is_last, is_root = stack.pop()
        name = node["name"]
        rel = node.get("rel_path", "")
        tag = ""
        if node.get("is_upload"):
            tag = "  [upload]"
        elif node.get("is_mount"):
            tag = "  [mount]"

        if is_root:
            out.append("/" if name == "/" else f"{name}/")
            child_prefix = ""
        else:
            connector = "└── " if is_last else "├── "
            if node["type"] == "dir":
                url = f"{base_url}/" + (
                    url_quote_path(rel.rstrip("/")) if rel else "")
                url = url.rstrip("/") + "/"
                out.append(f"{prefix}{connector}{name}/{tag}  {url}")
            else:
                url = f"{base_url}/" + url_quote_path(rel)
                size = node.get("size_human", "")
                out.append(f"{prefix}{connector}{name}  {size}  {url}")
            child_prefix = prefix + ("    " if is_last else "│   ")

        items = list(node.get("dirs", [])) + list(node.get("files", []))
        # Push in reverse so LIFO yields them in declaration order.
        for i in range(len(items) - 1, -1, -1):
            child = items[i]
            child_last = (i == len(items) - 1)
            stack.append((child, child_prefix, child_last, False))


def render_text(tree_root, directory, base_url, filters=None, depth=None,
                upload_path=None, upload_endpoint=None, source_endpoint=None,
                handbook_endpoint=None, clipboard_endpoint=None,
                repo_url=None, token=None, mounts=None):
    nd, nf = count_tree(tree_root)
    header = [
        f"# Directory : {directory}",
        f"# Base URL  : {base_url}",
        f"# Filters   : {fmt_filters(filters)}",
        f"# Depth     : {fmt_depth(depth)}",
        f"# Count     : {nd} dirs, {nf} files",
    ]
    if token:
        header.append(f"# Token     : {token}")
    if source_endpoint:
        header.append(f"# Source    : {source_endpoint}?format=zip")
        header.append(f"#             {source_endpoint}?format=tgz")
    if handbook_endpoint:
        header.append(f"# Handbook  : {handbook_endpoint}?view=html")
        header.append(f"#             {handbook_endpoint}?view=text")
    if clipboard_endpoint:
        header.append(f"# Clipboard : {clipboard_endpoint}")
    if upload_endpoint:
        header.append(f"# Upload    : POST {upload_endpoint}")
    else:
        header.append("# Upload    : disabled")
    if repo_url:
        header.append(f"# Repo      : {repo_url}")
    if mounts:
        header.append("# Mounts    :")
        for m in mounts:
            tag = "upload" if m.get("is_upload") else "share"
            header.append(f"#             [{tag:<6}] {m['prefix']:<14} -> {m['root']}")
    header.append("")
    out = []
    _render_text_tree(tree_root, out, base_url)
    return "\n".join(header) + "\n" + "\n".join(out) + "\n"


# ---------------------------------------------------------------------------
# JSON renderer
# ---------------------------------------------------------------------------
def _tree_to_json(node, base_url):
    name = node["name"]
    rel = node.get("rel_path", "")
    if node["type"] == "dir":
        url = f"{base_url}/" + (url_quote_path(rel.rstrip("/")) if rel else "")
        url = url.rstrip("/") + "/"
        entry = {
            "name": name, "type": "dir", "path": node.get("path", ""),
            "rel_path": rel, "url": url,
            "download_url": url + "?download=zip",
            "download_tgz_url": url + "?download=tgz",
            "dirs": [_tree_to_json(d, base_url) for d in node.get("dirs", [])],
            "files": [_tree_to_json(f, base_url) for f in node.get("files", [])],
        }
        if node.get("is_mount"):
            entry["mount"] = True
        if node.get("is_upload"):
            entry["upload"] = True
        return entry
    url = f"{base_url}/" + url_quote_path(rel)
    return {
        "name": name, "type": "file", "path": node.get("path", ""),
        "rel_path": rel, "size": node.get("size", 0),
        "mtime": node.get("mtime", 0),
        "size_human": node.get("size_human", ""), "url": url,
        "view_url": url + "?mode=view", "download_url": url + "?mode=download",
    }


def render_json(tree_root, directory, base_url, filters=None, depth=None,
                upload_path=None, upload_endpoint=None, source_endpoint=None,
                handbook_endpoint=None, clipboard_endpoint=None,
                repo_url=None, token=None, max_upload_size=None,
                mounts=None, upload_count=0, bindings=None):
    nd, nf = count_tree(tree_root)
    payload = {
        "directory": str(directory), "base_url": base_url,
        "filters": list(filters) if filters else [],
        "max_depth": depth,
        "token": token,
        "source_endpoint": source_endpoint,
        "source_zip_url": (source_endpoint + "?format=zip") if source_endpoint else None,
        "source_tgz_url": (source_endpoint + "?format=tgz") if source_endpoint else None,
        "handbook_endpoint": handbook_endpoint,
        "handbook_html_url": (handbook_endpoint + "?view=html") if handbook_endpoint else None,
        "handbook_text_url": (handbook_endpoint + "?view=text") if handbook_endpoint else None,
        "repo_url": repo_url,
        # Present only when the clipboard is enabled. Omitted entirely
        # when disabled (HANDBOOK.md §Disabling).
        **({"clipboard_endpoint": clipboard_endpoint}
           if clipboard_endpoint is not None else {}),
        "upload_enabled": upload_path is not None,
        "upload_endpoint": upload_endpoint,
        "upload_path": str(upload_path) if upload_path else None,
        "max_upload_size": max_upload_size,
        "count": {"dirs": nd, "files": nf},
        "upload_count": upload_count,
        "tree": _tree_to_json(tree_root, base_url),
        "_notes": {
            "base_url":  "prepend this to any 'rel_path' to build an absolute URL",
            "path":      "relative to the parent node — for tree walking only",
            "rel_path":  "relative to the current page URL — use with base_url",
        },
    }
    if mounts:
        payload["mounts"] = [
            {"prefix": m["prefix"], "root": str(m["root"]),
             "name": m["name"], "display": m.get("display") or m["name"],
             "is_upload": bool(m.get("is_upload"))}
            for m in mounts
        ]
    if bindings:
        payload["bindings"] = bindings
    return json_module.dumps(payload, indent=2)


# ---------------------------------------------------------------------------
# HTML renderer
# ---------------------------------------------------------------------------
def _html_dir_node(d, parent_path, is_mount=False):
    full_path = parent_path + d["path"]
    name = html_module.escape(d["name"])
    path_attr = html_module.escape(full_path, quote=True)
    path_esc = html_module.escape(url_quote_path(full_path), quote=True)

    extra_cls = ""
    badge_html = ""
    if d.get("is_upload"):
        extra_cls = " upload"
        badge_html = '<span class="badge">upload</span>'
    elif is_mount:
        badge_html = '<span class="badge mount">mount</span>'

    return (
        f'<div class="node dir{" mount" if is_mount else ""}{extra_cls}" '
        f'data-name="{name}" data-path="{path_attr}">'
        f'<div class="row">'
        f'<span class="toggle">{SVG_CHEVRON}</span>'
        f'{SVG_FOLDER_ICON}'
        f'<span class="name">{name}</span>'
        f'{badge_html}'
        f'<div class="row-actions">'
        f'<a class="mini" href="{path_esc}?download=zip" title="Download as ZIP">{SVG_ZIP_ICON}</a>'
        f'<a class="mini" href="{path_esc}?download=tgz" title="Download as TAR.GZ">{SVG_TGZ_ICON}</a>'
        f'<a class="mini" href="{path_esc}" title="Open folder page">{SVG_OPEN_ICON}</a>'
        f'</div>'
        f'</div>'
        f'<div class="children"></div>'
        f'</div>'
    )


def _html_file_node(f, parent_path):
    full_path = parent_path + f["path"]
    name = html_module.escape(f["name"])
    path_attr = html_module.escape(full_path, quote=True)
    path_esc = html_module.escape(url_quote_path(full_path), quote=True)
    return (
        f'<div class="node file" data-name="{name}" '
        f'data-path="{path_attr}">'
        f'<div class="row">'
        f'<span class="toggle leaf"></span>'
        f'{SVG_FILE_ICON}'
        f'<a class="name" href="{path_esc}?mode=view">{name}</a>'
        f'<span class="size">{f["size_human"]}</span>'
        f'<div class="row-actions">'
        f'<a class="mini" href="{path_esc}?mode=download" title="Download">{SVG_DOWNLOAD_MINI}</a>'
        f'</div>'
        f'</div>'
        f'</div>'
    )


def _render_breadcrumbs(crumbs):
    if not crumbs or len(crumbs) < 2:
        return ""
    parts = []
    for i, c in enumerate(crumbs):
        if i > 0:
            parts.append('<span class="crumb-sep">/</span>')
        label = html_module.escape(c["label"])
        url = html_module.escape(c["url"], quote=True)
        if c.get("current"):
            parts.append(f'<span class="crumb current">{label}</span>')
        else:
            parts.append(f'<a class="crumb" href="{url}">{label}</a>')
    return '<div class="breadcrumbs-bar">' + "".join(parts) + '</div>'


def _render_header_info(bindings, mounts, source_endpoint=None):
    rows = []

    if bindings:
        bind_lines = []
        for b in bindings:
            url = html_module.escape(b["url"], quote=True)
            src = html_module.escape(b.get("source", ""))
            src_html = f'<span class="bind-src">{src}</span>' if src else ""
            bind_lines.append(
                f'<div class="bind-line">'
                f'<a href="{url}" target="_blank" rel="noopener">{html_module.escape(b["url"])}</a>'
                f'{src_html}'
                f'</div>'
            )
        rows.append(
            '<div class="info-row">'
            '<span class="info-label">URL</span>'
            '<div class="info-values">' + "\n".join(bind_lines) + '</div>'
            '</div>'
        )

    if source_endpoint:
        zip_esc = html_module.escape(source_endpoint + "?format=zip", quote=True)
        tgz_esc = html_module.escape(source_endpoint + "?format=tgz", quote=True)
        src_esc = html_module.escape(source_endpoint)
        rows.append(
            '<div class="info-row">'
            '<span class="info-label">Source</span>'
            '<div class="info-values">'
            '<div class="bind-line">'
            f'<a href="{zip_esc}">ZIP</a>'
            '<span class="bind-src">·</span>'
            f'<a href="{tgz_esc}">TGZ</a>'
            f'<span class="bind-src">{src_esc}</span>'
            '</div>'
            '</div>'
            '</div>'
        )

    if mounts:
        mount_lines = []
        for m in mounts:
            kind = "upload" if m.get("is_upload") else "share"
            prefix = m["prefix"]
            root = str(m["root"])
            prefix_esc = html_module.escape(prefix, quote=True)
            root_esc = html_module.escape(root)
            mount_lines.append(
                f'<div class="mount-row">'
                f'<span class="mount-kind {kind}">{kind}</span>'
                f'<a class="mount-prefix" href="{prefix_esc}">{html_module.escape(prefix)}</a>'
                f'<span class="mount-arrow">&rarr;</span>'
                f'<span class="mount-path" title="{root_esc}">{root_esc}</span>'
                f'</div>'
            )
        rows.append(
            '<div class="info-row">'
            '<span class="info-label">Mounts</span>'
            '<div class="info-values">' + "\n".join(mount_lines) + '</div>'
            '</div>'
        )

    if not rows:
        return ""
    return '<div class="header-info">' + "\n".join(rows) + '</div>'


def _depth_labels(depth):
    """Return (value, hint) for the 'Depth' stat pill.

    Centralised so render_html() and render_text() cannot drift.
    """
    if depth is None:
        return fmt_depth(depth), "Every level is walked on page load"
    if depth == 0:
        return (fmt_depth(depth, lazy_label=True),
                "Only the top level is shown; deeper folders expand when clicked")
    return (fmt_depth(depth),
            f"Up to {depth} {'level' if depth == 1 else 'levels'} "
            f"shown on page load")


def render_html(tree, directory, base_url, filters=None, depth=None,
                rel_path="", upload_path=None, upload_endpoint=None,
                source_endpoint=None, handbook_endpoint=None,
                clipboard_endpoint=None, repo_url=None,
                max_upload_size=None,
                is_virtual_root=False, upload_count=0, clipboard_count=0,
                bindings=None, mounts=None, breadcrumbs=None, host_base=None,
                fingerprint=None, stat_url=None):
    dirs = tree.get("dirs", [])
    files = tree.get("files", [])
    nd, nf = count_tree(tree)

    nodes = []
    for d in dirs:
        nodes.append(_html_dir_node(d, "", is_mount=is_virtual_root))
    for f in files:
        nodes.append(_html_file_node(f, ""))
    tree_html = "\n".join(nodes) if nodes else _EMPTY_STATE

    back_btn = ""
    if rel_path and not is_virtual_root:
        back_btn = (f'<a class="icon-btn" href="../" title="Up one level">'
                    f'{SVG_BACK}</a>')

    upload_enabled = upload_path is not None
    max_upload_str = fmt_max_upload(max_upload_size or 0)

    # -- upload button + dropzone ------------------------------------------
    upload_button_html = ""
    upload_stat_html = ""
    dropzone_html = ""
    if upload_enabled and upload_endpoint:
        upload_button_html = (
            f'<button class="btn btn-primary upload-toggle" type="button">'
            f'{SVG_UPLOAD_ICON} Upload file</button>'
        )
        upload_stat_html = (
            f'<span class="stat upload-stat" '
            f'title="Files received in the upload folder">'
            f'<span class="k">\U0001F513 Upload</span>'
            f'<span class="v">{_plural(upload_count, "file")}</span></span>'
        )
        dropzone_html = Template(_load_static("dropzone.html")).safe_substitute(
            svg_upload_big=SVG_UPLOAD_BIG,
            upload_path=html_module.escape(str(upload_path)),
            max_upload=html_module.escape(max_upload_str),
            endpoint=html_module.escape(upload_endpoint),
        )

    # -- dropdowns (all built in one place) --------------------------------
    source_dropdown    = _build_source_dropdown(source_endpoint)
    clipboard_dropdown = _build_clipboard_dropdown(clipboard_endpoint)
    handbook_dropdown  = _build_handbook_dropdown(handbook_endpoint)
    export_dropdown    = _build_export_dropdown()

    # -- clipboard pill ----------------------------------------------------
    clipboard_stat_html = ""
    if clipboard_endpoint is not None:
        clipboard_stat_html = (
            f'<span class="stat clipboard-stat" '
            f'title="Text rooms shared between every connected client">'
            f'<span class="k">\U0001F4CB Clipboard</span>'
            f'<span class="v">{_plural(clipboard_count, "room")}</span></span>'
        )

    # -- mounts pill -------------------------------------------------------
    mounts_stat_html = ""
    if is_virtual_root and dirs:
        n = len(dirs)
        mounts_stat_html = (
            f'<span class="stat mount-stat" '
            f'title="Directories mounted at the virtual root">'
            f'<span class="k">Mounts</span>'
            f'<span class="v">{_plural(n, "share")}</span></span>'
        )

    # -- filters / depth labels --------------------------------------------
    filters_val = fmt_filters(filters)
    filters_hint = (
        "Only files matching one of these keywords or globs are shown"
        if filters else
        "No filter — every file is listed"
    )
    depth_val, depth_hint = _depth_labels(depth)

    items_hint = (
        f"{nd} {'directory' if nd == 1 else 'directories'}, "
        f"{nf} {'file' if nf == 1 else 'files'}"
    )

    # The virtual root would read "/ (virtual root)" as the page title,
    # which is clumsy in a tab. Use "/" instead — the breadcrumb and the
    # header already explain that this is the root.
    page_title = "/" if is_virtual_root else str(directory)

    ctx = {
        "version":            __version__,
        "title":              html_module.escape(page_title),
        "css":                _load_static("style.css"),
        "js":                 _load_static("app.js"),
        "svg_chevron":        SVG_CHEVRON_INNER,
        "svg_search":         SVG_SEARCH_INNER,
        "svg_expand":         SVG_EXPAND_INNER,
        "svg_collapse":       SVG_COLLAPSE_INNER,
        "svg_home":           SVG_HOME_INNER,
        "svg_refresh":        SVG_REFRESH_INNER,
        "svg_auto":           SVG_AUTO_INNER,
        "svg_github":         SVG_GITHUB,
        "filters":            html_module.escape(filters_val),
        "filters_hint":       html_module.escape(filters_hint, quote=True),
        "depth":              html_module.escape(depth_val),
        "depth_hint":         html_module.escape(depth_hint, quote=True),
        "items_label":        html_module.escape(f"{nd} dirs · {nf} files"),
        "items_hint":         html_module.escape(items_hint, quote=True),
        "max_upload":         html_module.escape(max_upload_str),
        "mounts_stat":        mounts_stat_html,
        "upload_stat":        upload_stat_html,
        "clipboard_stat":     clipboard_stat_html,
        "repo_url":           html_module.escape(repo_url or "", quote=True),
        # dropdowns
        "source_dropdown":    source_dropdown,
        "clipboard_dropdown": clipboard_dropdown,
        "handbook_dropdown":  handbook_dropdown,
        "export_dropdown":    export_dropdown,
        # fragments
        "header_info":        _render_header_info(bindings or [], mounts or [],
                                                  source_endpoint),
        "breadcrumbs":        _render_breadcrumbs(breadcrumbs or []),
        "tree":               tree_html,
        "back_btn":           back_btn,
        "upload_button":      upload_button_html,
        "dropzone":           dropzone_html,
        "upload_target_js":   json_module.dumps(upload_endpoint) if upload_endpoint else '""',
        "fingerprint_js":     json_module.dumps(fingerprint or ""),
        "stat_url_js":        json_module.dumps(stat_url or ""),
    }
    return Template(_load_static("page.html")).safe_substitute(ctx)


# ---------------------------------------------------------------------------
# Handbook renderer
# ---------------------------------------------------------------------------
def render_handbook_html(markdown_body, title, text_url):
    body = render_markdown(markdown_body)
    ctx = {
        "title":    html_module.escape(title),
        "body":     body,
        "css":      _load_static("style.css"),
        "text_url": html_module.escape(text_url, quote=True),
        "version":  __version__,
    }
    return Template(_load_static("handbook.html")).safe_substitute(ctx)


# ---------------------------------------------------------------------------
# Clipboard renderer
# ---------------------------------------------------------------------------
def render_clipboard_html(endpoint, version, initial_id=None):
    ctx = {
        "css":            _load_static("style.css"),
        "version":        version,
        "endpoint_js":    json_module.dumps(endpoint),
        "initial_id_js":  json_module.dumps(initial_id),
        "poll_ms_js":     json_module.dumps(CLIPBOARD_POLL_MS),
        "autosave_ms_js": json_module.dumps(CLIPBOARD_AUTOSAVE_MS),
    }
    return Template(_load_static("clipboard.html")).safe_substitute(ctx)