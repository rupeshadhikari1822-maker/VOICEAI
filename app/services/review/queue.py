"""Which clip a reviewer sees next.

Not "the next unverified clip". Three things shape the order, and each exists
because of a specific way reviewer time gets wasted:

1. **Speaker warm-up sampling.** Review all of a speaker's first N clips, then
   drop to a sample. Speaker quality is strongly autocorrelated -- someone who
   read twenty sentences cleanly in a quiet room will almost certainly read the
   next two hundred the same way. Reviewing all of them buys almost nothing.
   Sampling snaps back to 100% if their rejection rate climbs, so a speaker whose
   setup changes halfway through is caught.

2. **Priority ordering.** ASR uncertainty first (see asr_prefilter), then clips
   whose prompt has already been rejected for other speakers -- if a sentence is
   ambiguous, seeing several readings of it together is what makes that visible.

3. **No two consecutive clips from the same speaker.** Reviewers habituate to a
   voice within a few clips and stop hearing errors in it.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.models import Clip, Speaker


@dataclass(frozen=True)
class SpeakerPolicy:
    speaker_id: str
    reviewed: int
    rejected: int
    in_warmup: bool
    sampling: bool

    @property
    def reject_rate(self) -> float:
        return self.rejected / self.reviewed if self.reviewed else 0.0


def speaker_policy(db: Session, speaker_id: str, settings: Settings) -> SpeakerPolicy:
    """How much of this speaker's remaining output needs human review."""
    reviewed = (
        db.scalar(
            select(func.count())
            .select_from(Clip)
            .where(
                Clip.speaker_id == speaker_id,
                Clip.verify_status.in_(("verified", "rejected")),
                Clip.tombstoned.is_(False),
            )
        )
        or 0
    )
    rejected = (
        db.scalar(
            select(func.count())
            .select_from(Clip)
            .where(
                Clip.speaker_id == speaker_id,
                Clip.verify_status == "rejected",
                Clip.tombstoned.is_(False),
            )
        )
        or 0
    )

    in_warmup = reviewed < settings.review_warmup_clips
    rate = rejected / reviewed if reviewed else 0.0
    # Past warm-up and behaving: sample. Otherwise review everything.
    sampling = (not in_warmup) and rate <= settings.review_reject_rate_trigger

    return SpeakerPolicy(
        speaker_id=speaker_id,
        reviewed=reviewed,
        rejected=rejected,
        in_warmup=in_warmup,
        sampling=sampling,
    )


def sampled_in(clip_id: str, fraction: float) -> bool:
    """Deterministic per-clip sampling.

    Hashing the clip id rather than drawing randomly means the same clip is
    always either in or out of the sample. A reviewer who reloads the page does
    not get a different set, and the queue does not slowly leak clips that a
    random draw kept skipping.
    """
    if fraction >= 1.0:
        return True
    if fraction <= 0.0:
        return False
    digest = hashlib.sha256(clip_id.encode()).digest()
    bucket = int.from_bytes(digest[:4], "big") / 0xFFFFFFFF
    return bucket < fraction


def _contested_prompts(db: Session, lang: str) -> set[str]:
    """Prompts that have already been rejected by someone.

    A sentence several people misread is usually an ambiguous sentence, and the
    fastest way to see that is to review its readings near each other.
    """
    rows = db.execute(
        select(Clip.prompt_id)
        .where(
            Clip.lang == lang,
            Clip.verify_status == "rejected",
            Clip.tombstoned.is_(False),
        )
        .group_by(Clip.prompt_id)
    ).all()
    return {r[0] for r in rows}


def next_batch(
    db: Session, settings: Settings, lang: str = "ne", count: int = 10
) -> list[Clip]:
    """The next `count` clips to review, already ordered and de-clustered."""
    # Only clips that passed automated QC are worth a human's attention: a clip
    # that failed on noise is being re-recorded anyway.
    candidates = db.scalars(
        select(Clip)
        .join(Speaker, Clip.speaker_id == Speaker.id)
        .where(
            Clip.lang == lang,
            Clip.qc_status == "passed",
            Clip.verify_status == "unverified",
            Clip.tombstoned.is_(False),
            Speaker.withdrawn_at.is_(None),
        )
        # Pull a wide slice so sampling and alternation have room to work.
        .order_by(Clip.review_priority.desc(), Clip.created_at)
        .limit(max(count * 20, 200))
    ).all()

    if not candidates:
        return []

    contested = _contested_prompts(db, lang)
    policies: dict[str, SpeakerPolicy] = {}
    selected: list[Clip] = []

    for clip in candidates:
        policy = policies.get(clip.speaker_id)
        if policy is None:
            policy = speaker_policy(db, clip.speaker_id, settings)
            policies[clip.speaker_id] = policy

        if policy.sampling and not sampled_in(
            clip.id, settings.review_sample_fraction
        ):
            continue
        selected.append(clip)

    # Contested prompts first, then ASR uncertainty, then oldest.
    selected.sort(
        key=lambda c: (
            0 if c.prompt_id in contested else 1,
            -(c.review_priority or 0),
            c.created_at,
        )
    )

    return _spread_speakers(selected, count)


def _spread_speakers(clips: list[Clip], count: int) -> list[Clip]:
    """Avoid consecutive clips from one speaker, preserving order otherwise.

    Greedy: take the best-ranked clip whose speaker differs from the previous
    one; if every remaining clip is from that speaker, accept the repeat rather
    than dropping clips from the batch.
    """
    remaining = list(clips)
    out: list[Clip] = []
    last_speaker: str | None = None

    while remaining and len(out) < count:
        pick = next(
            (c for c in remaining if c.speaker_id != last_speaker),
            remaining[0],
        )
        remaining.remove(pick)
        out.append(pick)
        last_speaker = pick.speaker_id

    return out
