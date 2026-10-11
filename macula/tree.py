# file: macula/tree.py

"""Directory tree building, pruning, traversal, and fingerprinting."""
import hashlib
from pathlib import Path

from .utils import human_size, matches_filter, is_safe_entry


# ---------------------------------------------------------------------------
# Tree building
# ---------------------------------------------------------------------------
def build_tree(directory, filters=None, max_depth=None, current_depth=0,
               name=None, rel_path="", share_root=None):
    directory = Path(directory).resolve()
    node = {
        "name": name if name is not None else directory.name,
        "type": "dir", "path": "", "rel_path": rel_path,
        "dirs": [], "files": [],
    }
    try:
        entries = sorted(directory.iterdir(), key=lambda p: p.name.lower())
    except OSError:
        return node
    recurse = (max_depth is None or current_depth < max_depth)
    for entry in entries:
        if not entry.is_dir():
            continue
        if not is_safe_entry(entry, share_root):
            continue
        child_rel = (rel_path + entry.name + "/") if rel_path else (entry.name + "/")
        if recurse:
            child = build_tree(entry, filters, max_depth, current_depth + 1,
                               name=entry.name, rel_path=child_rel,
                               share_root=share_root)
        else:
            child = {
                "name": entry.name, "type": "dir",
                "path": entry.name + "/", "rel_path": child_rel,
                "dirs": [], "files": [],
            }
        child["path"] = entry.name + "/"
        node["dirs"].append(child)
    for entry in entries:
        if not entry.is_file():
            continue
        if not is_safe_entry(entry, share_root):
            continue
        if not matches_filter(entry.name, filters):
            continue
        try:
            st = entry.stat()
        except OSError:
            continue
        file_rel = (rel_path + entry.name) if rel_path else entry.name
        node["files"].append({
            "name": entry.name, "type": "file",
            "path": entry.name, "rel_path": file_rel,
            "size": st.st_size, "mtime": st.st_mtime_ns,
            "size_human": human_size(st.st_size),
        })
    return node


def prune_empty_dirs(node):
    node["dirs"] = [d for d in node["dirs"] if prune_empty_dirs(d)]
    return bool(node["dirs"] or node["files"])


def truncate_tree(node, max_depth, current_depth=0):
    if max_depth is None:
        return
    if current_depth >= max_depth:
        for d in node.get("dirs", []):
            d["dirs"] = []; d["files"] = []
        return
    for d in node.get("dirs", []):
        truncate_tree(d, max_depth, current_depth + 1)


def build_listing_tree(directory, filters, display_depth, share_root=None):
    scan_depth = None if filters else display_depth
    tree = build_tree(directory, filters, scan_depth, share_root=share_root)
    if filters:
        prune_empty_dirs(tree)
        if scan_depth is None and display_depth is not None:
            truncate_tree(tree, display_depth)
    return tree


def build_listing_tree_full(directory, filters, share_root=None):
    """Build the tree without any depth cut. Caller may truncate afterwards."""
    tree = build_tree(directory, filters, None, share_root=share_root)
    if filters:
        prune_empty_dirs(tree)
    return tree


def _prefix_rel_paths(node, prefix):
    """Prepend `prefix` to every rel_path in node's descendants (in-place)."""
    for d in node.get("dirs", []):
        d["rel_path"] = prefix + d["rel_path"]
        _prefix_rel_paths(d, prefix)
    for f in node.get("files", []):
        f["rel_path"] = prefix + f["rel_path"]


def build_virtual_root_tree(mounts, filters, display_depth):
    node = {
        "name": "/", "type": "dir", "path": "", "rel_path": "",
        "dirs": [], "files": [],
    }
    for m in mounts:
        sub = build_listing_tree(m["root"], filters, display_depth,
                                 share_root=m["root"])
        sub["name"] = m.get("display") or m["name"]
        sub["path"] = m["name"] + "/"
        sub["rel_path"] = m["name"] + "/"
        sub["is_mount"] = True
        if m.get("is_upload"):
            sub["is_upload"] = True
        _prefix_rel_paths(sub, m["name"] + "/")
        node["dirs"].append(sub)
    return node


