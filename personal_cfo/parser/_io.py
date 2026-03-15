"""File I/O with encoding fallback."""

from pathlib import Path


def _try_read(path):
    """Read file trying common encodings."""
    for enc in ("utf-8-sig", "utf-8", "big5", "cp950"):
        try:
            return Path(path).read_text(encoding=enc)
        except (UnicodeDecodeError, UnicodeError):
            continue
    raise ValueError(f"Cannot decode file: {Path(path).name}")
