"""Sentences to be read aloud."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, utcnow


class Prompt(Base):
    __tablename__ = "prompts"
    __table_args__ = (Index("ix_prompts_lang_active", "lang", "active"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    lang: Mapped[str] = mapped_column(String(16), index=True)
    text: Mapped[str] = mapped_column(Text)
    script: Mapped[str] = mapped_column(String(24), default="Deva")
    category: Mapped[str | None] = mapped_column(String(60))
    phonetic_tags: Mapped[list | None] = mapped_column(JSON)
    source: Mapped[str | None] = mapped_column(String(200))
    # Prompts in an unreviewed language land here as False on purpose: a wrong
    # sentence produces a wrong transcript, which is worse than no data.
    active: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