def count_tree(node):
    nd = len(node.get("dirs", []))
    nf = len(node.get("files", []))
    for d in node.get("dirs", []):
        cd, cf = count_tree(d)
        nd += cd; nf += cf
    return nd, nf


# ---------------------------------------------------------------------------
# Fingerprints
#
# There is exactly ONE fingerprint algorithm: fingerprint_from_tree. It is
# used by both the HTML renderer (to seed the client) and the ?stat=1
# endpoint (to check for changes). This guarantees that, given the same
# disk state, the two values match.
#
# Key format (newline-separated, UTF-8, replace-on-error):
#   D:<rel_path>\n                              for each directory
#   F:<rel_path>:<size>:<mtime_ns>\n            for each file
#
# <rel_path> is relative to the tree root, forward slashes, no leading or
# trailing slash. Nanosecond mtime is used so two writes within the same
# second still produce different fingerprints.
# ---------------------------------------------------------------------------
def _hash_tree_into(h, node):
    for d in node.get("dirs", []):
        rp = d.get("rel_path", "").rstrip("/")
        h.update(f"D:{rp}\n".encode("utf-8", "replace"))
        _hash_tree_into(h, d)
    for f in node.get("files", []):
        h.update(
            f"F:{f.get('rel_path', '')}:{f.get('size', 0)}:"
            f"{f.get('mtime', 0)}\n".encode("utf-8", "replace")
        )


def fingerprint_from_tree(node):
    """SHA1 over an in-memory tree (must contain 'mtime' on every file)."""
    h = hashlib.sha1()
    _hash_tree_into(h, node)
    return h.hexdigest()


def file_fingerprint(path):
    """SHA1 over (size, mtime_ns) for a single file.

    Used by ?stat=1 on a file path. A single file has no subtree to walk,
    so this is trivially cheap and does not go through fingerprint_from_tree.
    """
    try:
        st = Path(path).stat()
    except OSError:
        return "0" * 40
    return hashlib.sha1(
        f"{st.st_size}:{st.st_mtime_ns}".encode()
    ).hexdigest()


# ---------------------------------------------------------------------------
# Combined build + fingerprint (single disk pass)
# ---------------------------------------------------------------------------
def build_listing_tree_and_fp(directory, filters, display_depth,
                              share_root=None):
    """Build the full tree, compute its fingerprint, then truncate.

    Returns (tree, fingerprint). The fingerprint covers the full subtree
    even when display_depth cuts the rendered tree short, so the value is
    stable across ?depth=N query strings.
    """
    tree = build_listing_tree_full(directory, filters, share_root=share_root)
    fp = fingerprint_from_tree(tree)
    if display_depth is not None:
        truncate_tree(tree, display_depth)
    return tree, fp


def build_virtual_root_tree_and_fp(mounts, filters, display_depth):
    """Same as above, but across all mounts. Returns (root_node, fingerprint).

    The fingerprint is over the concatenation of per-mount subtree
    fingerprints, keyed by mount name. Both the HTML renderer and the
    ?stat=1 endpoint call this with the same arguments, so the two values
    match for identical disk state.
    """
    node = {
        "name": "/", "type": "dir", "path": "", "rel_path": "",
        "dirs": [], "files": [],
    }
    h = hashlib.sha1()
    for m in mounts:
        sub = build_listing_tree_full(m["root"], filters, share_root=m["root"])
        sub["name"] = m.get("display") or m["name"]
        sub["path"] = m["name"] + "/"
        sub["rel_path"] = m["name"] + "/"
        sub["is_mount"] = True
        if m.get("is_upload"):
            sub["is_upload"] = True
        _prefix_rel_paths(sub, m["name"] + "/")

        # Hash the full mount subtree before truncation, namespaced by mount.
        h.update(m["name"].encode("utf-8", "replace"))
        h.update(b"\0")
        h.update(fingerprint_from_tree(sub).encode())
        h.update(b"\n")

        if display_depth is not None:
            truncate_tree(sub, display_depth)
        node["dirs"].append(sub)
    return node, h.hexdigest()