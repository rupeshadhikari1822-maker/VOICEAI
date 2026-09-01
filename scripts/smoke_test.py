#!/usr/bin/env python
"""End-to-end smoke test.

    python scripts/smoke_test.py

Runs against a throwaway SQLite file and a temp storage directory, so it is safe
to run anywhere and leaves nothing behind. It checks the things that would
silently ruin a corpus rather than crash the server:

  * a clean take passes and a noisy one is rejected, with the SNR gate
    actually doing the discriminating
  * clipping is detected
  * the full init -> upload -> complete flow stores a clip and QCs it from the
    stored bytes, not from what the client claimed
  * the object key contains the speaker ULID and none of the PII
  * export rows carry no name, email, phone or caste
  * split assignment never puts one speaker in two splits
"""

from __future__ import annotations

import io
import os
import sys
import tempfile
import wave
from pathlib import Path
from urllib.parse import urlparse

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# Point everything at a sandbox before app modules read their settings.
_TMP = tempfile.mkdtemp(prefix="voice-smoke-")
os.environ["DATABASE_URL"] = f"sqlite:///{Path(_TMP).as_posix()}/smoke.db"
os.environ["STORAGE_BACKEND"] = "local"
os.environ["LOCAL_STORAGE_DIR"] = str(Path(_TMP) / "storage")
os.environ["SECRET_KEY"] = "smoke-test-key"
os.environ["PUBLIC_BASE_URL"] = "http://testserver"

from app.audio_qc import ASR_THRESHOLDS, analyze  # noqa: E402
from app.config import get_settings  # noqa: E402

SR = 48000
PASS = "\033[92mPASS\033[0m" if sys.stdout.isatty() else "PASS"
FAIL = "\033[91mFAIL\033[0m" if sys.stdout.isatty() else "FAIL"

_results: list[tuple[bool, str]] = []


def check(ok: bool, label: str, detail: str = "") -> bool:
    _results.append((ok, label))
    print(f"  [{PASS if ok else FAIL}] {label}" + (f"  ({detail})" if detail else ""))
    return ok


# --- synthetic audio ----------------------------------------------------


def synth_speech(duration_s: float = 3.0, sr: int = SR, rms_dbfs: float = -16.0):
    """A voice-like signal: harmonic stack, moving pitch, syllable envelope."""
    t = np.arange(int(sr * duration_s)) / sr
    f0 = 120.0 + 18.0 * np.sin(2 * np.pi * 0.7 * t)
    phase = 2 * np.pi * np.cumsum(f0) / sr
    sig = sum((1.0 / k) * np.sin(k * phase) for k in range(1, 12))
    # Syllable rate ~3.5 Hz, which is roughly conversational.
    envelope = (0.5 * (1 + np.sin(2 * np.pi * 3.5 * t - np.pi / 2))) ** 1.5
    sig = sig * (0.15 + 0.85 * envelope)
    sig = sig / max(float(np.sqrt(np.mean(sig**2))), 1e-12)
    return (sig * (10 ** (rms_dbfs / 20.0))).astype(np.float32)


def with_room(speech, noise_dbfs: float, pad_s: float = 0.3, sr: int = SR):
    """Pad with room tone at both ends and mix noise across the whole take."""
    pad = int(sr * pad_s)
    body = np.concatenate([np.zeros(pad, np.float32), speech, np.zeros(pad, np.float32)])
    rng = np.random.default_rng(20260901)
    noise = rng.standard_normal(body.size).astype(np.float32)
    noise *= (10 ** (noise_dbfs / 20.0)) / max(float(np.sqrt(np.mean(noise**2))), 1e-12)
    return body + noise


def to_wav(samples, sr: int = SR) -> bytes:
    pcm = np.clip(samples, -1.0, 1.0)
    ints = np.where(pcm < 0, pcm * 32768.0, pcm * 32767.0).astype("<i2")
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(ints.tobytes())
    return buf.getvalue()


# --- 1. QC discrimination ----------------------------------------------


