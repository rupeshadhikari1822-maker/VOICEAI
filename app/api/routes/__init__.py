"""Parent router: one include per resource module.

Adding a resource means adding a module here and one `include_router` line.
`main.py` never needs to change.
"""

from __future__ import annotations

from fastapi import APIRouter

from app.api.routes import (
    clips,
    consent,
    health,
    prompts,
    review,
    sessions,
    speakers,
)

api_router = APIRouter()

api_router.include_router(health.router, tags=["health"])
api_router.include_router(speakers.router, tags=["speakers"])
api_router.include_router(sessions.router, tags=["sessions"])
api_router.include_router(prompts.router, tags=["prompts"])
api_router.include_router(clips.router, tags=["clips"])
api_router.include_router(consent.router, tags=["consent"])
api_router.include_router(review.router, tags=["review"])

__all__ = ["api_router"]
