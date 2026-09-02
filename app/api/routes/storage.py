"""Storage preflight.

`scripts/check_deployment.py` cannot test bucket CORS: CORS is enforced by the
browser, and a presigned PUT from Python succeeds whether or not it is
configured. So a misconfigured bucket passes every server-side check and then
fails on the contributor's very first upload.

Without this, that failure arrives *after* someone has read twenty-five
sentences aloud, and the message they see is indistinguishable from bad wifi.
They conclude their connection is broken, or that they did something wrong, and
you lose both the session and the person.

This endpoint hands the browser a presigned PUT for a ~1 KB probe object. The
recorder performs it as a real cross-origin request at session start, before any
recording happens, and blocks the session with a named error if it fails.

Probe objects go under `_preflight/`, which is outside every export prefix and
carries no contributor data. Set a lifecycle rule on the bucket to expire that
prefix after a day.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter

from app.core.config import get_settings
from app.core.ids import new_ulid
from app.services.storage import LocalStorage, get_storage

logger = logging.getLogger("voice")
router = APIRouter()

# Big enough to be a real body, small enough to be free on any connection.
PROBE_BYTES = 1024
PROBE_PREFIX = "_preflight"


@router.get("/api/storage/preflight")
def storage_preflight() -> dict:
    """A presigned PUT the browser should attempt before recording anything."""
    settings = get_settings()
    storage = get_storage()

    key = f"{PROBE_PREFIX}/{new_ulid()}.bin"
    target = storage.presign_put(key, content_type="application/octet-stream")

    # On the local backend the PUT is same-origin, so it never triggers a CORS
    # preflight and proves nothing about a bucket. Say so rather than letting a
    # green result in development imply the production path is verified.
    same_origin = isinstance(storage, LocalStorage)

    return {
        "url": target.url,
        "method": target.method,
        "headers": target.headers,
        "probe_bytes": PROBE_BYTES,
        "expires_at": target.expires_at,
        # The recorder uses this to distinguish a network failure from a CORS
        # rejection: if the app itself is reachable, the network is fine.
        "control_url": "/healthz",
        "same_origin": same_origin,
        "backend": "local" if same_origin else "s3",
        "environment": settings.environment,
    }
