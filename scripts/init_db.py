#!/usr/bin/env python
"""Bring the database up to the current schema. Safe to re-run.

    python scripts/init_db.py
    python scripts/init_db.py --stamp    # existing DB that predates Alembic

This runs `alembic upgrade head`, not `create_all()`. The difference matters:
`create_all()` adds missing *tables* but never adds a *column* to a table that
already exists, so on a database that has already run, a new model field
silently does not exist and every insert fails at runtime with `no such column`.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from scripts._console import use_utf8  # noqa: E402

from app.core.config import get_settings  # noqa: E402
from app.core.db import engine  # noqa: E402

BASELINE = "0001_baseline"


def _alembic_config():
    from alembic.config import Config

    cfg = Config(str(ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(ROOT / "migrations"))
    return cfg


def main() -> int:
    use_utf8()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--stamp",
        action="store_true",
        help="mark an existing pre-Alembic database as being at the baseline, "
        "without replaying the baseline migration over live tables",
    )
    args = parser.parse_args()

    try:
        from alembic import command
    except ImportError:
        print(
            "alembic is not installed. Run: pip install -r requirements.txt",
            file=sys.stderr,
        )
        return 2

    settings = get_settings()
    cfg = _alembic_config()

    if args.stamp:
        command.stamp(cfg, BASELINE)
        print(f"stamped at {BASELINE} (no migrations replayed)")
    else:
        command.upgrade(cfg, "head")
        print(f"schema at head: {engine.url}")

    if settings.storage_backend == "local":
        Path(settings.local_storage_dir).mkdir(parents=True, exist_ok=True)
        print(f"local storage: {settings.local_storage_dir}")
    else:
        print(f"storage: s3 bucket {settings.s3_bucket} @ {settings.s3_endpoint_url}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
