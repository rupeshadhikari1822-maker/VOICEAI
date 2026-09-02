from __future__ import annotations

from pydantic import BaseModel


class PromptOut(BaseModel):
    id: str
    text: str
    lang: str
    category: str | None = None
