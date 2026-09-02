from __future__ import annotations

from pydantic import BaseModel, Field


class SessionIn(BaseModel):
    speaker_id: str
    lang: str = "ne"
    device_hint: str | None = Field(default=None, max_length=300)
    sample_rate: int | None = None


class SessionOut(BaseModel):
    session_id: str
    lang: str


class ProgressOut(BaseModel):
    speaker_id: str
    session_id: str
    recorded: int
    passed: int
    failed: int
    remaining: int
