"""Consent text loading and hashing.

We store the SHA-256 of the exact text a speaker agreed to, alongside the
version string. That is what makes the consent record evidence rather than a
boolean: if the wording is ever changed, old records still point at the old
hash and the change is visible.

**A missing consent file is a hard failure, not a fallback.**

This module used to return built-in placeholder text when
`docs/consent-ne.md` was absent. That meant a deleted or mis-deployed consent
file did not stop the app: it kept collecting, hashed the placeholder, and
stored that hash as though it were the real thing. Every speaker recorded in
that window would have "consented" to text nobody chose to show them, and
nothing anywhere would have surfaced it.

That is the same shape as an unguarded production config -- a wrong state that
looks exactly like a working one -- except in the one area with no remedy after
the fact. You cannot go back and re-obtain consent for audio you already hold.

So the file must be present. `ALLOW_MISSING_CONSENT_TEXT=true` exists for local
development on a fork that has not written its consent text yet, and the
production guard refuses that flag outright.
"""

from __future__ import annotations

import hashlib
from functools import lru_cache

from app.core.config import get_settings

CONSENT_FILE = "docs/consent-ne.md"

# Used only when ALLOW_MISSING_CONSENT_TEXT is explicitly set. Never a default.
_DEV_PLACEHOLDER = """\
# सहमति (PLACEHOLDER — NOT FOR COLLECTION)

म स्वेच्छाले यो आवाज संकलनमा सहभागी हुन सहमत छु।

ALLOW_MISSING_CONSENT_TEXT is set. This is placeholder text for local
development only. Any consent record created against it is worthless.
"""


class ConsentTextMissing(RuntimeError):
    """`docs/consent-ne.md` is not where the loader expects it."""


@lru_cache(maxsize=1)
def consent_text() -> str:
    settings = get_settings()
    path = settings.base_dir / CONSENT_FILE

    if path.is_file():
        return path.read_text(encoding="utf-8")

    if settings.allow_missing_consent_text:
        return _DEV_PLACEHOLDER

    raise ConsentTextMissing(
        "\n\n"
        f"refusing to start: consent text not found at {path}\n\n"
        "  Every speaker record stores the SHA-256 of the exact consent text\n"
        "  they were shown. Without the file there is nothing to hash, and\n"
        "  collecting anyway would produce consent records that point at text\n"
        "  nobody chose to display. That cannot be repaired afterwards.\n\n"
        "  If the file exists in the repository, this is a deployment problem:\n"
        "  check that docs/ was included in the deploy.\n\n"
        "  For local development on a fork with no consent text yet, set\n"
        "  ALLOW_MISSING_CONSENT_TEXT=true. Production refuses that flag.\n"
    )


def verify_consent_available() -> None:
    """Boot-time check. Called from the app lifespan.

    Loading is lazy and cached, so without this the failure would arrive on the
    first contributor's request rather than at startup -- which is exactly the
    wrong moment to discover it.
    """
    consent_text()


def consent_sha256() -> str:
    return hashlib.sha256(consent_text().encode("utf-8")).hexdigest()


def consent_payload() -> dict:
    return {
        "version": get_settings().consent_version,
        "text": consent_text(),
        "sha256": consent_sha256(),
    }
