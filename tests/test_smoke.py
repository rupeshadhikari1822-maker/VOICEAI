"""End-to-end flow, privacy guarantees, and split discipline.

These are the checks that catch a corpus being quietly ruined rather than the
server crashing: PII reaching an export, the client being able to talk its way
past QC, or one speaker appearing in both train and test.
"""

from __future__ import annotations

from urllib.parse import urlparse

import pytest

from app.core.db import SessionLocal
from app.models import Clip, Speaker
from scripts.export_dataset import assign_splits
from tests.synth import clean_take, noisy_take

# Planted deliberately so the tests can prove these values never come back out.
PII = {
    "name": "Test Contributor",
    "email": "contributor@example.com",
    "phone": "+9779800000000",
    "caste_ethnicity": "SENSITIVE-VALUE",
}


def make_speaker(client, consent_version, **overrides):
    payload = {
        **PII,
        "province": "बागमती",
        "district": "काठमाडौं",
        "mother_tongue": "नेपाली",
        "age_band": "25-34",
        "gender": "female",
        "consent": {
            "version": consent_version,
            "accepted": True,
            "commercial_use": True,
        },
        **overrides,
    }
    res = client.post("/api/speakers", json=payload)
    assert res.status_code == 201, res.text
    return res.json()["speaker_id"]


def upload(client, url: str, wav: bytes):
    """PUT through the presigned URL exactly as the browser does."""
    parsed = urlparse(url)
    return client.put(
        f"{parsed.path}?{parsed.query}",
        content=wav,
        headers={"Content-Type": "audio/wav"},
    )


# --- config -------------------------------------------------------------


def test_config_advertises_lossless_capture(client):
    audio = client.get("/api/config").json()["audio"]
    assert audio["sample_rate"] == 48000
    assert audio["bit_depth"] == 16
    assert audio["channels"] == 1


def test_consent_text_is_served_with_a_matching_hash(client):
    import hashlib

    consent = client.get("/api/config").json()["consent"]
    assert hashlib.sha256(consent["text"].encode()).hexdigest() == consent["sha256"]
    assert len(consent["text"]) > 1000, "should be the real doc, not the fallback"


# --- consent gate -------------------------------------------------------


def test_recording_without_consent_is_refused(client, consent_version):
    res = client.post(
        "/api/speakers",
        json={"consent": {"version": consent_version, "accepted": False}},
    )
    assert res.status_code == 400


def test_stale_consent_version_is_refused(client):
    res = client.post(
        "/api/speakers",
        json={"consent": {"version": "1999-01-01-v0", "accepted": True}},
    )
    assert res.status_code == 409


def test_commercial_assignment_consent_is_required(client, consent_version):
    res = client.post(
        "/api/speakers",
        json={
            "consent": {
                "version": consent_version,
                "accepted": True,
                "commercial_use": False,
            }
        },
    )
    assert res.status_code == 400


# --- the upload flow ----------------------------------------------------


def test_full_flow_and_server_side_qc_authority(client, consent_version, prompts):
    speaker_id = make_speaker(client, consent_version)
    session_id = client.post(
        "/api/sessions", json={"speaker_id": speaker_id, "lang": "ne"}
    ).json()["session_id"]

    available = client.get(f"/api/prompts?session_id={session_id}").json()
    assert available, "prompts should be served"

    init = client.post(
        "/api/clips/init",
        json={"session_id": session_id, "prompt_id": available[0]["id"]},
    ).json()

    # The object key is the thing most likely to leak PII by accident.
    assert speaker_id in init["object_key"]
    for value in PII.values():
        assert value not in init["object_key"]

    assert upload(client, init["upload"]["url"], clean_take()).status_code == 200

    # A client claiming a perfect take must not override the server.
    verdict = client.post(
        f"/api/clips/{init['clip_id']}/complete",
        json={"client_metrics": {"snr_db": 99.0, "peak_dbfs": -4.0}},
    ).json()
    assert verdict["passed"]
    assert verdict["snr_db"] < 90, "server must re-measure, not trust the client"

    # And a bad take is caught even when the client insists it is fine.
    init2 = client.post(
        "/api/clips/init",
        json={"session_id": session_id, "prompt_id": available[1]["id"]},
    ).json()
    upload(client, init2["upload"]["url"], noisy_take())
    bad = client.post(
        f"/api/clips/{init2['clip_id']}/complete",
        json={"client_metrics": {"snr_db": 99.0}},
    ).json()
    assert not bad["passed"]
    assert "snr_low" in bad["codes"]

    progress = client.get(f"/api/sessions/{session_id}/progress").json()
    assert progress["passed"] == 1
    assert progress["failed"] == 1

    with SessionLocal() as db:
        clip = db.get(Clip, init["clip_id"])
        assert clip.qc_status == "passed"
        assert clip.snr_db is not None


