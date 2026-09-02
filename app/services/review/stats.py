"""Review throughput and quality aggregates.

Kept out of the route module because these are non-trivial queries with real
judgement baked in -- particularly which events count towards agreement, and
what "too fast" means -- and that judgement should be readable without wading
through HTTP plumbing.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Clip, ReviewEvent
from app.services.review.reasons import ReviewAction

# A verdict faster than this means the reviewer did not listen to the clip.
TOO_FAST_MS = 2000

_SETTLED = (ReviewAction.VERIFIED.value, ReviewAction.REJECTED.value)
# Machine decisions are prefixed so they can be excluded from human statistics.
_MACHINE = "asr:%"


@dataclass
class ReviewStats:
    reviewed_total: int
    reviewed_by_me: int
    pending: int
    rejection_rate: float
    by_reason: dict[str, int]
    median_seconds: float | None
    too_fast: int
    agreement_rate: float | None
    auto_decided: int


def _count(db: Session, model, *where) -> int:
    return db.scalar(select(func.count()).select_from(model).where(*where)) or 0


def collect(db: Session, reviewer: str, lang: str = "ne") -> ReviewStats:
    reviewed_total = _count(db, ReviewEvent, ReviewEvent.action.in_(_SETTLED))
    mine = _count(
        db,
        ReviewEvent,
        ReviewEvent.reviewer == reviewer,
        ReviewEvent.action.in_(_SETTLED),
    )
    pending = _count(
        db,
        Clip,
        Clip.lang == lang,
        Clip.qc_status == "passed",
        Clip.verify_status == "unverified",
        Clip.tombstoned.is_(False),
    )
    rejected = _count(
        db,
        Clip,
        Clip.lang == lang,
        Clip.verify_status == "rejected",
        Clip.tombstoned.is_(False),
    )
    verified = _count(
        db,
        Clip,
        Clip.lang == lang,
        Clip.verify_status == "verified",
        Clip.tombstoned.is_(False),
    )

    by_reason = {
        reason: n
        for reason, n in db.execute(
            select(Clip.reject_reason, func.count())
            .where(Clip.reject_reason.is_not(None), Clip.tombstoned.is_(False))
            .group_by(Clip.reject_reason)
        ).all()
    }

    times = [
        t
        for (t,) in db.execute(
            select(ReviewEvent.time_spent_ms).where(
                ReviewEvent.reviewer == reviewer,
                ReviewEvent.time_spent_ms.is_not(None),
                ReviewEvent.action.in_(_SETTLED),
            )
        ).all()
    ]

    auto_decided = _count(db, ReviewEvent, ReviewEvent.reviewer.like(_MACHINE))
    settled = verified + rejected

    return ReviewStats(
        reviewed_total=reviewed_total,
        reviewed_by_me=mine,
        pending=pending,
        rejection_rate=(rejected / settled) if settled else 0.0,
        by_reason=by_reason,
        median_seconds=(statistics.median(times) / 1000.0) if times else None,
        too_fast=sum(1 for t in times if t < TOO_FAST_MS),
        agreement_rate=agreement_rate(db),
        auto_decided=auto_decided,
    )


def agreement_rate(db: Session) -> float | None:
    """Fraction of multiply-reviewed clips where the human verdicts agreed.

    Only clips judged by two or more *people* count. A human confirming the
    ASR's guess is not independent agreement -- it is the same judgement twice,
    and counting it would make the number look good precisely when the
    pre-filter is wrong.

    Returns None when no clip has two human verdicts, which is the normal state
    until second-opinion sampling exists.
    """
    rows = db.execute(
        select(ReviewEvent.clip_id, ReviewEvent.reviewer, ReviewEvent.action).where(
            ReviewEvent.action.in_(_SETTLED),
            ~ReviewEvent.reviewer.like(_MACHINE),
        )
    ).all()

    by_clip: dict[str, dict[str, str]] = {}
    for clip_id, who, action in rows:
        # Last verdict per reviewer per clip wins.
        by_clip.setdefault(clip_id, {})[who] = action

    contested = [v for v in by_clip.values() if len(v) > 1]
    if not contested:
        return None

    return sum(1 for v in contested if len(set(v.values())) == 1) / len(contested)
