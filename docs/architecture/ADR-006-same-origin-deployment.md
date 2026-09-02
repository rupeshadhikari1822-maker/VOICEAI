# ADR-006 — Same-origin deployment

**Status:** Accepted. Roadmap §6 is deferred with a named trigger.

## Context

The system has two web surfaces: a static marketing landing page, and the
recording studio. They have completely different requirements — the landing page
is static and cacheable, the studio is a stateful Python process that needs
microphone access, a database and object storage.

## Decision

- **`voice.cloudfrm.ai`** — the landing page. Static, on Vercel. Links across.
- **`record.cloudfrm.ai`** — this application. FastAPI serves the recorder UI
  from its own origin, behind Caddy on a VPS.

The recorder's HTML, JS and API all come from one origin. There is no CORS in
the path between the browser and the API.

### Differs from roadmap §6

§6 splits frontend and API across subdomains — `app.` and `api.`, or similar.

**The cost of splitting is specific and it lands in the worst possible place.**

Every API call would become cross-origin, including the upload flow. And a CORS
failure in `fetch` is uniquely opaque: the spec deliberately hides cross-origin
response detail, so a rejected preflight surfaces as a bare `TypeError` with no
status and no message. It is indistinguishable from a network failure without a
second control request to disambiguate — which is exactly the workaround
`static/recorder/preflight.js` already has to implement for the **one**
cross-origin request that genuinely cannot be avoided: the direct-to-bucket PUT.

Adding CORS to the rest of the API means adding that ambiguity to every call, in
a system whose users are on mobile data in a country with intermittent
connectivity, where "is it CORS or is it the network" is a question you cannot
ask a contributor to help you answer.

There is one cross-origin request in the design. That is the correct number
until something forces otherwise.

**Deferred, with triggers:** revisit when there is a dedicated frontend team who
need to deploy independently, or a second client (a mobile app, a partner
integration) that consumes the API without the bundled UI. Neither exists.

## Consequences

- The recorder is served by the same process that handles its API. At two
  uvicorn workers this is comfortable, because audio never passes through the
  process — the browser PUTs straight to the bucket.
- HTTPS is mandatory, not optional: `getUserMedia` requires a secure context.
  The production guard refuses to boot on a non-https `PUBLIC_BASE_URL`.
- `PUBLIC_BASE_URL` must match the URL contributors actually open. A mismatch
  makes presigned local-upload URLs point at the wrong host — uploads then work
  from the VPS and fail from phones, which is a miserable thing to debug.
- Bucket CORS is still required, for the one direct-to-bucket PUT and for review
  playback. See `docs/operations/deployment.md` step 3.

## Enforced by

- `app/core/config.py` production guard — https-only `PUBLIC_BASE_URL`
- `tests/test_deploy_guard.py::test_production_refuses_plain_http`
- `scripts/check_deployment.py` — TLS, redirect, HSTS
