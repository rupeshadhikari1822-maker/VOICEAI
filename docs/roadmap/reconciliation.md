# Roadmap reconciliation

Maps [cloudfarm-vision.md](cloudfarm-vision.md) — the 72-section "CloudFARM
Voice Studio" plan — against what is actually built.

**Check this table before implementing anything from the roadmap.** Several
sections describe approaches that were considered and deliberately rejected;
following them literally would damage the corpus in ways the section text does
not reveal.

## Three tiers

This table separates what blocks the first real recording from work that can
land later. Use this framing when reporting status: a flat list makes a broken
storage credential look equivalent to a future GPU integration, and they are
not the same kind of problem.

### Tier 1 -- blocks the pilot

Nothing works without these. Finish these before calling MVP-01 complete.

| Item | Status | Proof needed |
|---|---|---|
| Production storage credentials | **Open** | Confirm the Access Key ID in `/srv/voice/.env` belongs to a key that has the `voice-corpus` bucket attached with Read/Write permission in the provider panel. If the key is unscoped, create a new scoped key and enter the new ID and secret together. Then run `python scripts/verify_storage_credentials.py` on the deployed host so the live credentials perform a real PUT, GET and DELETE against the bucket. `check_deployment.py` alone is not proof: presigning is local cryptography and can pass with bad credentials. |
| Bucket CORS | **Open** | Confirm the actual provider from `S3_ENDPOINT_URL`, then add CORS allowing `PUT` and `GET` from `https://record.cloudfrm.ai` with `content-type` allowed. Python cannot verify CORS because browsers enforce it; do not report this done from a server-side check. |
| Real phone recording | **Open** | Rupesh must use an Android phone on mobile data, open `https://record.cloudfrm.ai`, screenshot the mic-check screen, record one full sentence, submit it, and confirm the review flow can play the landed object with correct metadata. This is the end-to-end proof. |

### Tier 2 -- land before the pilot, does not block starting it

Cheap, real improvements. Do these after Tier 1 is proven, not instead of it.

| Item | Status | Notes |
|---|---|---|
| Consent page Markdown rendering | **Done** | The recorder renders `docs/consent-ne.md` as presentable HTML while the server still hashes the exact Markdown text. |
| Rate limiting | **Open** | Add limits for `POST /api/speakers` and `POST /api/clips/init` before a public link. |
| Session recovery on refresh | **Open** | Persist `session_id` and current prompt index client-side. This is not sensitive data, and it prevents losing a volunteer's in-progress session. |
| Retention policy | **Open** | Decide and document raw audio, PII and rejected-clip retention in `docs/consent-ne.md` with Rupesh's explicit sign-off, because the consent hash changes. |
| Backup confirmation | **Open** | Run `scripts/backup_corpus.py` for real against production storage and keep the output. Fixture tests are not a production backup check. |

### Tier 3 -- do not touch until Tier 1 has run against real speakers

These are explicitly out of scope for the current job. If they appear while
fixing Tier 1 or Tier 2, record them as dependencies instead of building them.

| Item | Status | Boundary |
|---|---|---|
| Admin dashboard, research dashboard, full RBAC, Docker/GitHub Actions, Redis/queue architecture, FFmpeg async pipeline, ASR/TTS training, CloudFARM GPU integration, RAG, Himalaya Voice Engine, dataset versioning beyond current exports, staging environment | **Deferred** | Do not start without an explicit new task after Tier 1 has been phone-verified. |

## Status meanings

| Status | Meaning |
|---|---|
| **Built** | Implemented. The roadmap and the code agree. |
| **Deviated** | Deliberately done differently. An ADR says why. **Do not "fix" toward the roadmap.** |
| **Partial** | Some of it exists. What is missing is named. |
| **Deferred** | Correct not to have yet. A trigger condition names when to revisit. |
| **Gap** | The roadmap is right and the code is missing it. |

All 72 sections are reviewed below.

---

## 1–10 · Objective, architecture, participants

