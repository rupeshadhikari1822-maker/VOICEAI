"""Turn the corpus into a training-ready dataset.

Import from here: `from app.services.export import run_export, export_to_zip`.
See `pipeline.py` for the shared DB-to-zip logic, `manifest.py` for the
per-format manifest/card writers, `audio.py` for resampling/loudness, and
`splits.py` for the speaker-disjoint split assignment.
"""

from __future__ import annotations

from app.services.export.audio import TTS_TARGET_LUFS, normalize_loudness, resample, write_wav
from app.services.export.manifest import (
    FORMAT_DEFAULTS,
    relative_path,
    write_dataset_card,
    write_manifest_files,
)
from app.services.export.pipeline import (
    ExportEmpty,
    ExportResult,
    export_to_zip,
    run_export,
    zip_export_dir,
)
from app.services.export.splits import assign_splits

__all__ = [
    "FORMAT_DEFAULTS",
    "TTS_TARGET_LUFS",
    "ExportEmpty",
    "ExportResult",
    "assign_splits",
    "export_to_zip",
    "normalize_loudness",
    "relative_path",
    "resample",
    "run_export",
    "write_dataset_card",
    "write_manifest_files",
    "write_wav",
    "zip_export_dir",
]
