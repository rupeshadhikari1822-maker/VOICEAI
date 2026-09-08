from __future__ import annotations

from pydantic import BaseModel


class AdminLoginIn(BaseModel):
    email: str
    password: str


class AdminLoginOut(BaseModel):
    token: str
    reviewer: str
