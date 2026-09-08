"""Email/password gate in front of the reviewer-token scheme.

`app/core/security.py` deliberately has no per-user password -- reviewers
share a named token. This is a thin, single-account layer on top of it: a
hardcoded operator (ADMIN_EMAIL / ADMIN_PASSWORD_HASH), not a user table.
`POST /api/admin/login` checks these, then hands back whichever token is
configured under the name "admin" in REVIEWER_TOKENS. Everything after login
still goes through the existing reviewer-token check, unchanged.

The plaintext password is never stored -- only a salted scrypt hash. Generate
one with `scripts/set_admin_password.py`.
"""

from __future__ import annotations

import hashlib
import hmac
import os

_SCRYPT_N = 2**14
_SCRYPT_R = 8
_SCRYPT_P = 1
_DKLEN = 32


def hash_password(password: str) -> str:
    """`salt_hex$digest_hex`. Only ever meant to be generated offline and
    pasted into ADMIN_PASSWORD_HASH -- see scripts/set_admin_password.py."""
    salt = os.urandom(16)
    digest = hashlib.scrypt(
        password.encode("utf-8"), salt=salt, n=_SCRYPT_N, r=_SCRYPT_R, p=_SCRYPT_P, dklen=_DKLEN
    )
    return f"{salt.hex()}${digest.hex()}"


def verify_password(password: str, stored_hash: str) -> bool:
    """Constant-time compare against a hash produced by `hash_password`."""
    try:
        salt_hex, digest_hex = stored_hash.split("$", 1)
        salt = bytes.fromhex(salt_hex)
        expected = bytes.fromhex(digest_hex)
    except ValueError:
        return False
    actual = hashlib.scrypt(
        password.encode("utf-8"), salt=salt, n=_SCRYPT_N, r=_SCRYPT_R, p=_SCRYPT_P, dklen=_DKLEN
    )
    return hmac.compare_digest(actual, expected)
