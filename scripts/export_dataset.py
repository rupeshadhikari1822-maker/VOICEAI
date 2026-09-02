#!/usr/bin/env python
"""Turn the corpus into a training-ready dataset.

    python scripts/export_dataset.py --format asr --sr 16000 --out export_out/asr
    python scripts/export_dataset.py --format tts --sr 22050 --out export_out/tts
    python scripts/export_dataset.py --format ljspeech --out export_out/lj

Two invariants this script exists to protect:

1. **Splits are speaker-disjoint.** One voice never appears in both train and
   test. If it did, your test WER measures memorisation of a speaker rather than
   generalisation, and the number would be quietly, badly wrong.

2. **No PII leaves.** Rows are built from `Speaker.export_row()`, which returns
   a fixed set of non-identifying fields. Name, email, phone and caste are not
   reachable from here -- there is no flag that turns them on.

The 48 kHz masters in raw/ are never modified. Everything here is derived and
can be regenerated.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
import wave
from collections import defaultdict
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts._console import use_utf8  # noqa: E402

from app.services.audio_qc import decode_wav  # noqa: E402
from app.core.db import SessionLocal  # noqa: E402
from app.models import Clip, Speaker  # noqa: E402
from app.services.storage import StorageError, get_storage  # noqa: E402

FORMAT_DEFAULTS = {
    "asr": 16000,
    "tts": 22050,
    "ljspeech": 22050,
    "hf": 16000,
}

# ITU-R BS.1770 target used by most TTS recipes.
TTS_TARGET_LUFS = -23.0


# --- resampling ---------------------------------------------------------


def resample(x: np.ndarray, src_sr: int, dst_sr: int) -> np.ndarray:
    """Polyphase resample. Falls back to linear if scipy is absent."""
    if src_sr == dst_sr:
        return x
    try:
        from math import gcd

        from scipy.signal import resample_poly

        g = gcd(src_sr, dst_sr)
        return resample_poly(x, dst_sr // g, src_sr // g).astype(np.float32)
    except ImportError:
        print(
            "  warning: scipy not installed, falling back to linear interpolation.\n"
            "           Install scipy for a proper anti-aliased resample.",
            file=sys.stderr,
        )
        n_out = int(round(len(x) * dst_sr / src_sr))
        return np.interp(
            np.linspace(0, len(x) - 1, n_out), np.arange(len(x)), x
        ).astype(np.float32)


def normalize_loudness(x: np.ndarray, sr: int, target_lufs: float) -> np.ndarray:
    """Loudness-normalise for TTS. Uses pyloudnorm when available."""
    try:
        import pyloudnorm as pyln

        meter = pyln.Meter(sr)
        loudness = meter.integrated_loudness(x.astype(np.float64))
        if not np.isfinite(loudness):
            return x
        gain = 10 ** ((target_lufs - loudness) / 20.0)
    except ImportError:
        # RMS stand-in. Not BS.1770, but consistent across the set, which is
        # what matters for a single-voice TTS corpus.
        rms = float(np.sqrt(np.mean(x.astype(np.float64) ** 2)))
        if rms <= 0:
            return x
        gain = 10 ** ((target_lufs + 3.0) / 20.0) / rms

    y = x * gain
    # Normalising can push peaks past full scale; back off rather than clip.
    peak = float(np.max(np.abs(y))) if y.size else 0.0
    if peak > 0.99:
        y = y * (0.99 / peak)
    return y.astype(np.float32)


def write_wav(path: Path, x: np.ndarray, sr: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pcm = np.clip(x, -1.0, 1.0)
    ints = np.where(pcm < 0, pcm * 32768.0, pcm * 32767.0).astype("<i2")
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(ints.tobytes())


# --- splits -------------------------------------------------------------


def assign_splits(
    speaker_clip_counts: dict[str, int],
    ratios: tuple[float, float, float],
    seed: str,
) -> dict[str, str]:
    """Assign whole speakers to train/dev/test. Deterministic for a given seed.

    We shuffle speakers by a stable hash and then fill test, then dev, by clip
    count. Assigning per speaker rather than per clip is the whole point: it is
    the only way to guarantee no voice straddles two splits.
    """
    total = sum(speaker_clip_counts.values())
    if total == 0:
        return {}

    ordered = sorted(
        speaker_clip_counts,
        key=lambda s: hashlib.sha256(f"{seed}:{s}".encode()).hexdigest(),
    )

    _, dev_ratio, test_ratio = ratios
    test_quota = total * test_ratio
    dev_quota = total * dev_ratio

    assignment: dict[str, str] = {}
    test_n = dev_n = 0
    for speaker in ordered:
        n = speaker_clip_counts[speaker]
        if test_n < test_quota:
            assignment[speaker] = "test"
            test_n += n
        elif dev_n < dev_quota:
            assignment[speaker] = "dev"
            dev_n += n
        else:
            assignment[speaker] = "train"

    # With very few speakers the quotas can swallow everything. Training data
    # is the one split that must not end up empty.
    if not any(v == "train" for v in assignment.values()):
        biggest = max(speaker_clip_counts, key=lambda s: speaker_clip_counts[s])
        assignment[biggest] = "train"

    return assignment


# --- export -------------------------------------------------------------


def main() -> int:
    use_utf8()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--format", required=True, choices=sorted(FORMAT_DEFAULTS))
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--sr", type=int, help="target sample rate (per-format default)")
    parser.add_argument("--lang", default="ne")
    parser.add_argument(
        "--verified-only",
        action="store_true",
        help="only clips a human approved in the review pass",
    )
    parser.add_argument("--min-snr", type=float, default=None)
    parser.add_argument("--split-seed", default="voice-cloudfrm-v1")
    parser.add_argument("--train", type=float, default=0.90)
    parser.add_argument("--dev", type=float, default=0.05)
    parser.add_argument("--test", type=float, default=0.05)
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()

    target_sr = args.sr or FORMAT_DEFAULTS[args.format]
    out = args.out
    out.mkdir(parents=True, exist_ok=True)
    storage = get_storage()

    with SessionLocal() as db:
        query = (
            db.query(Clip, Speaker)
            .join(Speaker, Clip.speaker_id == Speaker.id)
            .filter(
                Clip.lang == args.lang,
                Clip.qc_status == "passed",
                Clip.tombstoned.is_(False),
                Speaker.withdrawn_at.is_(None),
            )
        )
        if args.verified_only:
            query = query.filter(Clip.verify_status == "verified")
        if args.min_snr is not None:
            query = query.filter(Clip.snr_db >= args.min_snr)

        rows = query.order_by(Clip.id).all()
        if args.limit:
            rows = rows[: args.limit]

        if not rows:
            print("nothing to export: no clips matched the filters", file=sys.stderr)
            return 1

        counts: dict[str, int] = defaultdict(int)
        for clip, _ in rows:
            counts[clip.speaker_id] += 1

        splits = assign_splits(
            counts, (args.train, args.dev, args.test), args.split_seed
        )

        print(f"exporting {len(rows)} clips from {len(counts)} speakers -> {out}")

        manifest: list[dict] = []
        per_split: dict[str, int] = defaultdict(int)
        total_seconds = 0.0
        failures = 0

        for clip, speaker in rows:
            split = splits[clip.speaker_id]
            try:
                data = storage.get_bytes(clip.object_key)
            except StorageError as exc:
                print(f"  missing object for clip {clip.id}: {exc}", file=sys.stderr)
                failures += 1
                continue

            try:
                x, src_sr, _channels, _bits = decode_wav(data)
            except Exception as exc:  # noqa: BLE001
                print(f"  undecodable clip {clip.id}: {exc}", file=sys.stderr)
                failures += 1
                continue

            y = resample(x, src_sr, target_sr)
            if args.format in ("tts", "ljspeech"):
                y = normalize_loudness(y, target_sr, TTS_TARGET_LUFS)

            rel = _relative_path(args.format, split, clip.id)
            write_wav(out / rel, y, target_sr)

            duration = len(y) / float(target_sr)
            total_seconds += duration
            per_split[split] += 1

            manifest.append(
                {
                    "id": clip.id,
                    "audio_filepath": rel.as_posix(),
                    "text": clip.prompt_text,
                    "duration": round(duration, 3),
                    "sample_rate": target_sr,
                    "lang": clip.lang,
                    "split": split,
                    "snr_db": clip.snr_db,
                    # Fixed, non-identifying field set. Caste is not reachable.
                    **speaker.export_row(),
                }
            )

    _write_manifests(out, args.format, manifest, per_split)
    _write_card(out, args, manifest, per_split, total_seconds, len(counts), target_sr)

    print(f"\n  clips written : {len(manifest)}")
    for split in ("train", "dev", "test"):
        print(f"  {split:<13} : {per_split.get(split, 0)}")
    print(f"  audio         : {total_seconds / 3600:.2f} h")

    # Splits hold whole speakers, so with a handful of voices the requested
    # ratios simply cannot be met. Say so rather than shipping an empty split.
    empty = [s for s in ("train", "dev", "test") if not per_split.get(s)]
    if empty:
        print(
            f"\n  note: {', '.join(empty)} split(s) are empty. Splits are"
            f" speaker-disjoint, and {len(counts)} speaker(s) cannot be divided"
            f" into the requested ratios. Recruit more speakers, or pass"
            f" --train/--dev/--test to rebalance."
        )
    if failures:
        print(f"  skipped       : {failures} (see stderr)")
    print(f"\nwrote {out}")
    return 0


def _relative_path(fmt: str, split: str, clip_id: str) -> Path:
    if fmt == "ljspeech":
        return Path("wavs") / f"{clip_id}.wav"
    if fmt == "hf":
        return Path("data") / split / f"{clip_id}.wav"
    return Path(split) / f"{clip_id}.wav"


def _write_manifests(
    out: Path, fmt: str, manifest: list[dict], per_split: dict[str, int]
) -> None:
    # Full manifest, always. Everything else is a view onto it.
    with (out / "manifest.jsonl").open("w", encoding="utf-8") as fh:
        for row in manifest:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")

    if fmt in ("asr", "tts", "hf"):
        for split in per_split:
            rows = [r for r in manifest if r["split"] == split]
            with (out / f"{split}.jsonl").open("w", encoding="utf-8") as fh:
                for row in rows:
                    fh.write(json.dumps(row, ensure_ascii=False) + "\n")

    if fmt == "hf":
        for split in per_split:
            rows = [r for r in manifest if r["split"] == split]
            path = out / "data" / split / "metadata.csv"
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("w", encoding="utf-8", newline="") as fh:
                writer = csv.writer(fh)
                writer.writerow(["file_name", "transcription", "speaker_id", "duration"])
                for row in rows:
                    writer.writerow(
                        [
                            Path(row["audio_filepath"]).name,
                            row["text"],
                            row["speaker_id"],
                            row["duration"],
                        ]
                    )

    if fmt == "ljspeech":
        # LJSpeech: id|raw text|normalised text, pipe-delimited, no header.
        with (out / "metadata.csv").open("w", encoding="utf-8", newline="") as fh:
            for row in manifest:
                fh.write(f"{row['id']}|{row['text']}|{row['text']}\n")


def _write_card(
    out: Path,
    args: argparse.Namespace,
    manifest: list[dict],
    per_split: dict[str, int],
    total_seconds: float,
    n_speakers: int,
    target_sr: int,
) -> None:
    """A dataset card, so the provenance travels with the data."""
    speakers_by_split: dict[str, set[str]] = defaultdict(set)
    for row in manifest:
        speakers_by_split[row["split"]].add(row["speaker_id"])

    overlap = (
        speakers_by_split["train"] & speakers_by_split["test"]
    ) | (speakers_by_split["train"] & speakers_by_split["dev"])

    lines = [
        "# Dataset card",
        "",
        f"- Language: `{args.lang}`",
        f"- Format: `{args.format}`",
        f"- Sample rate: {target_sr} Hz, 16-bit mono WAV",
        f"- Clips: {len(manifest)}",
        f"- Speakers: {n_speakers}",
        f"- Duration: {total_seconds / 3600:.2f} hours",
        f"- Split seed: `{args.split_seed}`",
        "",
        "## Splits",
        "",
        "| Split | Clips | Speakers |",
        "| --- | --- | --- |",
    ]
    for split in ("train", "dev", "test"):
        lines.append(
            f"| {split} | {per_split.get(split, 0)} | {len(speakers_by_split[split])} |"
        )

    lines += [
        "",
        f"Speaker-disjoint: **{'NO -- BUG' if overlap else 'yes'}**"
        + (f" (overlap: {sorted(overlap)})" if overlap else ""),
        "",
        "## Privacy",
        "",
        "Speakers appear only as opaque ULIDs. Names, emails, phone numbers and",
        "caste/ethnicity are held in the source database and are not present in",
        "this export in any form. Caste and ethnicity are sensitive personal",
        "information under Nepal's Individual Privacy Act 2075 s.27(2) and are",
        "never exported.",
        "",
        "Withdrawal requests are handled with `scripts/withdraw.py`; re-run this",
        "export afterwards to produce a dataset with those speakers removed.",
        "",
        "## Provenance",
        "",
        "Derived from 48 kHz / 16-bit / mono PCM masters captured in-browser via",
        "AudioWorklet with echo cancellation, noise suppression and auto gain",
        "control disabled. Every clip passed server-side QC in `app/services/audio_qc/`.",
    ]
    if args.format in ("tts", "ljspeech"):
        lines.append(f"Loudness-normalised to {TTS_TARGET_LUFS:.0f} LUFS.")

    (out / "DATASET_CARD.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    if overlap:
        print(
            f"\nERROR: speaker overlap between splits: {sorted(overlap)}",
            file=sys.stderr,
        )


if __name__ == "__main__":
    raise SystemExit(main())
