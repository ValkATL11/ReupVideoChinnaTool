# src/reup_tool/utils.py
"""Small I/O helpers used across the backend."""
from pathlib import Path
from typing import Optional


def read_text_file(file_path: Path, encodings: Optional[list] = None) -> str:
    """Read a text file with automatic encoding detection fallback.

    Tries the most common encodings in order:
      utf-8-sig  -> handles UTF-8 with BOM
      utf-8      -> modern default
      cp1252     -> Windows Western / Vietnamese mixed encoding
      gbk        -> Chinese subtitles
      latin-1    -> always succeeds, last resort
    """
    if encodings is None:
        encodings = ["utf-8-sig", "utf-8", "cp1252", "gbk", "latin-1"]

    for enc in encodings:
        try:
            with open(file_path, "r", encoding=enc) as f:
                return f.read()
        except (UnicodeDecodeError, UnicodeError):
            continue

    # Fallback: latin-1 never raises, but may produce mojibake
    with open(file_path, "r", encoding="latin-1") as f:
        return f.read()
