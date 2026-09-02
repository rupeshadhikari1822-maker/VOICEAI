"""Deprecated import path. Use `app.services.storage`.

Kept because scripts and docs referenced `app.storage` before the split.
"""

from app.services.storage import *  # noqa: F401,F403
from app.services.storage import get_storage, reset_storage  # noqa: F401