| § | Topic | Status | Notes |
|---|---|---|---|
| 1 | Executive objective (19 capabilities) | **Partial** | 1–13 built. 14 (versioned datasets) is a Gap, see §29. 15–19 (GPU export, training, voice engine, RAG) deferred — no ML code in this repo. |
| 2 | Six-layer architecture | **Partial** | UI → FastAPI → Postgres + object storage → QC → dataset generation all exist. No queue layer (§55), no FFmpeg/VAD stage (§20), no GPU/RAG layers. |
| 3 | Next.js + **MediaRecorder API** | **Deviated** | [ADR-001](../architecture/ADR-001-audio-capture.md). MediaRecorder yields WebM/Opus — lossy at capture, unrecoverable. **Do not adopt.** Frontend is dependency-free vanilla JS, not Next.js; the recorder is five files and a framework would not earn its bundle. |
| 4 | FastAPI backend, signed upload URLs, audio not through the API | **Built** | Exactly as specified. `clips/init` → presigned PUT → direct-to-bucket. Audit logging is **Partial** (§52). |
| 5 | DigitalOcean: Ubuntu, Nginx, Docker, Worker, Redis | **Partial** | Ubuntu + FastAPI + Postgres + object storage built. **Caddy instead of Nginx** — automatic TLS, and certificate renewal is the failure mode that actually bites. No Docker, no Redis, no worker: nothing is asynchronous yet. |
| 6 | Three environments; `api.voice.cloudfrm.ai` split | **Deviated** | [ADR-006](../architecture/ADR-006-same-origin-deployment.md). One origin: `record.cloudfrm.ai` serves UI and API; `voice.cloudfrm.ai` stays the Vercel landing page. Splitting puts CORS ambiguity in every call rather than one. **Staging is a Gap** — there is no staging environment. |
| 7 | Monorepo `frontend/ backend/ audio_pipeline/ ml/` | **Deferred** | [ADR-004](../architecture/ADR-004-repository-structure.md). **Trigger:** when ML training code exists in this repo. |
| 8 | Invitation link `/session/XXXXXXXX` | **Deviated** | No session token in the URL. A contributor opens `record.cloudfrm.ai` and registers; the session is created server-side after consent. Campaign scoping does not exist yet — see §24. Honours the underlying rule: no internal database IDs are exposed (ULIDs, [ADR-005](../architecture/ADR-005-speaker-identifiers.md)). |
| 9 | Participant fields | **Partial** | Built: age band, gender, province, district, municipality, ward, mother tongue, language variety, education, name/email/phone. **Not collected:** profession, additional languages, urban/rural, years speaking. Deliberate — every field is a thing to store, protect and justify. |
| 10 | Caste handling | **Built** | Implemented exactly as written: optional, "prefer not to say", stored separately, access-controlled, **never in training metadata**. [ADR-003](../architecture/ADR-003-consent-model.md). The identity ≠ research ≠ training distinction is enforced by `Speaker.export_row()` being an allow-list. |

## 11–20 · Identity, consent, recording, storage

