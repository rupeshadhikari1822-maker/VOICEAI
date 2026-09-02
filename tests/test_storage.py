"""Storage adapter and, more importantly, the key layout.

The key layout is a privacy control: if a name ever ends up in an object key it
is effectively published to anyone with bucket access, and it is baked into
every backup from that moment on.
"""

from __future__ import annotations

import pytest

from app.core.config import get_settings
from app.services.storage import (
    LocalStorage,
    StorageError,
    consent_key,
    derived_key,
    raw_key,
)


@pytest.fixture
def storage() -> LocalStorage:
    return LocalStorage(get_settings())


def test_key_layout_is_stable():
    assert raw_key("ne", "01SPK", "01SES", "01CLIP") == "raw/ne/01SPK/01SES/01CLIP.wav"
    assert derived_key("16k", "ne", "01SPK", "01CLIP") == "derived/16k/ne/01SPK/01CLIP.wav"
    assert consent_key("01SPK", "v1") == "consent/01SPK/consent_v1.wav"


def test_keys_contain_only_the_opaque_id():
    """Whatever else changes, PII must never reach a key."""
    key = raw_key("ne", "01SPEAKERULID", "01SESSION", "01CLIP")
    for pii in ("Ram Bahadur", "ram@example.com", "+9779800000000", "Chhetri"):
        assert pii not in key


def test_round_trip(storage):
    storage.put_bytes("raw/ne/X/Y/Z.wav", b"hello")
    assert storage.get_bytes("raw/ne/X/Y/Z.wav") == b"hello"
    assert storage.exists("raw/ne/X/Y/Z.wav")
    storage.delete("raw/ne/X/Y/Z.wav")
    assert not storage.exists("raw/ne/X/Y/Z.wav")


def test_missing_object_raises_storage_error(storage):
    with pytest.raises(StorageError):
        storage.get_bytes("raw/ne/nope/nope/nope.wav")


def test_path_traversal_refused(storage):
    for evil in ("../../etc/passwd", "/etc/passwd", "raw/../../secrets"):
        with pytest.raises(StorageError):
            storage.get_bytes(evil)


def test_delete_prefix_removes_a_subtree(storage):
    for i in range(3):
        storage.put_bytes(f"raw/ne/SPK/SES/{i}.wav", b"x")
    assert storage.delete_prefix("raw/ne/SPK/") == 3
    assert not storage.exists("raw/ne/SPK/SES/0.wav")


def test_presigned_put_is_signed_and_expiring(storage):
    target = storage.presign_put("raw/ne/A/B/C.wav")
    assert target.method == "PUT"
    assert "sig=" in target.url and "expires=" in target.url
    assert target.headers["Content-Type"] == "audio/wav"

    assert storage.verify("raw/ne/A/B/C.wav", target.expires_at,
                          storage.sign("raw/ne/A/B/C.wav", target.expires_at))
    # Wrong signature, and an expired-but-correctly-signed URL, both fail.
    assert not storage.verify("raw/ne/A/B/C.wav", target.expires_at, "deadbeef")
    assert not storage.verify("raw/ne/A/B/C.wav", 1, storage.sign("raw/ne/A/B/C.wav", 1))


def test_signature_is_bound_to_the_key(storage):
    """A signature for one key must not authorise writing another."""
    target = storage.presign_put("raw/ne/A/B/C.wav")
    sig = storage.sign("raw/ne/A/B/C.wav", target.expires_at)
    assert not storage.verify("raw/ne/OTHER/B/C.wav", target.expires_at, sig)
