"""Consent text loading and hashing.

We store the SHA-256 of the exact text a speaker agreed to, alongside the
version string. That is what makes the consent record evidence rather than a
boolean: if the wording is ever changed, old records still point at the old
hash and the change is visible.
"""

from __future__ import annotations

import hashlib
from functools import lru_cache

from app.config import get_settings

_CONSENT_FILE = "docs/consent-ne.md"

_FALLBACK = """\
# सहमति

म स्वेच्छाले यो आवाज संकलनमा सहभागी हुन सहमत छु।
(docs/consent-ne.md फेला परेन — यो अस्थायी पाठ हो।)
"""


@lru_cache(maxsize=1)
def consent_text() -> str:
    path = get_settings().base_dir / _CONSENT_FILE
    if path.is_file():
        return path.read_text(encoding="utf-8")
    return _FALLBACK


def consent_sha256() -> str:
    return hashlib.sha256(consent_text().encode("utf-8")).hexdigest()


def consent_payload() -> dict:
    return {
        "version": get_settings().consent_version,
        "text": consent_text(),
        "sha256": consent_sha256(),
    }
