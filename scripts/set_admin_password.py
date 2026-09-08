#!/usr/bin/env python
"""Generate (or rotate) the admin dashboard's email/password credentials.

    python scripts/set_admin_password.py you@example.com
    python scripts/set_admin_password.py you@example.com --password "a specific one"

Prints the three .env lines to paste in -- ADMIN_EMAIL, ADMIN_PASSWORD_HASH,
and a REVIEWER_TOKENS entry named "admin" (POST /api/admin/login exchanges the
email/password for whichever token is configured under that exact name). If
--password is omitted, a random one is generated and printed once -- it is
never stored anywhere, only its hash is.

This is a single hardcoded operator account, not a user table -- see
app/core/admin_auth.py.
"""

from __future__ import annotations

import argparse
import secrets
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts._console import use_utf8  # noqa: E402

from app.core.admin_auth import hash_password  # noqa: E402


def main() -> int:
    use_utf8()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("email")
    parser.add_argument(
        "--password",
        default=None,
        help="omit to generate a random one (printed once, below)",
    )
    args = parser.parse_args()

    password = args.password or secrets.token_urlsafe(12)
    password_hash = hash_password(password)
    token = secrets.token_urlsafe(24)

    print(f"email    : {args.email}")
    print(f"password : {password}")
    print("(shown once -- not stored anywhere except your own notes)")
    print()
    print("paste into .env:")
    print()
    print(f"ADMIN_EMAIL={args.email}")
    print(f"ADMIN_PASSWORD_HASH={password_hash}")
    print(f"REVIEWER_TOKENS=admin:{token}")
    print()
    print(
        "(if REVIEWER_TOKENS already lists other reviewers, add"
        f" admin:{token} as one more comma-separated entry rather than"
        " replacing the line)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
