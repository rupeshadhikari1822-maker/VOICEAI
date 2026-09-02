#!/usr/bin/env python
"""Verify a live deployment from outside it.

    python scripts/check_deployment.py https://record.cloudfrm.ai
    python scripts/check_deployment.py https://record.cloudfrm.ai --deep

Run this from your own machine, not from the VPS. Half of what it checks --
DNS, TLS, the redirect, whether assets are actually reachable -- looks fine
from localhost and is broken from the outside.

**What this cannot check.** Bucket CORS is enforced by the browser, not the
server. A presigned PUT from Python succeeds whether or not CORS is configured,
so every check here can pass while a real phone fails at the first upload. The
only test for that is recording one sentence on a real device over mobile data.
That is why it is a separate step and why it comes before the landing page CTA.

Exit codes: 0 all good, 1 something failed, 2 could not reach the host.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import socket
import ssl
import sys
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import urljoin, urlparse

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from scripts._console import use_utf8  # noqa: E402

TIMEOUT = 20

_PASS, _FAIL, _WARN = [], [], []


def _c(code: str, text: str) -> str:
    return f"\033[{code}m{text}\033[0m" if sys.stdout.isatty() else text


def ok(label: str, detail: str = "") -> None:
    _PASS.append(label)
    print(f"  [{_c('92', 'PASS')}] {label}" + (f"  ({detail})" if detail else ""))


def fail(label: str, detail: str = "") -> None:
    _FAIL.append((label, detail))
    print(f"  [{_c('91', 'FAIL')}] {label}" + (f"  ({detail})" if detail else ""))


def warn(label: str, detail: str = "") -> None:
    _WARN.append((label, detail))
    print(f"  [{_c('93', 'WARN')}] {label}" + (f"  ({detail})" if detail else ""))


def get(url: str, method: str = "GET", headers: dict | None = None,
        data: bytes | None = None, redirect: bool = True):
    """Fetch a URL. Returns (status, headers, body) and never raises on HTTP status."""
    request = urllib.request.Request(url, method=method, data=data,
                                     headers=headers or {})

    class _NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, *_args, **_kwargs):
            return None

    opener = urllib.request.build_opener(
        *([] if redirect else [_NoRedirect])
    )
    try:
        with opener.open(request, timeout=TIMEOUT) as response:
            return response.status, dict(response.headers), response.read()
    except urllib.error.HTTPError as exc:
        return exc.code, dict(exc.headers), exc.read()


# --- 1. DNS and TLS -----------------------------------------------------


def check_dns_and_tls(base: str) -> bool:
    print("\nDNS and TLS")
    host = urlparse(base).hostname or ""

    try:
        addresses = sorted({r[4][0] for r in socket.getaddrinfo(host, None)})
    except socket.gaierror as exc:
        fail(f"{host} resolves", str(exc))
        print(f"\n  {host} does not resolve. Create the A record first;")
        print("  Caddy cannot obtain a certificate until it does.")
        return False
    ok(f"{host} resolves", ", ".join(addresses))

    if urlparse(base).scheme != "https":
        fail("served over HTTPS", "microphone access requires a secure context")
        return True

    try:
        context = ssl.create_default_context()
        with socket.create_connection((host, 443), timeout=TIMEOUT) as sock:
            with context.wrap_socket(sock, server_hostname=host) as tls:
                cert = tls.getpeercert()
        issuer = dict(x[0] for x in cert["issuer"]).get("organizationName", "?")
        ok("TLS certificate is valid", f"issuer {issuer}, expires {cert['notAfter']}")
    except Exception as exc:  # noqa: BLE001
        fail("TLS certificate is valid", str(exc))
        print("\n  Caddy could not get a certificate. Usually DNS was not in place")
        print("  when it first tried; check: journalctl -u caddy -n 50")
        return False

    # A contributor who types the bare hostname must land on HTTPS, or
    # getUserMedia is refused and the app looks broken rather than insecure.
    status, headers, _ = get(f"http://{host}/", redirect=False)
    if status in (301, 302, 307, 308) and headers.get("Location", "").startswith("https"):
        ok("HTTP redirects to HTTPS", f"{status} -> {headers['Location']}")
    else:
        warn("HTTP redirects to HTTPS", f"got {status}")

    return True


# --- 2. the app ---------------------------------------------------------


def check_app(base: str) -> None:
    print("\napplication")

    status, _headers, body = get(urljoin(base, "/healthz"))
    if status == 200 and b'"ok":true' in body.replace(b" ", b""):
        ok("/healthz responds")
    else:
        fail("/healthz responds", f"HTTP {status}")

    status, headers, body = get(base)
    if status != 200:
        fail("recorder page loads", f"HTTP {status}")
        return
    html = body.decode("utf-8", "replace")
    ok("recorder page loads", f"{len(body)} bytes")

    if "Strict-Transport-Security" in headers:
        ok("HSTS header present")
    else:
        warn("HSTS header present", "add it in the Caddyfile")

    # Every asset the page names must load. A 404 on pcm-worklet.js means
    # recording fails at the moment the contributor presses record, which is
    # the worst possible place to discover it.
    assets = sorted(set(re.findall(r'(?:src|href)="(/static/[^"]+)"', html)))
    # audio.js is imported by recorder.js, not referenced in the HTML.
    assets += ["/static/recorder/audio.js", "/static/recorder/pcm-worklet.js"]

    broken = []
    for asset in sorted(set(assets)):
        code, _h, content = get(urljoin(base, asset))
        if code != 200 or not content:
            broken.append(f"{asset} -> {code}")
    if broken:
        fail("all recorder assets load", "; ".join(broken))
    else:
        ok("all recorder assets load", f"{len(set(assets))} files")


# --- 3. configuration ---------------------------------------------------


def check_config(base: str) -> dict | None:
    print("\nconfiguration")

    status, _headers, body = get(urljoin(base, "/api/config"))
    if status != 200:
        fail("/api/config responds", f"HTTP {status}")
        return None
    config = json.loads(body)

    audio = config.get("audio", {})
    if (audio.get("sample_rate"), audio.get("bit_depth"), audio.get("channels")) == (
        48000, 16, 1
    ):
        ok("capture spec is 48 kHz / 16-bit / mono")
    else:
        fail("capture spec is 48 kHz / 16-bit / mono", str(audio))

    consent = config.get("consent", {})
    text = consent.get("text", "")

    if hashlib.sha256(text.encode()).hexdigest() == consent.get("sha256"):
        ok("consent hash matches the served text")
    else:
        fail("consent hash matches the served text")

    if "फेला परेन" in text or len(text) < 1000:
        fail(
            "real consent text is deployed",
            "serving the built-in fallback -- docs/consent-ne.md is missing",
        )
    else:
        ok("real consent text is deployed", f"{len(text)} chars, {consent.get('version')}")

    # Collecting under consent text that differs from the repo's is the one
    # mistake here that cannot be corrected afterwards.
    local = ROOT / "docs" / "consent-ne.md"
    if local.is_file():
        local_hash = hashlib.sha256(local.read_text(encoding="utf-8").encode()).hexdigest()
        if local_hash == consent.get("sha256"):
            ok("deployed consent matches this checkout")
        else:
            warn(
                "deployed consent matches this checkout",
                "the server is serving different consent text than docs/consent-ne.md",
            )

    return config


# --- 4. storage and secrets --------------------------------------------


def check_storage_and_secrets(base: str) -> None:
    print("\nstorage and secrets")

    # The local-upload route only exists on the local backend. A 404 means the
    # deployment is on S3/R2, which is what production must be.
    status, _h, _b = get(
        urljoin(base, "/api/_local_upload?key=probe&expires=1&sig=probe"),
        method="PUT",
        data=b"",
    )
    if status == 404:
        ok("storage backend is S3/R2", "local upload route is absent")
    elif status in (400, 403):
        fail(
            "storage backend is S3/R2",
            "running on STORAGE_BACKEND=local -- clips are on one disk with "
            "no versioning, and every byte flows through this box",
        )
        # Only meaningful on the local backend, where the key actually signs
        # something reachable.
        _check_default_secret(base)
    else:
        warn("storage backend is S3/R2", f"unexpected HTTP {status}")

    status, _h, _b = get(urljoin(base, "/api/review/next"))
    if status == 401:
        ok("/review is gated", "401 without a token")
    elif status == 404:
        warn("/review is gated", "route missing -- deployed code predates the review pass")
    else:
        fail("/review is gated", f"HTTP {status} without a token")

    status, _h, _b = get(urljoin(base, "/openapi.json"))
    if status == 200:
        warn(
            "API schema is public",
            "/openapi.json and /docs are reachable; harmless but it advertises "
            "every endpoint",
        )
    else:
        ok("API schema is not public")


def _check_default_secret(base: str) -> None:
    """If SECRET_KEY is still the repo default, upload URLs can be forged."""
    import hmac
    import time

    key = "dev-insecure-change-me"
    expires = int(time.time()) + 600
    probe = "raw/ne/PROBE/PROBE/PROBE.wav"
    signature = hmac.new(
        key.encode(), f"{probe}:{expires}".encode(), hashlib.sha256
    ).hexdigest()

    status, _h, _b = get(
        urljoin(base, f"/api/_local_upload?key={probe}&expires={expires}&sig={signature}"),
        method="PUT",
        data=b"",
    )
    # 400 "empty body" means the signature was ACCEPTED and only the payload
    # was rejected -- so the default key is live.
    if status == 400:
        fail(
            "SECRET_KEY has been changed",
            "the repo's default key is in use; anyone can forge upload URLs",
        )
    else:
        ok("SECRET_KEY has been changed", "forged signature refused")


# --- 5. optional round trip --------------------------------------------


def check_round_trip(base: str) -> None:
    """Record a synthetic clip against the live deployment.

    Off by default because it writes a real speaker and a real clip into the
    production corpus. It is the only way to confirm prompts are loaded and the
    bucket actually accepts writes.
    """
    print("\nround trip (--deep)")
    try:
        from tests.synth import clean_take
    except ImportError as exc:  # noqa: BLE001
        warn("round trip", f"needs numpy from this checkout: {exc}")
        return

    status, _h, body = get(urljoin(base, "/api/config"))
    version = json.loads(body)["consent"]["version"]

    payload = json.dumps(
        {
            "name": None,
            "mother_tongue": "नेपाली",
            "consent": {"version": version, "accepted": True, "commercial_use": False},
        }
    ).encode()
    status, _h, body = get(
        urljoin(base, "/api/speakers"), method="POST",
        headers={"Content-Type": "application/json"}, data=payload,
    )
    if status != 201:
        fail("create speaker", f"HTTP {status} {body[:200]!r}")
        return
    speaker_id = json.loads(body)["speaker_id"]
    ok("create speaker", speaker_id)

    status, _h, body = get(
        urljoin(base, "/api/sessions"), method="POST",
        headers={"Content-Type": "application/json"},
        data=json.dumps({"speaker_id": speaker_id, "lang": "ne"}).encode(),
    )
    session_id = json.loads(body)["session_id"]

    status, _h, body = get(urljoin(base, f"/api/prompts?session_id={session_id}"))
    prompts = json.loads(body)
    if not prompts:
        fail("prompts are loaded", "no active prompts -- run import_prompts.py")
        return
    ok("prompts are loaded", f"{len(prompts)} served")

    status, _h, body = get(
        urljoin(base, "/api/clips/init"), method="POST",
        headers={"Content-Type": "application/json"},
        data=json.dumps({"session_id": session_id, "prompt_id": prompts[0]["id"]}).encode(),
    )
    init = json.loads(body)

    # Test the path, not the host: on the local backend PUBLIC_BASE_URL may be
    # "localhost" while you probed "127.0.0.1", and a hostname comparison would
    # pass while every byte still flows through the app.
    upload_url = init["upload"]["url"]
    if "/api/_local_upload" in upload_url:
        fail(
            "uploads go straight to the bucket",
            "presigned URL points back at the app -- STORAGE_BACKEND is local",
        )
    else:
        ok("uploads go straight to the bucket", urlparse(upload_url).hostname or "?")

    wav = clean_take()
    status, _h, body = get(
        init["upload"]["url"], method="PUT",
        headers={"Content-Type": "audio/wav"}, data=wav,
    )
    if status not in (200, 201, 204):
        fail("bucket accepts the upload", f"HTTP {status} {body[:200]!r}")
        return
    ok("bucket accepts the upload", f"{len(wav)} bytes")

    status, _h, body = get(
        urljoin(base, f"/api/clips/{init['clip_id']}/complete"), method="POST",
        headers={"Content-Type": "application/json"}, data=b"{}",
    )
    verdict = json.loads(body)
    if verdict.get("passed"):
        ok("server QC ran on the stored bytes", f"SNR {verdict['snr_db']:.0f} dB")
    else:
        fail("server QC ran on the stored bytes", str(verdict.get("codes")))

    print(f"\n  This wrote a real speaker to the corpus. Remove it on the VPS:")
    print(f"      sudo -u voice /srv/voice/.venv/bin/python \\")
    print(f"          scripts/withdraw.py {speaker_id} --confirm")


# --- main ---------------------------------------------------------------


def main() -> int:
    use_utf8()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("url", help="e.g. https://record.cloudfrm.ai")
    parser.add_argument(
        "--deep",
        action="store_true",
        help="record a synthetic clip end to end (writes to the live corpus)",
    )
    args = parser.parse_args()

    base = args.url.rstrip("/") + "/"
    print("=" * 66)
    print(f"  deployment check: {base}")
    print("=" * 66)

    if not check_dns_and_tls(base):
        print("\ncannot continue until the host is reachable over TLS.")
        return 2

    check_app(base)
    check_config(base)
    check_storage_and_secrets(base)
    if args.deep:
        check_round_trip(base)

    print("\n" + "=" * 66)
    print(f"  {len(_PASS)} passed, {len(_FAIL)} failed, {len(_WARN)} warnings")
    for label, detail in _FAIL:
        print(f"    FAIL  {label}" + (f" -- {detail}" if detail else ""))
    for label, detail in _WARN:
        print(f"    WARN  {label}" + (f" -- {detail}" if detail else ""))

    print("\n  Still unverified by this script: bucket CORS.")
    print("  It is enforced by the browser, so everything above can pass while")
    print("  a real phone fails on the first upload. Record one sentence on a")
    print("  real device over mobile data before linking the landing page.")
    print("=" * 66)
    return 1 if _FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