| § | Topic | Status | Notes |
|---|---|---|---|
| 11 | `SPK-000001` sequential IDs | **Deviated** | [ADR-005](../architecture/ADR-005-speaker-identifiers.md). Sequential IDs leak corpus size and invite enumeration. ULIDs instead. If readable IDs are wanted for research conversations, add a display alias — do not change the primary key. |
| 12 | Consent version, timestamp, status, scope; never bare `consent = true` | **Built, exceeded** | Plus the **server-computed SHA-256 of the exact text shown**, which the roadmap does not ask for and which is what makes the record evidence. `campaign_id` is absent (no campaigns yet). |
| 13 | Recording studio interface | **Built** | One sentence at a time, level meter, timer, playback, submit. Multi-language ready via the `lang` field; only `ne` prompts are active. |
| 14 | Recording instructions | **Built** | [recording-guide.md](../collection/recording-guide.md), Nepali-first. **Deviation:** 15–20 cm rather than 10–20 cm, and slightly off-axis, because plosives hitting the capsule are the most common avoidable defect. Bluetooth is explicitly rejected, which the roadmap does not mention. |
| 15 | Recording behaviour and auto-detection | **Built** | All eight conditions detected except **multiple speakers**, which needs diarisation — a Gap, low priority for read-aloud prompts. |
| 16 | **16 kHz archival**, optional 24-bit/48 kHz master | **Deviated** | [ADR-002](../architecture/ADR-002-storage-and-formats.md). 48 kHz/16-bit is the *mandatory* master, not an optional extra. 16 kHz archival inverts an irreversible direction: you can downsample forever, you can never restore. 24-bit is not useful — browsers deliver Float32 and the room noise floor sits far above the 16-bit floor. |
| 17 | `raw/ processed/ validated/ rejected/ datasets/ exports/ backups/` | **Deviated** | Three prefixes: `raw/`, `derived/`, `consent/`. `processed`/`validated`/`rejected` are **row states, not directories** — a clip's status changes without moving bytes, and moving audio between prefixes to represent a status change is how objects get orphaned. |
| 18 | `NP_SPK000001_UTT000001.wav` | **Deviated** | Keys are `raw/{lang}/{speaker_ulid}/{session}/{clip}.wav`. Follows the roadmap's own rule — metadata belongs in the database, not the filename — more strictly than its example does. |
| 19 | Per-utterance metadata | **Partial** | Built: everything except `campaign_id`, `dialect` (folded into `language_variety`), `quality_score` (§22), `processing_version`, `dataset_version` (§29). |
| 20 | UPLOAD → FFmpeg → VAD → QC → ASR → score | **Deviated** | QC runs **synchronously** on `clips/complete`, in-process, from the stored bytes. No FFmpeg (the browser already emits canonical WAV, so there is nothing to normalise), no VAD library (frame-energy speech-span detection in `audio_qc/metrics.py`), ASR is a separate batch pass (§46). Revisit if QC latency becomes visible to contributors. |

## 21–30 · Quality, scripts, datasets

| § | Topic | Status | Notes |
|---|---|---|---|
| 21 | Quality metrics | **Built** | Duration, silence ratio, RMS, peak, clipping ratio, SNR, voice activity, transcript consistency — all present. |
| 22 | 0–100 quality score with bands | **Deviated** | Pass/fail plus **machine-readable failure codes** (`snr_low`, `clipping`, `too_quiet`…). A composite score hides *which* thing was wrong, and the contributor needs to be told what to physically change. Thresholds are configurable via `Settings`, as §22 requires. |
| 23 | Never auto-delete raw data | **Built** | Failed clips keep their row and object. Withdrawal is the only deletion path, and it tombstones rather than dropping rows. |
| 24 | Script management admin UI, campaigns | **Partial** | `prompts` table with id, lang, category, tags, source, active. **No admin UI** — `import_prompts.py` and `prompt_health.py` are CLI. **No campaign concept.** Trigger: a second collection round with different sentence sets. |
| 25 | Script categories (banking, health, government…) | **Gap** | 50 seed sentences chosen for *phonetic* coverage, not domain coverage. The `category` field exists and is unused beyond coarse labels. Real gap for voice-bot training. **Trigger:** after the pilot, driven by the intended bot domain. |
| 26 | Language / script / dialect / locale taxonomy | **Partial** | `lang` + `language_variety` + `script` exist. No structured taxonomy, and — per the roadmap's own caution — that should be set by linguists, not invented here. Unreviewed languages import **inactive**, which the roadmap does not specify and which prevents machine-translated prompts reaching a contributor. |
| 27 | Datasets A (ASR) / B (TTS) / C (speaker research) | **Built** | `export_dataset.py --format asr|tts|hf|ljspeech`. Dataset C is served by the same export plus speaker metadata; it is not a separate artefact. |
| 28 | Machine-readable manifests, JSONL/CSV/Parquet | **Partial** | JSONL manifest + per-split JSONL + CSV for HF/LJSpeech. **No Parquet.** Trivial to add when something needs it. |
| 29 | Dataset versioning (`Nepali-ASR-v1.0`) | **Gap** | Real gap. Exports are ad hoc directories; nothing records a version, and nothing prevents overwriting. `DATASET_CARD.md` captures split seed, counts and provenance — the ingredients of a version, without the version. **Trigger:** before the first export handed to anyone outside the team. |
| 30 | Speaker-level splits, no leakage | **Built** | `assign_splits()` assigns whole speakers, never clips. Asserted in `tests/test_smoke.py`, and every export writes a speaker-disjointness check into its card. |