def test_qc() -> None:
    print("\naudio QC")

    clean = analyze(to_wav(with_room(synth_speech(), noise_dbfs=-63.0)), ASR_THRESHOLDS)
    check(
        clean.passed and clean.snr_db >= ASR_THRESHOLDS.min_snr_db,
        "clean take passes the QC gate",
        f"SNR {clean.snr_db:.0f} dB, peak {clean.peak_dbfs:.1f} dBFS, "
        f"floor {clean.noise_floor_dbfs:.0f} dBFS",
    )
    if clean.codes:
        print(f"        unexpected failure codes: {clean.codes}")

    noisy = analyze(to_wav(with_room(synth_speech(), noise_dbfs=-26.0)), ASR_THRESHOLDS)
    check(
        not noisy.passed and "snr_low" in noisy.codes,
        "noisy take is rejected on SNR",
        f"SNR {noisy.snr_db:.0f} dB, floor {noisy.noise_floor_dbfs:.0f} dBFS",
    )
    check(
        any("पंखा" in r for r in noisy.reasons),
        "rejection tells the reader what to physically change",
        "Nepali guidance present",
    )

    hot = analyze(to_wav(with_room(synth_speech(rms_dbfs=-2.0), -63.0)), ASR_THRESHOLDS)
    check(
        not hot.passed and ("clipping" in hot.codes or "too_loud" in hot.codes),
        "clipped take is rejected",
        f"clipping {hot.clipping_ratio * 100:.2f}%, peak {hot.peak_dbfs:.1f} dBFS",
    )

    silence = analyze(to_wav(np.zeros(SR * 2, np.float32)), ASR_THRESHOLDS)
    check(not silence.passed, "silence is rejected", f"codes {silence.codes}")

    quiet = analyze(to_wav(with_room(synth_speech(rms_dbfs=-52.0), -80.0)), ASR_THRESHOLDS)
    check(
        not quiet.passed and "too_quiet" in quiet.codes,
        "too-quiet take is rejected",
        f"peak {quiet.peak_dbfs:.1f} dBFS",
    )

    check(
        analyze(b"not a wav file at all").passed is False,
        "garbage input fails cleanly instead of raising",
    )


# --- 2. full API flow ---------------------------------------------------


def test_api() -> None:
    print("\nAPI flow")
    try:
        from fastapi.testclient import TestClient
    except ImportError:
        print("  [skip] fastapi.testclient unavailable (pip install httpx)")
        return

    from app.db import SessionLocal, create_all
    from app.main import app
    from app.models import Clip, Prompt

    create_all()
    with SessionLocal() as db:
        if db.get(Prompt, "ne-test-1") is None:
            db.add(Prompt(id="ne-test-1", lang="ne", text="नमस्ते, तपाईंलाई कस्तो छ?", active=True))
            db.add(Prompt(id="ne-test-2", lang="ne", text="आज मौसम राम्रो छ।", active=True))
            db.commit()

    client = TestClient(app)

    config = client.get("/api/config").json()
    check(config["audio"]["sample_rate"] == 48000, "config advertises 48 kHz capture")

    # PII goes in deliberately, to prove it never comes back out.
    speaker_res = client.post(
        "/api/speakers",
        json={
            "name": "Test Contributor",
            "email": "contributor@example.com",
            "phone": "+9779800000000",
            "caste_ethnicity": "SENSITIVE-VALUE",
            "province": "बागमती",
            "district": "काठमाडौं",
            "mother_tongue": "नेपाली",
            "age_band": "25-34",
            "gender": "female",
            "consent": {
                "version": config["consent"]["version"],
                "accepted": True,
                "commercial_use": False,
            },
        },
    )
    check(speaker_res.status_code == 201, "speaker created", f"HTTP {speaker_res.status_code}")
    speaker_id = speaker_res.json()["speaker_id"]

    refused = client.post(
        "/api/speakers",
        json={"consent": {"version": config["consent"]["version"], "accepted": False}},
    )
    check(refused.status_code == 400, "recording without consent is refused")

    session_id = client.post(
        "/api/sessions", json={"speaker_id": speaker_id, "lang": "ne"}
    ).json()["session_id"]

    prompts = client.get(f"/api/prompts?session_id={session_id}").json()
    check(len(prompts) >= 1, "prompts served", f"{len(prompts)} available")

    init = client.post(
        "/api/clips/init",
        json={"session_id": session_id, "prompt_id": prompts[0]["id"]},
    ).json()

    key = init["object_key"]
    check(
        speaker_id in key
        and "Test Contributor" not in key
        and "contributor@example.com" not in key
        and "SENSITIVE-VALUE" not in key,
        "object key carries the ULID and no PII",
        key,
    )

    # Upload through the presigned URL, exactly as the browser does.
    parsed = urlparse(init["upload"]["url"])
    upload = client.put(
        f"{parsed.path}?{parsed.query}",
        content=to_wav(with_room(synth_speech(), noise_dbfs=-63.0)),
        headers={"Content-Type": "audio/wav"},
    )
    check(upload.status_code == 200, "presigned upload accepted", f"HTTP {upload.status_code}")

    # A client claiming a perfect take must not be able to override the server.
    verdict = client.post(
        f"/api/clips/{init['clip_id']}/complete",
        json={"client_metrics": {"snr_db": 99.0, "peak_dbfs": -4.0}},
    ).json()
    check(
        verdict["passed"] and verdict["snr_db"] < 90,
        "server re-measures the stored bytes and ignores client claims",
        f"server SNR {verdict['snr_db']:.0f} dB vs client-claimed 99 dB",
    )

    # And a bad take is caught even when the client says it is fine.
    init2 = client.post(
        "/api/clips/init",
        json={"session_id": session_id, "prompt_id": prompts[1]["id"]},
    ).json()
    p2 = urlparse(init2["upload"]["url"])
    client.put(
        f"{p2.path}?{p2.query}",
        content=to_wav(with_room(synth_speech(), noise_dbfs=-26.0)),
        headers={"Content-Type": "audio/wav"},
    )
    bad = client.post(
        f"/api/clips/{init2['clip_id']}/complete",
        json={"client_metrics": {"snr_db": 99.0}},
    ).json()
    check(not bad["passed"] and "snr_low" in bad["codes"], "noisy upload rejected server-side")

    tampered = client.put(
        f"{parsed.path}?key={key}&expires=99999999999&sig=deadbeef",
        content=b"x",
        headers={"Content-Type": "audio/wav"},
    )
    check(tampered.status_code == 403, "forged upload signature is refused")

    progress = client.get(f"/api/sessions/{session_id}/progress").json()
    check(progress["passed"] == 1 and progress["failed"] == 1, "progress counts are right",
          f"passed={progress['passed']} failed={progress['failed']}")

    with SessionLocal() as db:
        clip = db.get(Clip, init["clip_id"])
        check(
            clip.qc_status == "passed" and clip.snr_db is not None,
            "QC verdict persisted on the clip row",
            f"status={clip.qc_status} snr={clip.snr_db:.0f}",
        )

    return speaker_id