def test_forged_upload_signature_refused(client, consent_version, prompts):
    speaker_id = make_speaker(client, consent_version)
    session_id = client.post(
        "/api/sessions", json={"speaker_id": speaker_id}
    ).json()["session_id"]
    available = client.get(f"/api/prompts?session_id={session_id}").json()
    init = client.post(
        "/api/clips/init",
        json={"session_id": session_id, "prompt_id": available[0]["id"]},
    ).json()

    res = client.put(
        f"/api/_local_upload?key={init['object_key']}&expires=99999999999&sig=deadbeef",
        content=b"x",
        headers={"Content-Type": "audio/wav"},
    )
    assert res.status_code == 403


def test_completing_without_an_upload_is_a_conflict(client, consent_version, prompts):
    speaker_id = make_speaker(client, consent_version)
    session_id = client.post(
        "/api/sessions", json={"speaker_id": speaker_id}
    ).json()["session_id"]
    available = client.get(f"/api/prompts?session_id={session_id}").json()
    init = client.post(
        "/api/clips/init",
        json={"session_id": session_id, "prompt_id": available[0]["id"]},
    ).json()

    res = client.post(f"/api/clips/{init['clip_id']}/complete", json={})
    assert res.status_code == 409


def test_inactive_prompt_cannot_be_recorded(client, consent_version, prompts, db):
    from app.models import Prompt

    db.add(Prompt(id="ne-inactive", lang="ne", text="अनुमोदन नभएको।", active=False))
    db.commit()

    speaker_id = make_speaker(client, consent_version)
    session_id = client.post(
        "/api/sessions", json={"speaker_id": speaker_id}
    ).json()["session_id"]

    served = {p["id"] for p in client.get(f"/api/prompts?session_id={session_id}").json()}
    assert "ne-inactive" not in served

    res = client.post(
        "/api/clips/init",
        json={"session_id": session_id, "prompt_id": "ne-inactive"},
    )
    assert res.status_code == 404


# --- privacy ------------------------------------------------------------


def test_export_row_contains_no_pii(client, consent_version):
    speaker_id = make_speaker(client, consent_version)
    with SessionLocal() as db:
        row = db.get(Speaker, speaker_id).export_row()

    flat = " ".join(str(v) for v in row.values())
    for value in PII.values():
        assert value not in flat
    assert "caste_ethnicity" not in row
    assert row["speaker_id"] == speaker_id


def test_pii_is_stored_but_only_in_the_speakers_table(client, consent_version):
    """The data is kept -- it just must not be reachable from an export."""
    speaker_id = make_speaker(client, consent_version)
    with SessionLocal() as db:
        speaker = db.get(Speaker, speaker_id)
        assert speaker.name == PII["name"]
        assert speaker.caste_ethnicity == PII["caste_ethnicity"]
        assert "caste_ethnicity" not in speaker.export_row()


# --- splits -------------------------------------------------------------


def test_splits_are_speaker_disjoint():
    counts = {f"SPEAKER{i:03d}": 20 + i for i in range(25)}
    splits = assign_splits(counts, (0.9, 0.05, 0.05), "test-seed")

    buckets: dict[str, set[str]] = {"train": set(), "dev": set(), "test": set()}
    for speaker_id, split in splits.items():
        buckets[split].add(speaker_id)

    assert not (buckets["train"] & buckets["test"])
    assert not (buckets["train"] & buckets["dev"])
    assert not (buckets["dev"] & buckets["test"])
    assert all(buckets[s] for s in ("train", "dev", "test"))


def test_split_assignment_is_deterministic():
    counts = {f"SPEAKER{i:03d}": 20 + i for i in range(25)}
    a = assign_splits(counts, (0.9, 0.05, 0.05), "seed-a")
    b = assign_splits(counts, (0.9, 0.05, 0.05), "seed-a")
    c = assign_splits(counts, (0.9, 0.05, 0.05), "seed-b")
    assert a == b
    assert a != c, "a different seed should reshuffle"


def test_single_speaker_still_yields_a_train_split():
    assert assign_splits({"ONLY": 5}, (0.9, 0.05, 0.05), "s") == {"ONLY": "train"}


def test_empty_corpus_yields_no_assignment():
    assert assign_splits({}, (0.9, 0.05, 0.05), "s") == {}
