# file: macula/utils.py

"""Small helpers shared across macula."""
import fnmatch
import ipaddress
import os
import re
import shutil
import subprocess
from urllib.parse import quote as url_quote


def is_ipv4(value):
    try:
        ipaddress.IPv4Address(value); return True
    except ValueError:
        return False


def get_interface_ip(interface):
    patterns = [
        ("ip", ["ip", "-4", "addr", "show", interface],
         r"inet\s+(\d+\.\d+\.\d+\.\d+)"),
        ("ifconfig", ["ifconfig", interface],
         r"inet\s+(?:addr:)?(\d+\.\d+\.\d+\.\d+)"),
    ]
    for tool, argv, regex in patterns:
        if not shutil.which(tool):
            continue
        try:
            output = subprocess.check_output(argv, text=True,
                                             stderr=subprocess.DEVNULL)
        except (subprocess.CalledProcessError, FileNotFoundError):
            continue
        match = re.search(regex, output)
        if match:
            return match.group(1)
    return None


def parse_size(value):
    if value is None:
        return None
    s = str(value).strip().upper()
    if s in ("0", "OFF", "NONE", "UNLIMITED"):
        return 0
    m = re.match(r"^(\d+(?:\.\d+)?)\s*([KMGTP]?)B?$", s)
    if not m:
        return None
    mult = {"": 1, "K": 1024, "M": 1024 ** 2,
            "G": 1024 ** 3, "T": 1024 ** 4, "P": 1024 ** 5}[m.group(2)]
    return int(float(m.group(1)) * mult)


def human_size(size):
    """Format a byte count as B/K/M/G/T/P.

    Zero decimals up to G, one decimal for T and P. Negative inputs
    are clamped to 0. See HANDBOOK.md → Design choices → human_size.
    """
    if size < 0:
        size = 0
    for unit in ["B", "K", "M", "G"]:
        if size < 1024:
            return f"{size:.0f}{unit}"
        size /= 1024
    if size < 1024:
        return f"{size:.1f}T"
    size /= 1024
    return f"{size:.1f}P"


def safe_filename(name):
    """Sanitize a single path segment.

    Keeps only [A-Za-z0-9._-], collapses runs of disallowed chars to '_',
    then strips leading/trailing dots and underscores. Empty results (or
    dot-only) map to 'download'.
    """
    name = re.sub(r"[^A-Za-z0-9._-]+", "_", str(name or ""))
    name = name.strip("._")
    if not name:
        return "download"
    return name


def url_quote_path(path):
    return "/".join(url_quote(seg) for seg in path.split("/"))


def matches_filter(filename, filters):
    if not filters:
        return True
    filename_lower = filename.lower()
    for f in filters:
        f_lower = f.lower()
        if '*' in f_lower or '?' in f_lower:
            if fnmatch.fnmatch(filename_lower, f_lower):
                return True
        else:
            if f_lower in filename_lower:
                return True
    return False


def is_safe_entry(entry, share_root):
    if share_root is None:
        return True
    if not entry.is_symlink():
        return True
    try:
        entry.resolve().relative_to(share_root); return True
    except (ValueError, OSError, RuntimeError):
        return False


def fmt_depth(depth, lazy_label=False):
    if depth is None:
        return "unlimited"
    if lazy_label and depth == 0:
        return "load on click"
    return str(depth)


def fmt_filters(filters):
    return ", ".join(filters) if filters else "none"


def fmt_max_upload(size):
    if size == 0:
        return "unlimited"
    return human_size(size)


def count_upload_files(upload_path):
    if upload_path is None:
        return 0
    n = 0
    try:
        for _r, _d, files in os.walk(upload_path):
            n += len(files)
    except OSError:
        pass
    return n