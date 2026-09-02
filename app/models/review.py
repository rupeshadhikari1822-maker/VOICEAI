"""Append-only review history.

`Clip.verify_status` holds the current state, which is what queries need. This
table holds how it got there, which is what people need months later: who
rejected a clip and when, whether two reviewers agree, and how fast a reviewer
was going when they made a call.

A column that gets overwritten can answer none of those. Nothing here is ever
updated or deleted -- a changed verdict is a new row.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.ids import new_ulid
from app.models.base import Base, utcnow


class ReviewEvent(Base):
    __tablename__ = "review_events"
    __table_args__ = (
        Index("ix_review_events_reviewer_created", "reviewer", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(26), primary_key=True, default=new_ulid)
    clip_id: Mapped[str] = mapped_column(ForeignKey("clips.id"), index=True)
    # A human's name, or "asr:<model>" for an automated decision. Prefixing the
    # machine ones keeps them bulk-revertible and out of agreement statistics.
    reviewer: Mapped[str] = mapped_column(String(80), index=True)
    action: Mapped[str] = mapped_column(String(16))
    reason: Mapped[str | None] = mapped_column(String(32))
    notes: Mapped[str | None] = mapped_column(String(300))
    # How long the reviewer spent before deciding. Under ~2s means they did not
    # listen, and that is worth being able to see.
    time_spent_ms: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)
