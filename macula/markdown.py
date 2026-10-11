# file: macula/markdown.py

"""Minimal Markdown renderer — no external dependencies.

Supports a pragmatic subset of CommonMark plus a few extensions:
  - ATX headings (# .. ######) with auto-generated anchor ids
  - Paragraphs (soft-wrapped lines joined with a space)
  - Fenced code blocks (``` and ~~~), with optional language class
  - Inline code (`code`)
  - Bold (**x**, __x__) and italic (*x*, _x_)
  - Links [text](url) — including in-page anchors [text](#slug)
  - Unordered lists (-, *, +) and ordered lists (1.) with nesting
  - Blockquotes (> text)
  - Horizontal rules (---, ***, ___)
  - Pipe tables with optional alignment (| a | b |), GFM-compatible
    (outer pipes are optional)

HTML is escaped before processing, so user content cannot inject tags.
Link URLs are additionally filtered by scheme: only http, https, mailto,
tel, ftp, ftps, fragment-only, and relative URLs are kept. Anything else
(javascript:, data:, vbscript:, file:, ...) is replaced with '#'.

HTML comments (`<!-- ... -->`) are stripped at the block level, both
single-line and multi-line. Comments inside fenced code blocks or
inline code spans are preserved verbatim: if you need to *document*
the syntax `<!-- comment -->`, put it inside backticks or a fence.

The table of contents is NOT generated here. If the source document ships
its own TOC (as most handbooks do), it is rendered as plain markdown; the
heading ids produced by `_slugify` match the convention used by common
editors' TOC generators (VS Code Markdown All in One, markdown-toc).

List nesting is driven by leading whitespace. Tabs are expanded to 2
columns; any consistent indentation scheme (2 spaces, 4 spaces, tabs)
produces the correct hierarchy because only relative differences matter.
"""
import html as html_module
import re
import unicodedata


_FENCE_RE        = re.compile(r"^(```|~~~)(.*)$")
_HEADING_RE      = re.compile(r"^(#{1,6})\s+(.*)$")
_HR_RE           = re.compile(r"^\s*([-*_])\s*(\1\s*){2,}$")
_ULIST_ITEM_RE   = re.compile(r"^(\s*)[-*+]\s+(.*)$")
_OLIST_ITEM_RE   = re.compile(r"^(\s*)\d+\.\s+(.*)$")
_INLINE_CODE_RE  = re.compile(r"(`+)(.+?)\1")
_LINK_RE         = re.compile(r"\[([^\]]+)\]\(([^)\s]+)\)")
_BOLD1_RE        = re.compile(r"\*\*(.+?)\*\*")
_BOLD2_RE        = re.compile(r"__(.+?)__")
_ITAL1_RE        = re.compile(r"\*(.+?)\*")
_ITAL2_RE        = re.compile(r"_(.+?)_")
_CODE_RESTORE_RE = re.compile(r"\x00C(\d+)\x00")
_TABLE_SEP_CELL  = re.compile(r"^:?-{3,}:?$")

# URL schemes permitted in rendered links. Everything else (including
# javascript:, data:, vbscript:, file:) is replaced with '#'.
_SAFE_URL_SCHEMES = frozenset((
    "http", "https", "mailto", "tel", "ftp", "ftps",
))
_SCHEME_RE = re.compile(r"^([a-zA-Z][a-zA-Z0-9+.-]*):")

# Used by the HTML-comment stripper to protect inline code spans from
# being mistaken for comment delimiters.
_INLINE_CODE_STRIP_RE = re.compile(r"`+[^`]*`+")
_CODE_SENTINEL_RE     = re.compile(r"\x00S(\d+)\x00")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
def render_markdown(text):
    lines = _strip_html_comments(text.splitlines())
    headings = []  # used only for slug dedup
    out = []
    _render_blocks(lines, out, headings)
    return "\n".join(out)