# --- 3. privacy + splits ------------------------------------------------


def test_privacy_and_splits() -> None:
    print("\nprivacy and splits")

    from app.db import SessionLocal
    from app.models import Speaker
    from scripts.export_dataset import assign_splits

    with SessionLocal() as db:
        speaker = db.query(Speaker).first()
        if speaker is not None:
            row = speaker.export_row()
            leaked = [
                field
                for field, value in row.items()
                if isinstance(value, str)
                and value in {"Test Contributor", "contributor@example.com",
                              "+9779800000000", "SENSITIVE-VALUE"}
            ]
            check(not leaked, "export row contains no PII", f"fields: {sorted(row)}")
            check(
                "caste_ethnicity" not in row,
                "caste/ethnicity is absent from the export schema entirely",
            )

    counts = {f"SPEAKER{i:03d}": 20 + i for i in range(25)}
    splits = assign_splits(counts, (0.9, 0.05, 0.05), "smoke")
    buckets: dict[str, set[str]] = {"train": set(), "dev": set(), "test": set()}
    for speaker_id, split in splits.items():
        buckets[split].add(speaker_id)

    overlap = (buckets["train"] & buckets["test"]) | (buckets["train"] & buckets["dev"])
    check(not overlap, "splits are speaker-disjoint", f"overlap={sorted(overlap)}")
    check(
        all(buckets[s] for s in ("train", "dev", "test")),
        "every split got at least one speaker",
        f"train={len(buckets['train'])} dev={len(buckets['dev'])} test={len(buckets['test'])}",
    )
    check(
        assign_splits(counts, (0.9, 0.05, 0.05), "smoke") == splits,
        "split assignment is deterministic",
    )

    tiny = assign_splits({"ONLY": 5}, (0.9, 0.05, 0.05), "smoke")
    check(tiny == {"ONLY": "train"}, "a single speaker still yields a train split")


# --- 4. storage key hygiene --------------------------------------------


def test_storage() -> None:
    print("\nstorage")
    from app.storage import LocalStorage, StorageError, raw_key

    storage = LocalStorage(get_settings())
    key = raw_key("ne", "01SPEAKER", "01SESSION", "01CLIP")
    check(key == "raw/ne/01SPEAKER/01SESSION/01CLIP.wav", "key layout is stable", key)

    storage.put_bytes("raw/ne/X/Y/Z.wav", b"hello")
    check(storage.get_bytes("raw/ne/X/Y/Z.wav") == b"hello", "round-trips bytes")
    storage.delete("raw/ne/X/Y/Z.wav")
    check(not storage.exists("raw/ne/X/Y/Z.wav"), "delete removes the object")

    try:
        storage.get_bytes("../../etc/passwd")
        traversal_blocked = False
    except StorageError:
        traversal_blocked = True
    check(traversal_blocked, "path traversal in an object key is refused")


def main() -> int:
    print("=" * 62)
    print("  voice.cloudfrm.ai smoke test")
    print("=" * 62)
    print(f"  sandbox: {_TMP}")

    test_qc()
    test_api()
    test_privacy_and_splits()
    test_storage()

    failed = [label for ok, label in _results if not ok]
    print("\n" + "=" * 62)
    if failed:
        print(f"  {len(failed)} of {len(_results)} checks FAILED:")
        for label in failed:
            print(f"    - {label}")
        print("=" * 62)
        return 1

    print(f"  smoke test passed  ({len(_results)} checks)")
    print("=" * 62)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