## 31–40 · ML, dashboards, security

| § | Topic | Status | Notes |
|---|---|---|---|
| 31 | ML pipeline / model registry | **Deferred** | No ML code in this repo. **Trigger:** enough usable hours to train against — realistically after §65. |
| 32 | CloudFARM GPU integration | **Deferred** | Same trigger. The export side is built; nothing consumes it yet. |
| 33 | RAG architecture | **Deferred** | Different system. This repo produces the corpus that would feed it. |
| 34 | Nepali-first architecture | **Built** | Every contributor-facing string is Nepali-first with English in parentheses. Language codes throughout. Error messages name the physical fix, in Nepali. |
| 35 | Romanized Nepali input | **Deferred** | **Trigger:** when prompts come from contributor-submitted text rather than a curated set. The normaliser in `review/normalize.py` already does NFC and Devanagari-digit folding, which is the groundwork. |
| 36 | Admin dashboard | **Gap** | No web dashboard. `qc_report.py` gives the same numbers on a terminal. **Trigger:** when someone who is not comfortable with a shell needs the numbers. |
| 37 | Research dashboard / query-driven dataset builder | **Gap** | `export_dataset.py` takes `--lang`, `--min-snr`, `--verified-only`, `--limit`. No UI, no arbitrary metadata queries. **Trigger:** a researcher outside the build team. |
| 38 | Security architecture | **Partial** | Built: HTTPS, security headers, CORS restriction, signed upload/download URLs, env secrets, no secrets in Git, size limits, HSTS, `noindex`. **Missing: rate limiting** on `/api/speakers` and `/api/clips/init` — a real gap before a public link. Also no MIME/malware validation beyond WAV decoding, and no encrypted-backup story. |
| 39 | Eight RBAC roles | **Gap** | Only reviewer tokens exist (staff-grade, named, not an identity system). The roadmap's principle — a reviewer should not see contact details — **is** honoured: the review API never returns PII. **Trigger:** a reviewer who is not already trusted with the database. |
| 40 | Privacy-by-design, PII ≠ ML dataset | **Built** | `Speaker.export_row()` is a seven-field allow-list; caste is unreachable from it. Asserted by `test_export_row_contains_no_pii`. |

## 41–50 · Retention, resilience, corpus balance

| § | Topic | Status | Notes |
|---|---|---|---|
| 41 | Data retention policy | **Gap** | No retention policy, and no automatic expiry of anything except `_preflight/` probes. The roadmap is right that this should be defined **before** collecting at volume. **Trigger: before the pilot** — this is a policy decision, not code. |
| 42 | Session state machine | **Partial** | `qc_status` (pending/passed/failed) + `verify_status` (unverified/verified/rejected) cover the meaningful states. The full nine-state machine is not modelled; UPLOADING and PROCESSING are transient and would add rows without adding information. |
| 43 | Failure recovery (9 conditions) | **Partial** | Handled: permission denial, upload failure, duplicate submission (fresh clip id per take), server timeout, mic disconnect (surfaced by the watchdog). **Not handled: browser refresh and session expiry lose the in-progress session** — a real gap, and the fix is resumable signed links. **Trigger: before the pilot.** |
| 44 | Offline / poor-network upload queue | **Deferred** | The preflight and per-clip retry cover the common case; a full local queue with retry is a significant build. **Trigger:** if pilot data shows upload failures on mobile data. The roadmap's rule — never claim a recording is stored before the server confirms — **is** honoured today. |
| 45 | Recording quality gate before accept | **Built** | All nine conditions checked, server-side, from the stored bytes. |
| 46 | Store expected / ASR / verified transcript | **Built** | `prompt_text` (snapshot at record time), `asr_text`, `asr_cer`. Human verdict lives in `verify_status` plus the `ReviewEvent` trail. |
| 47 | Human review interface | **Built, exceeded** | `/review`, keyboard-driven, with warm-up sampling and speaker de-clustering the roadmap does not mention. **Deviation:** QC score and ASR text are **hidden until after the verdict** — showing them anchors the reviewer. [ADR-007](../architecture/ADR-007-quality-gate-and-review.md). |
| 48 | Dataset quality principles | **Built (as philosophy)** | Diversity over volume is the operating assumption throughout. Measuring it is §50. |
| 49 | Per-speaker and per-campaign quotas | **Gap** | Real gap. Nothing caps contribution; five enthusiastic speakers could dominate the corpus. `qc_report.py` warns when one speaker exceeds 50% of audio — detection, not prevention. **Trigger:** after the 50-speaker pilot, when there is a real distribution to set a cap against. |
| 50 | Corpus balance dashboard | **Gap** | Real gap. No targets for language, dialect, region, age, gender or speaker balance, and nothing steers recruitment. The **data** is collected — `export_row()` carries all six axes — but nothing acts on it. **Trigger:** after the pilot, alongside §49. |

