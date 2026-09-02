"""SQLAlchemy models, one module per table.

Importing this package registers every mapper, which SQLAlchemy needs before it
can resolve the string targets in `relationship()`. Import models from here
rather than from the individual modules -- `from app.models import Clip` keeps
working exactly as it did before the split.
"""

from __future__ import annotations

from app.models.base import Base, utcnow
from app.models.clip import Clip
from app.models.consent import ConsentRecord
from app.models.prompt import Prompt
from app.models.review import ReviewEvent
from app.models.session import RecordingSession
from app.models.speaker import Speaker

__all__ = [
    "Base",
    "Clip",
    "ConsentRecord",
    "Prompt",
    "ReviewEvent",
    "RecordingSession",
    "Speaker",
    "utcnow",
]
