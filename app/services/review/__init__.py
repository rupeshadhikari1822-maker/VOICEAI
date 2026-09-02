"""Human validation of clips: queue policy, verdicts, ASR pre-filter.

Automated QC catches noise, clipping and level. It cannot catch a clean
misread -- someone saying the wrong word, clearly, at a good level. That is what
this package is for.
"""

from __future__ import annotations

from app.services.review.asr_prefilter import PrefilterDecision, decide
from app.services.review.normalize import cer, normalize
from app.services.review.queue import next_batch, speaker_policy
from app.services.review.stats import ReviewStats, collect
from app.services.review.reasons import (
    KEYBOARD_ORDER,
    LABELS,
    RejectReason,
    ReviewAction,
    keyboard_map,
)
from app.services.review.verdicts import VerdictError, record_verdict, undo_last

__all__ = [
    "KEYBOARD_ORDER",
    "LABELS",
    "PrefilterDecision",
    "RejectReason",
    "ReviewStats",
    "ReviewAction",
    "VerdictError",
    "cer",
    "collect",
    "decide",
    "keyboard_map",
    "next_batch",
    "normalize",
    "record_verdict",
    "speaker_policy",
    "undo_last",
]