## 51–60 · Operations

| § | Topic | Status | Notes |
|---|---|---|---|
| 51 | Prometheus / Grafana | **Deferred** | Overhead at zero speakers, and the roadmap itself says "when the platform reaches the appropriate scale". **Trigger:** more than one VPS, or an operator who is not the author. |
| 52 | Audit event log | **Partial** | `ReviewEvent` is a genuine append-only audit trail for review decisions. Consent and speaker creation are timestamped rows. There is **no unified audit log** across the twelve named events. **Trigger:** alongside §39 RBAC — audit matters once more than one person can act. |
| 53 | Browser and recording test matrix | **Partial** | 113 automated tests, plus synthetic clean/noisy/clipped/silent/quiet audio cases. **No real-device matrix has been run** — Android/iPhone/Safari/Firefox is unverified, and the AudioWorklet path has never executed in a browser. See [pilot-plan.md](../collection/pilot-plan.md). **This is the largest untested surface in the project.** |
| 54 | Performance targets, asynchronous processing | **Partial** | Upload does not block on processing in the sense that matters — audio goes straight to the bucket. But QC runs synchronously inside `clips/complete`, so the contributor waits for it (tens of milliseconds; acceptable). No progress indicator on upload. |
| 55 | Redis / worker queue | **Deferred** | Nothing currently needs to be asynchronous. ASR is already batch and offline. **Trigger:** if QC latency becomes visible, or FFmpeg/VAD (§20) is adopted. |
| 56 | `/api/v1/...` versioned APIs | **Deviated** | Routes are unversioned. There is one client, shipped from the same origin, deployed together — a version prefix would be ceremony. **Trigger:** a second client, which is the same trigger as §6. |
| 57 | `/health`, `/health/live`, `/health/ready` | **Partial** | Only `/healthz`, which reports process liveness. It does **not** check database, storage or queue — so it can report healthy while uploads fail. `check_deployment.py` covers that externally. Worth extending. |
| 58 | Docker + GitHub Actions → DigitalOcean | **Deviated** | `bootstrap.sh` clones, installs, migrates and restarts; idempotent, re-run to deploy. No Docker, no CI. Deliberate for a single-box pilot — Docker adds a layer to debug at 2am for no current benefit. **Trigger:** a second environment, which is §6's staging gap. |
| 59 | Environment variables | **Built (renamed)** | `STORAGE_*` → `S3_*`, `JWT_SECRET` → `SECRET_KEY`, no `REDIS_URL` or `CORS_ORIGINS` (no queue, one origin). `.env.example` committed, real credentials never. |
| 60 | Backup strategy | **Built** | `backup_corpus.py` copies masters + consent + database and audits rows against objects. Bucket versioning and an offsite copy are documented in [backup-and-restore.md](../operations/backup-and-restore.md) as operator actions. |

## 61–72 · Governance and milestones

