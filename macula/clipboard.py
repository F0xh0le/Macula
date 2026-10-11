# file: macula/clipboard.py

"""In-memory shared clipboard for macula.

Each clipboard entry is a "room": a single text buffer identified by an
integer id. Multiple clients can read, edit, clear, or delete the same
room; changes are visible to everyone.

Thread-safe. Evicts the oldest rooms when either the room count or the
total byte budget exceeds the configured limits.

Not persisted: everything is lost when the process exits.
"""
import re
import threading
import time

from . import (CLIPBOARD_MAX_MB_PER_ROOM, CLIPBOARD_MAX_ROOMS,
               CLIPBOARD_MAX_TOTAL_MB, MB)


def _preview(text, limit=60):
    """First line of `text`, truncated to `limit` chars.

    Slices at most `limit * 4` characters before stripping so we never
    duplicate a multi-megabyte single-line text just to compute a preview.
    """
    nl = text.find("\n")
    end = nl if nl != -1 else len(text)
    scan = text[:min(end, limit * 4)].strip()
    if len(scan) > limit:
        scan = scan[:limit] + "…"
    return scan


class ClipboardStore:
    def __init__(self,
                 max_rooms=CLIPBOARD_MAX_ROOMS,
                 max_bytes_per_room=CLIPBOARD_MAX_MB_PER_ROOM * MB,
                 max_total_bytes=CLIPBOARD_MAX_TOTAL_MB * MB):
        self._lock = threading.Lock()
        self._rooms = {}            # id -> {id, text, size, ts}
        self._next_id = 1
        self.max_rooms = max_rooms
        self.max_bytes_per_room = max_bytes_per_room
        self.max_total_bytes = max_total_bytes

    # ------------------------------------------------------------------ write
    def create_room(self, text=""):
        raw = text.encode("utf-8", "replace")
        if len(raw) > self.max_bytes_per_room:
            raise ValueError(
                f"room too large: {len(raw)} bytes "
                f"(max {self.max_bytes_per_room})"
            )
        with self._lock:
            rid = self._next_id
            self._next_id += 1
            self._rooms[rid] = {
                "id": rid,
                "text": text,
                "size": len(raw),
                "ts": time.time(),
            }
            self._evict_locked()
            return rid

    def update_room(self, rid, text):
        raw = text.encode("utf-8", "replace")
        if len(raw) > self.max_bytes_per_room:
            raise ValueError(
                f"room too large: {len(raw)} bytes "
                f"(max {self.max_bytes_per_room})"
            )
        with self._lock:
            room = self._rooms.get(rid)
            if room is None:
                return False
            room["text"] = text
            room["size"] = len(raw)
            room["ts"] = time.time()
            self._evict_locked()
            return True

    def clear_room(self, rid):
        with self._lock:
            room = self._rooms.get(rid)
            if room is None:
                return False
            room["text"] = ""
            room["size"] = 0
            room["ts"] = time.time()
            return True

    def delete_room(self, rid):
        with self._lock:
            return self._rooms.pop(rid, None) is not None

    def clear_all(self):
        with self._lock:
            self._rooms.clear()

    # ------------------------------------------------------------------- read
    def list_rooms(self):
        """Metadata only — newest first."""
        with self._lock:
            rooms = [
                {"id": r["id"], "size": r["size"], "ts": r["ts"],
                 "preview": _preview(r["text"])}
                for r in self._rooms.values()
            ]
        rooms.sort(key=lambda x: -x["ts"])
        return rooms

    def get_room(self, rid):
        with self._lock:
            r = self._rooms.get(rid)
            return dict(r) if r else None

    def count(self):
        with self._lock:
            return len(self._rooms)

    # ----------------------------------------------------------------- search
    def search(self, query, use_regex=False):
        """Return the set of room ids whose text matches `query`.

        Returns None when `query` is empty (no filter — caller should
        return everything). Returns an empty set when the regex doesn't
        compile.
        """
        if not query:
            return None
        with self._lock:
            snapshot = [(r["id"], r["text"]) for r in self._rooms.values()]
        if use_regex:
            try:
                rx = re.compile(query, re.IGNORECASE)
            except re.error:
                return set()
        else:
            rx = re.compile(re.escape(query), re.IGNORECASE)
        return {rid for rid, text in snapshot if rx.search(text)}

    # ---------------------------------------------------------------- helpers
    def _evict_locked(self):
        total = sum(r["size"] for r in self._rooms.values())
        while self._rooms and (
            len(self._rooms) > self.max_rooms
            or total > self.max_total_bytes
        ):
            oldest = min(self._rooms.values(), key=lambda r: r["ts"])
            del self._rooms[oldest["id"]]
            total -= oldest["size"]