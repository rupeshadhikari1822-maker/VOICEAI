"""Supabase Auth verification.

Login/signup and Google sign-in happen entirely on the frontend via Supabase
Auth; the API never sees a password or an OAuth token. What it sees is the JWT
Supabase issues afterwards, in `Authorization: Bearer <jwt>`.

Supabase now signs those tokens with a per-project ES256 key pair (its "JWT
Signing Keys" system), not the older shared HS256 secret -- so verification
here means fetching Supabase's public key set (JWKS) and checking the token's
signature against it, never a shared secret. The JWKS endpoint is public by
design (it hands out public keys), so this needs no credential and never
calls out to Supabase on any OTHER part of the request path -- `PyJWKClient`
caches the keys after the first fetch.

This is a distinct trust boundary from `app/core/security.py` (reviewer
tokens): reviewers are trusted staff on a shared token; this is the public,
per-account identity used only to link a speaker profile to whoever created
it. The account id is opaque like `speaker_id` -- treat it the same way: never
log it next to a name, never put it in an object key.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

import jwt

from app.core.config import get_settings


@dataclass(frozen=True)
class AuthUser:
    id: str  # Supabase auth user id (uuid).
    email: str | None


class AuthError(Exception):
    """Raised when a bearer token is absent, expired, or does not verify."""


@lru_cache(maxsize=1)
def _jwks_client() -> jwt.PyJWKClient:
    settings = get_settings()
    if not settings.supabase_url:
        raise AuthError("accounts are not configured: set SUPABASE_URL")
    jwks_url = f"{settings.supabase_url.rstrip('/')}/auth/v1/.well-known/jwks.json"
    return jwt.PyJWKClient(jwks_url)


def decode_supabase_jwt(token: str | None) -> AuthUser:
    if not token:
        raise AuthError("missing session token")

    try:
        signing_key = _jwks_client().get_signing_key_from_jwt(token)
        claims = jwt.decode(
            token,
            signing_key.key,
            algorithms=["ES256"],
            audience="authenticated",
        )
    except jwt.PyJWTError as exc:
        raise AuthError(f"invalid session: {exc}") from exc

    sub = claims.get("sub")
    if not sub:
        raise AuthError("token has no subject")
    return AuthUser(id=sub, email=claims.get("email"))