| § | Topic | Status | Notes |
|---|---|---|---|
| 61 | IP: participant → dataset → model → commercial rights | **Partial** | The active consent version requires commercial rights assignment for participation and stores that scope on `ConsentRecord`. **Model ownership and downstream licensing are still legal questions, not code ones.** The roadmap's own advice to have the framework reviewed for the jurisdiction stands. |
| 62 | Phases 1–9 | **Partial** | Phase 1 mostly (no Docker, no auth beyond reviewer tokens). Phase 2 fully. Phase 3 partly (§24). Phase 4 differently (§20). Phase 5 as CLI, not dashboard (§36). Phase 6 mostly, minus versioning (§29). Phases 7–9 deferred. |
| 63 | MVP definition | **Built, exceeded** | Every step in the MVP chain works, plus automated QC — which §63 says to add *after* the MVP works. |
| 64 | First pilot: 50 speakers | **Ready, not run** | [pilot-plan.md](../collection/pilot-plan.md). The roadmap's framing — the pilot validates UX and reliability, **not** model training — is adopted verbatim. |
| 65 | Second stage, 200–500 speakers | **Deferred** | **Trigger:** pilot complete and its failure modes closed. |
| 66 | National scale, 5,000–20,000 speakers | **Deferred** | Horizontal scaling needs the queue (§55), staging (§6) and probably the monorepo split (§7). **Trigger:** sustained collection beyond §65. |
| 67 | "Speech data infrastructure, not a voice recorder" | **Built (as principle)** | The nine-element asset definition — speaker, language, dialect, transcript, audio, metadata, consent, quality, dataset version — is complete except **dataset version** (§29). |
| 68 | Final architecture diagram | **Deferred** | Aspirational end state. Present system is the left half. |
| 69 | Immediate build order, steps 1–25 | **Partial** | Steps 1–14 built (differently where an ADR says so). 15–16 differently (§20, §22). 17 built as batch (§46). 18 built. 19 is a Gap (§29). 20–23 deferred. **24 (security/privacy audit) not done** — worth doing before the pilot given §38's rate-limiting gap. 25 is next. |
| 70 | plan → implement → test → inspect → fix → commit | **Built** | Adopted as the working rule in `CLAUDE.md`. Every prohibition in §70's "never" list is honoured; several are enforced by tests rather than convention. |
| 71 | Definition of success | **Not yet** | Requires a real contributor on a real phone. That is the pilot. |
| 72 | MVP-01 acceptance criteria | **Partial** | Met: GitHub, VS Code, participant registration, consent, recording, playback, secure upload, metadata, no secrets in Git. Admin view/play/accept-reject is met by `/review` rather than an admin UI. **Outstanding: DigitalOcean server operational, HTTPS enabled, mobile recording tested, database backup configured.** All four are the current deployment task. |

---

## The honest summary

**Where the roadmap is right and the code is not** — eight genuine gaps, not
rationalised as deviations:

| § | Gap | When |
|---|---|---|
| 41 | No data retention policy | **Before the pilot** — a policy decision |
| 38 | No rate limiting on public endpoints | **Before the pilot** — public link |
| 43 | Browser refresh loses an in-progress session | **Before the pilot** |
| 29 | No dataset versioning | Before the first external export |
| 49 | No per-speaker quotas | After the pilot |
| 50 | No corpus balance targets | After the pilot |
| 25 | No domain script categories | After the pilot |
| 36, 37, 39, 52 | No dashboards, RBAC or unified audit log | When a non-builder needs them |

Also outstanding from §69: **a security/privacy audit (step 24) has not been
done**, and §53's real-device browser matrix has never been run.

## On deviations

Four are load-bearing and must not be reversed: **§3** (MediaRecorder),
**§16** (16 kHz archival), **§11** (sequential IDs), **§6** (split subdomains).
Each has an ADR. The first two would damage the corpus irreversibly and would
look, in a diff, like ordinary spec compliance.

The rest — §17 storage prefixes, §18 naming, §20 pipeline shape, §22 scoring,
§56 API versioning, §58 Docker — are engineering judgement about a
single-box pilot. Revisit them when the triggers fire, not before.

## On deferrals

Every deferral names a trigger. That is the difference between a decision and
an omission. When a trigger fires, the row gets revisited and either built or
re-deferred with a new trigger and a reason — not silently left.
