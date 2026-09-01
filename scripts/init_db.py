#!/usr/bin/env python
"""Create the database schema. Safe to re-run."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts._console import use_utf8  # noqa: E402

from app.config import get_settings  # noqa: E402
from app.db import create_all, engine  # noqa: E402


def main() -> int:
    use_utf8()
    settings = get_settings()
    create_all()
    print(f"schema ready: {engine.url}")
    if settings.storage_backend == "local":
        Path(settings.local_storage_dir).mkdir(parents=True, exist_ok=True)
        print(f"local storage: {settings.local_storage_dir}")
    else:
        print(f"storage: s3 bucket {settings.s3_bucket} @ {settings.s3_endpoint_url}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
