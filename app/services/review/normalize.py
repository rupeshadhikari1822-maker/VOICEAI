"""Devanagari-aware text normalisation and character error rate.

This is the most dangerous code in the review pass. CER drives auto-verify and
auto-reject, so a normaliser that is slightly wrong does not produce slightly
wrong numbers -- it auto-rejects good clips in bulk, and nobody notices because
the whole point of the pre-filter is that a human never sees them.

What it does, in order:

  1. NFC. Devanagari has multiple encodings for the same grapheme: क़ can be one
     codepoint (U+0958) or क + nukta (U+0915 U+093C). Unnormalised, those compare
     as different characters and inflate CER on every word containing one.
  2. Strip ZWJ/ZWNJ. These control conjunct rendering and are invisible. A
     transcript that spells a conjunct differently is not a misread.
  3. Devanagari digits to ASCII. ASR models emit either; the prompt has one.
  4. Strip punctuation, including danda (।) and double danda (॥). A missing
     full stop is not a reading error.
  5. Collapse whitespace, casefold Latin.

CER is implemented here rather than pulled from `jiwer`, because these functions
must be testable in the base install -- making the thing that decides auto-reject
depend on an optional package is the wrong trade. It is ~20 lines of Levenshtein.
"""

from __future__ import annotations

import re
import unicodedata

# Invisible joiners that only affect conjunct rendering.
_ZERO_WIDTH = dict.fromkeys([0x200B, 0x200C, 0x200D, 0x2060, 0xFEFF])

# Devanagari digits ० १ २ ३ ४ ५ ६ ७ ८ ९ -> 0-9
_DEVA_DIGITS = {0x0966 + i: ord("0") + i for i in range(10)}

_TRANSLATE = {**_ZERO_WIDTH, **_DEVA_DIGITS}

# Danda, double danda, abbreviation sign, plus ASCII and general punctuation.
_PUNCT = re.compile(
    r"[।॥॰"
    r"!\"#$%&'()*+,\-./:;<=>?@\[\\\]^_`{|}~"
    r"‐-‧‰-⁞]"
)

_WS = re.compile(r"\s+")


def normalize(text: str) -> str:
    """Canonical form for comparison. Never shown to a user."""
    if not text:
        return ""
    out = unicodedata.normalize("NFC", text)
    out = out.translate(_TRANSLATE)
    out = _PUNCT.sub(" ", out)
    out = _WS.sub(" ", out).strip()
    return out.casefold()


def levenshtein(a: str, b: str) -> int:
    """Edit distance, two rows of memory rather than a full matrix."""
    if a == b:
        return 0
    if not a:
        return len(b)
    if not b:
        return len(a)
    # Iterate over the shorter string to keep the row small.
    if len(a) < len(b):
        a, b = b, a

    previous = list(range(len(b) + 1))
    for i, ca in enumerate(a, start=1):
        current = [i]
        for j, cb in enumerate(b, start=1):
            current.append(
                min(
                    previous[j] + 1,          # deletion
                    current[j - 1] + 1,       # insertion
                    previous[j - 1] + (ca != cb),  # substitution
                )
            )
        previous = current
    return previous[-1]


def cer(reference: str, hypothesis: str) -> float:
    """Character error rate of `hypothesis` against `reference`, both normalised.

    Returns 0.0 for an exact match. An empty reference with a non-empty
    hypothesis returns 1.0 rather than dividing by zero -- that is a clip where
    the model heard speech the prompt does not contain, which is a real failure,
    not an undefined one.
    """
    ref = normalize(reference)
    hyp = normalize(hypothesis)

    if not ref:
        return 0.0 if not hyp else 1.0

    return levenshtein(ref, hyp) / len(ref)