# ---------------------------------------------------------------------------
# HTML comment stripping
#
# We remove `<!-- ... -->` before block parsing instead of during inline
# rendering. Doing it here means:
#   - multi-line comments are handled as a unit;
#   - a comment on a line of its own disappears without leaving an
#     empty paragraph behind;
#   - text before and after a same-line comment is merged cleanly.
#
# Fenced code blocks and inline code spans are protected: their content
# is copied through unchanged, so `<!-- -->` inside backticks or inside
# a ``` fence is preserved as literal text.
# ---------------------------------------------------------------------------
def _strip_html_comments(lines):
    """Return a new list of lines with HTML comments removed.

    Handles single-line comments, multi-line comments, and comments
    embedded in a line of otherwise normal text. Comments inside
    fenced code blocks or inline code spans are left alone.
    """
    result = []
    in_fence = None
    in_comment = False

    for line in lines:
        # ---- inside a fenced code block: copy verbatim ----
        if in_fence is not None:
            result.append(line)
            if line.startswith(in_fence):
                in_fence = None
            continue

        # ---- fence opener ----
        m = _FENCE_RE.match(line)
        if m:
            in_fence = m.group(1)
            result.append(line)
            continue

        # ---- protect inline code spans from being parsed as comments ----
        spans = []

        def _stash(sm):
            spans.append(sm.group(0))
            return f"\x00S{len(spans) - 1}\x00"

        working = _INLINE_CODE_STRIP_RE.sub(_stash, line)
        had_comment = False

        # ---- we are already inside a multi-line comment ----
        if in_comment:
            idx = working.find("-->")
            if idx == -1:
                continue                       # still inside, drop the line
            working = working[idx + 3:]
            in_comment = False
            had_comment = True

        # ---- strip every complete (or opening) comment on this line ----
        while "<!--" in working:
            before, _, after = working.partition("<!--")
            if "-->" in after:
                _, _, after = after.partition("-->")
                working = before + after
            else:
                # unterminated → comment continues on the next line
                working = before
                in_comment = True
                had_comment = True
                break
            had_comment = True

        # ---- restore inline code spans ----
        if spans:
            working = _CODE_SENTINEL_RE.sub(
                lambda m2: spans[int(m2.group(1))], working)

        # Drop a line that consisted only of a comment. Keep blank lines
        # and whitespace-only lines (they carry paragraph separation).
        if had_comment and not working.strip():
            continue
        result.append(working)

    return result


# ---------------------------------------------------------------------------
# Block-level parsing
# ---------------------------------------------------------------------------
def _render_blocks(lines, out, headings):
    i = 0
    n = len(lines)
    while i < n:
        line = lines[i]

        # ---- fenced code block ----
        m = _FENCE_RE.match(line)
        if m:
            fence = m.group(1)
            lang = m.group(2).strip()
            i += 1
            code_lines = []
            while i < n and not lines[i].startswith(fence):
                code_lines.append(lines[i])
                i += 1
            if i < n:
                i += 1
            cls = (f' class="lang-{html_module.escape(lang, quote=True)}"'
                   if lang else "")
            out.append(f"<pre><code{cls}>"
                       + html_module.escape("\n".join(code_lines))
                       + "</code></pre>")
            continue

        # ---- heading ----
        m = _HEADING_RE.match(line)
        if m:
            level = len(m.group(1))
            raw = m.group(2).strip()
            slug = _unique_slug(_slugify(raw), headings)
            headings.append((level, _strip_inline(raw), slug))
            out.append(f'<h{level} id="{slug}">{_inline(raw)}</h{level}>')
            i += 1
            continue

        # ---- horizontal rule ----
        if _HR_RE.match(line):
            out.append("<hr>")
            i += 1
            continue

        # ---- table ----
        if (_is_table_row(line)
                and i + 1 < n
                and _is_table_sep(lines[i + 1])):
            i = _render_table(lines, i, out)
            continue

        # ---- blockquote ----
        if line.lstrip().startswith(">"):
            quote = []
            while i < n and lines[i].lstrip().startswith(">"):
                quote.append(lines[i].lstrip()[1:].lstrip())
                i += 1
            inner = []
            _render_blocks(quote, inner, [])
            out.append("<blockquote>" + "\n".join(inner) + "</blockquote>")
            continue

        # ---- unordered list (with nesting) ----
        if _ULIST_ITEM_RE.match(line):
            i = _render_list(lines, i, out, ordered=False)
            continue

        # ---- ordered list (with nesting) ----
        if _OLIST_ITEM_RE.match(line):
            i = _render_list(lines, i, out, ordered=True)
            continue

        # ---- blank line ----
        if not line.strip():
            i += 1
            continue

        # ---- paragraph ----
        para = [line]
        i += 1
        while i < n and lines[i].strip() and not _is_block_start(lines[i]):
            if (_is_table_row(lines[i])
                    and i + 1 < n
                    and _is_table_sep(lines[i + 1])):
                break
            para.append(lines[i])
            i += 1
        out.append("<p>" + _inline(" ".join(para)) + "</p>")


