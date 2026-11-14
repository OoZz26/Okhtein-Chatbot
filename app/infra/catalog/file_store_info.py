"""StoreInfoSource adapter: reads the knowledge file and re-reads it whenever the file changes."""

from pathlib import Path


class FileStoreInfoSource:
    def __init__(self, path: Path) -> None:
        self._path = path
        self._cached_mtime: float | None = None
        self._cached_text = ""

    def get_knowledge(self) -> str:
        """Cheap on every call (one stat); edits to the file show up on the next message, no restart."""
        if not self._path.exists():
            return ""
        mtime = self._path.stat().st_mtime
        if mtime != self._cached_mtime:
            self._cached_text = self._path.read_text(encoding="utf-8")
            self._cached_mtime = mtime
        return self._cached_text
