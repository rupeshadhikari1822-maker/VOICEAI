"""Decide what to do with a clip given what the ASR model heard.

This is the highest-leverage part of the review pass. Because the target text is
already known, this is a much easier problem than open transcription: we only
need to know whether the reader said roughly the printed sentence. Typically
60-80% of the queue can be resolved without a human.

Pure decision logic -- no model loading, no I/O. `scripts/asr_prefilter.py` does
the slow part in batch. Transcription must never happen inside a request.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.core.config import Settings
from app.services.review.normalize import cer
from app.services.review.reasons import RejectReason

# Priority for a clip with no ASR data at all. Sits above the confidently-judged
# ones and below the genuinely ambiguous, so an un-transcribed backlog neither
# floods the queue nor sinks out of sight.
NO_ASR_PRIORITY = 50


@dataclass(frozen=True)
class PrefilterDecision:
    verify_status: str            # "verified" | "rejected" | "unverified"
    reject_reason: str | None
    review_priority: int          # higher surfaces first
    cer: float
    auto: bool                    # did the model decide, or is a human needed?


def decide(prompt_text: str, asr_text: str, settings: Settings) -> PrefilterDecision:
    """Classify one clip by character error rate against its prompt."""
    score = cer(prompt_text, asr_text)

    verify_t = settings.asr_auto_verify_cer
    reject_t = settings.asr_auto_reject_cer

    if score < verify_t:
        # Said what was printed. Nothing for a human to add.
        return PrefilterDecision("verified", None, 0, score, auto=True)

    if score > reject_t:
        # Far enough from the prompt that it is a misread, not a transcription
        # wobble. `bad_prompt` is deliberately not inferred here -- that is a
        # judgement about the sentence, which needs the aggregate view.
        return PrefilterDecision(
            "rejected", RejectReason.MISREAD.value, 0, score, auto=True
        )

    return PrefilterDecision(
        "unverified", None, uncertainty_priority(score, settings), score, auto=False
    )


def uncertainty_priority(score: float, settings: Settings) -> int:
    """0-100, peaking where the model is least able to decide.

    Priority peaks at the middle of the undecided band rather than rising with
    CER, because a clip at the edges is nearly resolved either way. The middle is
    where a human's time actually buys information.
    """
    verify_t = settings.asr_auto_verify_cer
    reject_t = settings.asr_auto_reject_cer
    half = (reject_t - verify_t) / 2.0
    if half <= 0:
        return NO_ASR_PRIORITY

    midpoint = (verify_t + reject_t) / 2.0
    closeness = 1.0 - abs(score - midpoint) / half
    return max(0, min(100, int(round(closeness * 100))))