# ---------------------------------------------------------------------------
# Lists (with nesting)
# ---------------------------------------------------------------------------
def _render_list(lines, i, out, ordered):
    item_re = _OLIST_ITEM_RE if ordered else _ULIST_ITEM_RE
    tag = "ol" if ordered else "ul"

    items = []
    n = len(lines)
    while i < n:
        m = item_re.match(lines[i])
        if not m:
            break
        indent = len(m.group(1).expandtabs(2))
        items.append((indent, m.group(2)))
        i += 1

    if not items:
        return i

    out.append(_build_list_html(items, tag))
    return i


def _build_list_html(items, tag):
    html = [f"<{tag}>"]
    stack = []

    for indent, text in items:
        content = _inline(text)

        if not stack:
            stack.append(indent)
            html.append(f"<li>{content}")
            continue

        while len(stack) > 1 and indent < stack[-1]:
            html.append(f"</li></{tag}>")
            stack.pop()

        if indent > stack[-1]:
            stack.append(indent)
            html.append(f"<{tag}><li>{content}")
        else:
            html.append(f"</li><li>{content}")

    while stack:
        html.append(f"</li></{tag}>")
        stack.pop()

    return "".join(html)


# ---------------------------------------------------------------------------
# Tables
# ---------------------------------------------------------------------------
def _render_table(lines, i, out):
    header_cells = _split_table_row(lines[i])
    aligns = _parse_alignment(lines[i + 1])
    while len(aligns) < len(header_cells):
        aligns.append(None)
    i += 2

    body_rows = []
    n = len(lines)
    while i < n and lines[i].strip() and _is_table_row(lines[i]):
        body_rows.append(_split_table_row(lines[i]))
        i += 1

    def cell(tag, content, align):
        attr = f' style="text-align:{align}"' if align else ""
        return f"<{tag}{attr}>{content}</{tag}>"

    parts = ["<table>", "<thead><tr>"]
    for idx, cell_text in enumerate(header_cells):
        parts.append(cell("th", _inline(cell_text), aligns[idx]))
    parts.append("</tr></thead>")

    if body_rows:
        parts.append("<tbody>")
        for row in body_rows:
            parts.append("<tr>")
            for idx, cell_text in enumerate(row):
                align = aligns[idx] if idx < len(aligns) else None
                parts.append(cell("td", _inline(cell_text), align))
            parts.append("</tr>")
        parts.append("</tbody>")

    parts.append("</table>")
    out.append("".join(parts))
    return i


def _is_block_start(line):
    return bool(
        _HEADING_RE.match(line)
        or _FENCE_RE.match(line)
        or _HR_RE.match(line)
        or line.lstrip().startswith(">")
        or _ULIST_ITEM_RE.match(line)
        or _OLIST_ITEM_RE.match(line)
    )


# ---------------------------------------------------------------------------
# Table helpers
# ---------------------------------------------------------------------------
def _is_table_row(line):
    """A line is a table-row candidate if it contains at least one pipe.

    GFM allows tables without outer pipes ('a | b'), so we do not
    require a leading or trailing '|'. The actual 'is this a table'
    decision is made by _is_table_sep() on the following line.
    """
    return "|" in line


