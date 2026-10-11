# file: macula/__init__.py

"""macula — a small, zero-dependency file server for pentesting."""
import secrets

__version__ = "0.2.0"

# ===========================================================================
# MAGIC CONSTANTS — everything tunable lives here. Change once, done.
# ===========================================================================

# ------------------------------------------------------------------ Project
REPO_URL = "https://github.com/F0xh0le/Macula"

# ------------------------------------------------------------------ Networking
DEFAULT_PORT       = 8000
DEFAULT_BIND       = "127.0.0.1"
DEFAULT_MAX_UPLOAD = "2G"

# -------------------------------------------------------------------- Listing
VALID_FORMATS      = ("html", "json", "text")

# ------------------------------------------------------ Endpoint URL suffixes
# Internal endpoints live under /{token}/<suffix>; token is per-run random.
UPLOAD_SUFFIX    = "upload"
SOURCE_SUFFIX    = "source"
HANDBOOK_SUFFIX  = "handbook.md"
CLIPBOARD_SUFFIX = "clipboard"

# Filename on disk for the operational handbook served at
# /{token}/handbook.md.
HANDBOOK_FILE = "HANDBOOK.md"

# ---------------------------------------------------------------- Units
# Binary size units (1 KB = 1024 B). `MB` is a mebibyte, matching the
# interpretation used by --max-upload-size and --clipboard-max-mb.
KB = 1024
MB = 1024 * 1024
GB = 1024 * 1024 * 1024

# ------------------------------------------------------- Shared clipboard
# Overridable via CLI flags (--no-clipboard, --clipboard-max-rooms, ...)
CLIPBOARD_ENABLED         = True      # toggled by --no-clipboard
CLIPBOARD_MAX_ROOMS       = 200       # max number of rooms kept
CLIPBOARD_MAX_MB_PER_ROOM = 1         # max MB per room text
CLIPBOARD_MAX_TOTAL_MB    = 20        # max MB across all rooms

# Frontend timings (milliseconds)
CLIPBOARD_POLL_MS     = 3000          # how often to poll list / selected room
CLIPBOARD_AUTOSAVE_MS = 1500          # debounce before autosaving the active room

# ===========================================================================


def make_token():
    """8 hex chars — URL-safe, unpredictable, per-run."""
    return secrets.token_hex(4)


def make_upload_endpoint(token):
    return f"/{token}/{UPLOAD_SUFFIX}"


def make_source_endpoint(token):
    return f"/{token}/{SOURCE_SUFFIX}"


def make_handbook_endpoint(token):
    return f"/{token}/{HANDBOOK_SUFFIX}"


def make_clipboard_endpoint(token):
    return f"/{token}/{CLIPBOARD_SUFFIX}"