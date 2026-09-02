"""Object key layout.

Keys carry only the opaque speaker ULID -- never a name, email or phone. Keeping
the naming in one module means there is exactly one place to audit that claim.

    raw/     the 48 kHz master. Immutable, kept forever.
    derived/ resampled training sets, regenerable from raw.
    consent/ spoken consent, kept apart from the corpus.
"""

from __future__ import annotations


def raw_key(lang: str, speaker_id: str, session_id: str, clip_id: str) -> str:
    return f"raw/{lang}/{speaker_id}/{session_id}/{clip_id}.wav"


def derived_key(sr_khz: str, lang: str, speaker_id: str, clip_id: str) -> str:
    return f"derived/{sr_khz}/{lang}/{speaker_id}/{clip_id}.wav"


def consent_key(speaker_id: str, version: str) -> str:
    return f"consent/{speaker_id}/consent_{version}.wav"
