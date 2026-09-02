"""ULIDs, without a dependency.

Speaker and clip identifiers are the only things that leave this system, so they
must carry no personal information. A ULID is opaque, sorts by creation time,
and is safe to put in an object key or a published dataset.
"""

from __future__ import annotations

import os
import time

# Crockford base32: no I, L, O or U, so the ids survive being read aloud.
_ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"


def _encode(value: int, length: int) -> str:
    out = [""] * length
    for i in range(length - 1, -1, -1):
        out[i] = _ALPHABET[value & 0x1F]
        value >>= 5
    return "".join(out)


def new_ulid() -> str:
    """26-character ULID: 48-bit millisecond timestamp + 80 bits of entropy."""
    timestamp = int(time.time() * 1000) & ((1 << 48) - 1)
    randomness = int.from_bytes(os.urandom(10), "big")
    return _encode(timestamp, 10) + _encode(randomness, 16)


def is_ulid(value: str) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 26
        and all(c in _ALPHABET for c in value.upper())
    )
