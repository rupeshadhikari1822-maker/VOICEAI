"""Server-side audio quality control.

This package is authoritative. The browser computes the same metrics for instant
feedback, but every clip is re-analysed here from the bytes that actually landed
in storage. If the two disagree, this one wins.

    metrics.py     decode + measure (physics)
    thresholds.py  the numbers      (policy)
    gate.py        verdict + contributor-facing messages

`analyze()` is the whole surface most callers need.
"""

from __future__ import annotations

from app.services.audio_qc.gate import apply_gate
from app.services.audio_qc.metrics import (
    QCResult,
    dbfs,
    decode_wav,
    frame_energies,
    measure,
)
from app.services.audio_qc.thresholds import (
    ASR_THRESHOLDS,
    TTS_THRESHOLDS,
    QCThresholds,
)

__all__ = [
    "ASR_THRESHOLDS",
    "QCResult",
    "QCThresholds",
    "TTS_THRESHOLDS",
    "analyze",
    "apply_gate",
    "dbfs",
    "decode_wav",
    "frame_energies",
    "measure",
]


def analyze(data: bytes, thresholds: QCThresholds | None = None) -> QCResult:
    """Measure a WAV blob and decide whether it is fit for the corpus."""
    result = measure(data)
    # measure() sets a code only when it could not get far enough to judge
    # (undecodable, empty, no speech). Those are already final.
    if result.codes:
        return result

    apply_gate(result, thresholds or ASR_THRESHOLDS)
    result.passed = not result.codes
    return result
