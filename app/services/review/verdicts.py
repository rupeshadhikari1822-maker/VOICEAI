"""Recording a verdict, and undoing one.

Every verdict writes two things: the denormalised state on `Clip` (what queries
read) and a `ReviewEvent` (how it got there). They are written in one
transaction, because a clip whose status has no matching event is unauditable and
an event with no matching status is a lie.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.ids import new_ulid
from app.models import Clip, ReviewEvent
from app.services.review.reasons import RejectReason, ReviewAction

# A skip or an unsure is recorded but does not change the clip's status: the
# clip stays in the queue for someone else. Only these two settle it.
_SETTLES = {ReviewAction.VERIFIED, ReviewAction.REJECTED}


class VerdictError(ValueError):
    pass


def record_verdict(
    db: Session,
    clip: Clip,
    reviewer: str,
    action: str,
    reason: str | None = None,
    notes: str | None = None,
    time_spent_ms: int | None = None,
) -> ReviewEvent:
    """Apply a verdict and append its event. Caller commits."""
    try:
        act = ReviewAction(action)
    except ValueError as exc:
        raise VerdictError(f"unknown action: {action!r}") from exc

    if act is ReviewAction.REJECTED:
        if not reason:
            raise VerdictError("a rejection needs a reason")
        try:
            RejectReason(reason)
        except ValueError as exc:
            raise VerdictError(f"unknown reject reason: {reason!r}") from exc
    else:
        # A reason on a non-rejection would be misleading in aggregates.
        reason = None

    event = ReviewEvent(
        id=new_ulid(),
        clip_id=clip.id,
        reviewer=reviewer,
        action=act.value,
        reason=reason,
        notes=(notes or None),
        time_spent_ms=time_spent_ms,
    )
    db.add(event)

    if act in _SETTLES:
        clip.verify_status = act.value
        clip.verified_by = reviewer
        clip.verified_at = datetime.now(timezone.utc)
        clip.reject_reason = reason
        clip.review_notes = notes or None

    return event


def undo_last(db: Session, reviewer: str) -> Clip | None:
    """Revert this reviewer's own most recent settling verdict.

    Scoped to the caller on purpose: undo is for the reviewer who just fat-
    fingered a key, not a way to overwrite a colleague's judgement.

    The undo is itself recorded as a `skipped` event rather than deleting the
    original, so the history stays append-only and a reviewer who keeps undoing
    is visible.
    """
    last = db.scalars(
        select(ReviewEvent)
        .where(
            ReviewEvent.reviewer == reviewer,
            ReviewEvent.action.in_((ReviewAction.VERIFIED, ReviewAction.REJECTED)),
        )
        .order_by(ReviewEvent.created_at.desc(), ReviewEvent.id.desc())
        .limit(1)
    ).first()

    if last is None:
        return None

    clip = db.get(Clip, last.clip_id)
    if clip is None:
        return None

    # Only revert if the clip still carries this reviewer's verdict; if someone
    # else has since re-judged it, leave theirs alone.
    if clip.verified_by != reviewer:
        return None

    prior = _previous_settled_state(db, clip.id, exclude_event_id=last.id)

    if prior is None:
        clip.verify_status = "unverified"
        clip.verified_by = None
        clip.verified_at = None
        clip.reject_reason = None
        clip.review_notes = None
    else:
        clip.verify_status = prior.action
        clip.verified_by = prior.reviewer
        clip.verified_at = prior.created_at
        clip.reject_reason = prior.reason
        clip.review_notes = prior.notes

    db.add(
        ReviewEvent(
            id=new_ulid(),
            clip_id=clip.id,
            reviewer=reviewer,
            action=ReviewAction.SKIPPED.value,
            notes=f"undo of {last.action}",
        )
    )
    return clip


def _previous_settled_state(
    db: Session, clip_id: str, exclude_event_id: str
) -> ReviewEvent | None:
    """The settling verdict before the one being undone, if any."""
    return db.scalars(
        select(ReviewEvent)
        .where(
            ReviewEvent.clip_id == clip_id,
            ReviewEvent.id != exclude_event_id,
            ReviewEvent.action.in_((ReviewAction.VERIFIED, ReviewAction.REJECTED)),
        )
        .order_by(ReviewEvent.created_at.desc(), ReviewEvent.id.desc())
        .limit(1)
    ).first()
