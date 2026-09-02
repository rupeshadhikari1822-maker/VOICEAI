from __future__ import annotations

from pydantic import BaseModel


class UploadTarget(BaseModel):
    """Where the browser should PUT the bytes, and with which headers.

    Shared by clip uploads and spoken-consent uploads, so it lives here rather
    than in either one.
    """

    url: str
    method: str
    headers: dict[str, str]
