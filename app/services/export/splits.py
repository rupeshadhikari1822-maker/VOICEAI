"""Speaker-disjoint train/dev/test assignment.

One voice must never appear in both train and test -- see the hard rule in
CLAUDE.md. Assigning whole speakers (not individual clips) is the only way to
guarantee that.
"""

from __future__ import annotations

import hashlib


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
