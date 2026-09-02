"""Structured reject reasons.

Free text cannot be aggregated. These can, and that is where the payoff is:
group rejections by `prompt_id` and a prompt that five different speakers misread
stops looking like five bad readers and starts looking like one bad prompt.
Numerals and long conjuncts are the usual culprits.

`review_notes` stays available for the odd case, but is never the primary signal.
"""

from __future__ import annotations

from enum import StrEnum


class RejectReason(StrEnum):
    MISREAD = "misread"                    # read a different word than printed
    WRONG_WORD = "wrong_word"              # substituted a word
    PARTIAL = "partial"                    # cut off, incomplete sentence
    EXTRA_SPEECH = "extra_speech"          # said something beyond the prompt
    BACKGROUND_EVENT = "background_event"  # door, horn, another voice
    HESITATION = "hesitation"              # false start, stammer, self-correction
    WRONG_LANGUAGE = "wrong_language"      # not the language the prompt is in
    BAD_PROMPT = "bad_prompt"              # the sentence itself is the problem
    OTHER = "other"

    @classmethod
    def values(cls) -> list[str]:
        return [r.value for r in cls]


# Order matters: this is the 1-9 keyboard mapping in the review UI, so it must
# stay stable or reviewers will build muscle memory for the wrong key.
KEYBOARD_ORDER: list[RejectReason] = [
    RejectReason.MISREAD,
    RejectReason.WRONG_WORD,
    RejectReason.PARTIAL,
    RejectReason.EXTRA_SPEECH,
    RejectReason.BACKGROUND_EVENT,
    RejectReason.HESITATION,
    RejectReason.WRONG_LANGUAGE,
    RejectReason.BAD_PROMPT,
    RejectReason.OTHER,
]

# Nepali-first labels, matching the recorder UI's voice.
LABELS: dict[RejectReason, str] = {
    RejectReason.MISREAD: "गलत पढ्यो",
    RejectReason.WRONG_WORD: "फरक शब्द",
    RejectReason.PARTIAL: "अधुरो",
    RejectReason.EXTRA_SPEECH: "थप बोली",
    RejectReason.BACKGROUND_EVENT: "पछाडिको आवाज",
    RejectReason.HESITATION: "अड्कियो",
    RejectReason.WRONG_LANGUAGE: "फरक भाषा",
    RejectReason.BAD_PROMPT: "वाक्य नै बिग्रेको",
    RejectReason.OTHER: "अन्य",
}


class ReviewAction(StrEnum):
    VERIFIED = "verified"
    REJECTED = "rejected"
    SKIPPED = "skipped"
    UNSURE = "unsure"


def keyboard_map() -> list[dict]:
    """What the UI renders next to keys 1-9."""
    return [
        {"key": str(i + 1), "reason": r.value, "label": LABELS[r]}
        for i, r in enumerate(KEYBOARD_ORDER)
    ]
