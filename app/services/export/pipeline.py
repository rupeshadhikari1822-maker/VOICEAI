"""The export pipeline: DB rows -> resampled WAVs + manifests + a dataset card.

Shared by `scripts/export_dataset.py` (CLI, run on the box) and the admin
dashboard's `/api/admin/export` (download button, no shell access needed) --
both must produce byte-identical corpus semantics: speaker-disjoint splits and
`Speaker.export_row()`'s PII fence. Neither call site duplicates this logic.
"""

from __future__ import annotations

import logging
import shutil
import tempfile
import zipfile
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy.orm import Session

from app.models import Clip, Speaker
from app.services.audio_qc import decode_wav
from app.services.export.audio import TTS_TARGET_LUFS, normalize_loudness, resample, write_wav
from app.services.export.manifest import (
    FORMAT_DEFAULTS,
    relative_path,
    write_dataset_card,
    write_manifest_files,
)
from app.services.export.splits import assign_splits
from app.services.storage import BaseStorage, StorageError

logger = logging.getLogger(__name__)


class ExportEmpty(RuntimeError):
    """No clips matched the requested filters -- nothing to write."""


@dataclass
class ExportResult:
    out_dir: Path
    manifest: list[dict]
    per_split: dict[str, int]
    total_seconds: float
    n_speakers: int
    failures: int
    target_sr: int
    speaker_overlap: set[str]


def run_export(
    db: Session,
    storage: BaseStorage,
    out: Path,
    *,
    fmt: str,
    sr: int | None = None,
    lang: str = "ne",
    verified_only: bool = False,
    min_snr: float | None = None,
    split_seed: str = "voice-cloudfrm-v1",
    train: float = 0.90,
    dev: float = 0.05,
    test: float = 0.05,
    limit: int | None = None,
) -> ExportResult:
    """Write WAVs + manifests + a dataset card under `out`.

    Raises `ExportEmpty` if no clip matches. Read-only against the database
    and the object store; `out` is the only thing written.
    """
    target_sr = sr or FORMAT_DEFAULTS[fmt]
    out.mkdir(parents=True, exist_ok=True)

    query = (
        db.query(Clip, Speaker)
        .join(Speaker, Clip.speaker_id == Speaker.id)
        .filter(
            Clip.lang == lang,
            Clip.qc_status == "passed",
            Clip.tombstoned.is_(False),
            Speaker.withdrawn_at.is_(None),
        )
    )
    if verified_only:
        query = query.filter(Clip.verify_status == "verified")
    if min_snr is not None:
        query = query.filter(Clip.snr_db >= min_snr)

    rows = query.order_by(Clip.id).all()
    if limit:
        rows = rows[:limit]
    if not rows:
        raise ExportEmpty("no clips matched the filters")

    counts: dict[str, int] = defaultdict(int)
    for clip, _ in rows:
        counts[clip.speaker_id] += 1
    splits = assign_splits(counts, (train, dev, test), split_seed)

    manifest: list[dict] = []
    per_split: dict[str, int] = defaultdict(int)
    total_seconds = 0.0
    failures = 0

    for clip, speaker in rows:
        split = splits[clip.speaker_id]
        try:
            data = storage.get_bytes(clip.object_key)
        except StorageError as exc:
            logger.warning("export: missing object for clip %s: %s", clip.id, exc)
            failures += 1
            continue

        try:
            x, src_sr, _channels, _bits = decode_wav(data)
        except Exception as exc:  # noqa: BLE001
            logger.warning("export: undecodable clip %s: %s", clip.id, exc)
            failures += 1
            continue

        y = resample(x, src_sr, target_sr)
        if fmt in ("tts", "ljspeech"):
            y = normalize_loudness(y, target_sr, TTS_TARGET_LUFS)

        rel = relative_path(fmt, split, clip.id)
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

    write_manifest_files(out, fmt, manifest, per_split)
    overlap = write_dataset_card(
        out,
        lang=lang,
        fmt=fmt,
        target_sr=target_sr,
        split_seed=split_seed,
        manifest=manifest,
        per_split=per_split,
        total_seconds=total_seconds,
        n_speakers=len(counts),
    )
    if overlap:
        logger.error("export: speaker overlap between splits: %s", sorted(overlap))

    return ExportResult(
        out_dir=out,
        manifest=manifest,
        per_split=dict(per_split),
        total_seconds=total_seconds,
        n_speakers=len(counts),
        failures=failures,
        target_sr=target_sr,
        speaker_overlap=overlap,
    )


def zip_export_dir(src_dir: Path, zip_path: Path) -> Path:
    """Zip `src_dir`'s contents (not the directory itself) into `zip_path`."""
    zip_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for path in sorted(src_dir.rglob("*")):
            if path.is_file():
                zf.write(path, path.relative_to(src_dir))
    return zip_path


def export_to_zip(
    db: Session, storage: BaseStorage, *, fmt: str, **kwargs
) -> tuple[Path, Path, ExportResult]:
    """Run the pipeline into a fresh temp directory and zip the result.

    Returns `(workdir, zip_path, result)`. `workdir` holds both the unzipped
    dataset and the zip; the caller (the admin download endpoint) is
    responsible for deleting it once the response has been sent.
    """
    workdir = Path(tempfile.mkdtemp(prefix="voiceai-export-"))
    try:
        dataset_dir = workdir / "dataset"
        result = run_export(db, storage, dataset_dir, fmt=fmt, **kwargs)
        zip_path = zip_export_dir(dataset_dir, workdir / f"voiceai-{fmt}-export.zip")
        return workdir, zip_path, result
    except BaseException:
        shutil.rmtree(workdir, ignore_errors=True)
        raise
