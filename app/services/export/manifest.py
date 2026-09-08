"""Manifest and dataset-card writers, one per training pipeline shape.

Every training stack reads a corpus differently, so a single export produces
several equivalent views of the same manifest rather than picking one:

- `manifest.jsonl` (always) -- one JSON object per clip, the NeMo/ESPnet-style
  shape most ASR toolkits and custom loaders already know how to read.
- `{split}.jsonl` (asr/tts/hf) -- the same rows, pre-split.
- `data/{split}/metadata.csv` (hf) -- Hugging Face `datasets`' AudioFolder
  convention, so `load_dataset("audiofolder", data_dir=...)` works with zero
  loader code.
- `metadata.csv` (ljspeech) -- `id|text|normalised_text`, the format Tacotron2,
  VITS, Coqui TTS and ESPnet's TTS recipes all expect out of the box.
"""

from __future__ import annotations

import csv
import json
from collections import defaultdict
from pathlib import Path

FORMAT_DEFAULTS: dict[str, int] = {
    "asr": 16000,
    "tts": 22050,
    "ljspeech": 22050,
    "hf": 16000,
}


def relative_path(fmt: str, split: str, clip_id: str) -> Path:
    if fmt == "ljspeech":
        return Path("wavs") / f"{clip_id}.wav"
    if fmt == "hf":
        return Path("data") / split / f"{clip_id}.wav"
    return Path(split) / f"{clip_id}.wav"


def write_manifest_files(
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


def write_dataset_card(
    out: Path,
    *,
    lang: str,
    fmt: str,
    target_sr: int,
    split_seed: str,
    manifest: list[dict],
    per_split: dict[str, int],
    total_seconds: float,
    n_speakers: int,
) -> set[str]:
    """A dataset card, so the provenance travels with the data.

    Returns the set of speaker IDs that leaked across train and test/dev, if
    any -- should always be empty; the caller decides how loudly to complain.
    """
    speakers_by_split: dict[str, set[str]] = defaultdict(set)
    for row in manifest:
        speakers_by_split[row["split"]].add(row["speaker_id"])

    overlap = (speakers_by_split["train"] & speakers_by_split["test"]) | (
        speakers_by_split["train"] & speakers_by_split["dev"]
    )

    lines = [
        "# Dataset card",
        "",
        f"- Language: `{lang}`",
        f"- Format: `{fmt}`",
        f"- Sample rate: {target_sr} Hz, 16-bit mono WAV",
        f"- Clips: {len(manifest)}",
        f"- Speakers: {n_speakers}",
        f"- Duration: {total_seconds / 3600:.2f} hours",
        f"- Split seed: `{split_seed}`",
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
    if fmt in ("tts", "ljspeech"):
        from app.services.export.audio import TTS_TARGET_LUFS

        lines.append(f"Loudness-normalised to {TTS_TARGET_LUFS:.0f} LUFS.")

    (out / "DATASET_CARD.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return overlap
