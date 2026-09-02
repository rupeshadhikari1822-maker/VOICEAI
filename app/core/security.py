"""Reviewer authentication.

Reviewers are trusted staff, not the public, so this is a named shared-token
scheme rather than an identity system: `REVIEWER_TOKENS=alice:tok1,bob:tok2`.

What it does give you is a *name* on every verdict, which is the part that
matters for the data. Attribution is what makes inter-reviewer agreement
measurable and lets a bad reviewing session be found and reverted later. An
anonymous "reviewed: true" cannot be audited or undone.

What it is not: no per-user password, no rotation, no session management, no
audit of who holds which token. Do not reuse it for anything public-facing.
"""

from __future__ import annotations

import secrets

from app.core.config import get_settings


class ReviewAuthError(Exception):
    """Raised when a token is absent, malformed or unknown."""


def reviewer_for_token(token: str | None) -> str:
    """Return the reviewer name for a token, or raise ReviewAuthError.

    Compared with `compare_digest` against every configured token so the time
    taken does not reveal which prefix was correct.
    """
    if not token:
        raise ReviewAuthError("missing reviewer token")

    reviewers = get_settings().reviewers
    if not reviewers:
        raise ReviewAuthError(
            "review is not configured: set REVIEWER_TOKENS=name:token[,name:token]"
        )

    matched: str | None = None
    for name, expected in reviewers.items():
        if secrets.compare_digest(token, expected):
            matched = name

    if matched is None:
        raise ReviewAuthError("unknown reviewer token")
    return matched


def extract_token(authorization: str | None, query_token: str | None) -> str | None:
    """Accept `Authorization: Bearer <tok>` or `?token=<tok>`.

    The query form exists because the review page is opened by pasting a link,
    and because `<audio src=...>` cannot carry a header. It is acceptable here
    only because these are staff tokens on an internal tool.
    """
    if authorization:
        scheme, _, value = authorization.partition(" ")
        if scheme.lower() == "bearer" and value.strip():
            return value.strip()
    return query_token or None