def _is_table_sep(line):
    s = line.strip()
    if "|" not in s:
        return False
    inner = s.strip("|").strip()
    if not inner:
        return False
    for cell in inner.split("|"):
        if not _TABLE_SEP_CELL.match(cell.strip()):
            return False
    return True


def _split_table_row(line):
    s = line.strip()
    if s.startswith("|"):
        s = s[1:]
    if s.endswith("|"):
        s = s[:-1]
    return [c.strip() for c in s.split("|")]


def _parse_alignment(sep_line):
    aligns = []
    for cell in _split_table_row(sep_line):
        c = cell.strip()
        left = c.startswith(":")
        right = c.endswith(":")
        if left and right:
            aligns.append("center")
        elif right:
            aligns.append("right")
        elif left:
            aligns.append("left")
        else:
            aligns.append(None)
    return aligns


# ---------------------------------------------------------------------------
# Heading anchors
#
# The slug format matches the observed output of common TOC generators
# (VS Code Markdown All in One, markdown-toc):
#   - backticks and '*' stripped
#   - lowercase
#   - NFKD-folded to ASCII
#   - every char outside [a-z0-9 _-] removed
#   - spaces become '-' (consecutive dashes are NOT collapsed)
#   - leading/trailing dashes are kept
#   - duplicates get -1, -2, … appended
# ---------------------------------------------------------------------------
def _slugify(text):
    text = re.sub(r"[`*]", "", text)
    text = text.lower()
    text = unicodedata.normalize("NFKD", text)
    text = text.encode("ascii", "ignore").decode("ascii")
    text = re.sub(r"[^a-z0-9 _-]", "", text)
    text = text.replace(" ", "-")
    return text or "section"


def _unique_slug(base, headings):
    used = {h[2] for h in headings}
    if base not in used:
        return base
    i = 1
    while f"{base}-{i}" in used:
        i += 1
    return f"{base}-{i}"


def _strip_inline(text):
    text = re.sub(r"`+([^`]+)`+", r"\1", text)
    text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)
    text = re.sub(r"__(.+?)__", r"\1", text)
    text = re.sub(r"\*(.+?)\*", r"\1", text)
    text = re.sub(r"_(.+?)_", r"\1", text)
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    return text


# ---------------------------------------------------------------------------
# Inline formatting
# ---------------------------------------------------------------------------
def _safe_href(url):
    """Return `url` if it uses a whitelisted scheme (or none), else '#'.

    A "scheme" is anything matching the RFC 3986 pattern
    `[a-zA-Z][a-zA-Z0-9+.-]*:` before any '/' or '?'. Relative URLs and
    fragment-only links (no scheme) pass through untouched.
    """
    m = _SCHEME_RE.match(url)
    if m and m.group(1).lower() not in _SAFE_URL_SCHEMES:
        return "#"
    return url


def _inline(text):
    # quote=True (default) escapes '"' and "'" so that a link URL
    # containing a double quote cannot break out of the href attribute.
    text = html_module.escape(text, quote=True)

    code_spans = []

    def _stash(m):
        code_spans.append(m.group(2))
        return f"\x00C{len(code_spans) - 1}\x00"

    text = _INLINE_CODE_RE.sub(_stash, text)
    text = _LINK_RE.sub(
        lambda m: (f'<a href="{_safe_href(m.group(2))}" '
                   f'rel="noopener">{m.group(1)}</a>'),
        text,
    )
    text = _BOLD1_RE.sub(r"<strong>\1</strong>", text)
    text = _BOLD2_RE.sub(r"<strong>\1</strong>", text)
    text = _ITAL1_RE.sub(r"<em>\1</em>", text)
    text = _ITAL2_RE.sub(r"<em>\1</em>", text)

    def _restore(m):
        return f"<code>{code_spans[int(m.group(1))]}</code>"

    text = _CODE_RESTORE_RE.sub(_restore, text)
    return text