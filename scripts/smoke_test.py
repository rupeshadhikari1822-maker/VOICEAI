#!/usr/bin/env python
"""Run the test suite.

    python scripts/smoke_test.py            # everything
    python scripts/smoke_test.py -k review  # a subset
    python scripts/smoke_test.py -v         # per-test names

The real tests live in `tests/`. This wrapper exists so the command documented
in README.md and SETUP.md keeps working, and so a deployment check has one
obvious thing to run.

Everything runs against a throwaway SQLite file and a temp storage directory, so
it is safe on a production machine and leaves nothing behind.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from scripts._console import use_utf8  # noqa: E402


def main() -> int:
    use_utf8()
    try:
        import pytest
    except ImportError:
        print(
            "pytest is not installed. Run: pip install -r requirements.txt",
            file=sys.stderr,
        )
        return 2

    args = sys.argv[1:] or ["-q"]
    code = pytest.main([str(ROOT / "tests"), *args])

    if code == 0:
        print("\nsmoke test passed")
    else:
        print("\nsmoke test FAILED", file=sys.stderr)
    return int(code)


if __name__ == "__main__":
    raise SystemExit(main())
