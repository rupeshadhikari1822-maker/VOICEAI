#!/usr/bin/env python
"""Verify that configured S3/R2/Spaces credentials really work.

    python scripts/verify_storage_credentials.py

`check_deployment.py` can prove that the app can mint a presigned-looking URL,
but presigning is local cryptography. It does not contact the storage provider,
so it can pass with an unscoped or wrong key. This script performs the missing
network proof using the credentials in the live `.env`: PUT a small object, GET
it back, then DELETE it.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from scripts._console import use_utf8  # noqa: E402

from app.core.config import get_settings  # noqa: E402
from app.core.ids import new_ulid  # noqa: E402
from app.services.storage import get_storage  # noqa: E402


def _masked(value: str | None) -> str:
    if not value:
        return "<unset>"
    if len(value) <= 8:
        return "*" * len(value)
    return f"{value[:4]}...{value[-4:]}"


def main() -> int:
    use_utf8()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--prefix",
        default="_credential_check/",
        help="temporary object prefix; keep it outside raw/, derived/ and consent/",
    )
    args = parser.parse_args()

    settings = get_settings()
    backend = settings.storage_backend.strip().lower()
    if backend != "s3":
        print(f"refusing to run: STORAGE_BACKEND is {settings.storage_backend!r}, not 's3'")
        print("This check is for real object-storage credentials, not local dev storage.")
        return 2

    prefix = args.prefix.strip().lstrip("/")
    if not prefix or prefix.startswith(("raw/", "derived/", "consent/")):
        print("refusing to run: prefix must be outside raw/, derived/ and consent/")
        return 2
    if not prefix.endswith("/"):
        prefix += "/"

    key = f"{prefix}{new_ulid()}.txt"
    payload = f"voice storage credential check {new_ulid()}\n".encode("utf-8")
    storage = get_storage()

    print("storage credential verification")
    print(f"  backend       : {settings.storage_backend}")
    print(f"  endpoint      : {settings.s3_endpoint_url}")
    print(f"  bucket        : {settings.s3_bucket}")
    print(f"  access key id : {_masked(settings.s3_access_key_id)}")
    print(f"  probe key     : {key}")

    try:
        print("  PUT           : ", end="", flush=True)
        storage.put_bytes(key, payload, content_type="text/plain; charset=utf-8")
        print("ok")

        print("  GET           : ", end="", flush=True)
        returned = storage.get_bytes(key)
        if returned != payload:
            print("failed")
            print("downloaded bytes did not match uploaded bytes")
            return 1
        print("ok")

        print("  DELETE        : ", end="", flush=True)
        storage.delete(key)
        print("ok")

        print("  VERIFY DELETE : ", end="", flush=True)
        if storage.exists(key):
            print("failed")
            print("object still exists after delete")
            return 1
        print("ok")
    except Exception as exc:  # noqa: BLE001 - provider SDKs raise many concrete types.
        print("failed")
        print(f"storage error: {type(exc).__name__}: {exc}")
        print(
            "Check that the access key is attached to the bucket with Read/Write "
            "permission. A key with no buckets selected returns the same kind of "
            "failure as a wrong secret."
        )
        return 1

    print("result        : real PUT/GET/DELETE succeeded")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())