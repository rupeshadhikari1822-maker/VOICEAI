"""Make stdout safe for Devanagari.

Windows consoles still default to a legacy code page (cp1252 on most machines),
so printing Nepali raises UnicodeEncodeError. Every script here prints prompt
text or QC reasons, all of which are Nepali-first, so they all need this.

Call `use_utf8()` once at the top of a script's main().
"""

from __future__ import annotations

import sys


def use_utf8() -> None:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue
        try:
            # errors="replace" so an exotic glyph degrades to '?' instead of
            # killing a long-running export halfway through.
            reconfigure(encoding="utf-8", errors="replace")
        except (ValueError, OSError):
            pass
