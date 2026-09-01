# Setup: GitHub → VS Code → Claude Code

## 1. The repo

The URL originally given (`github.com/rupeshadhikari1822-maker/voice-cloudfrm`)
returns 404 — it does not exist. This code lives in
**`github.com/rupeshadhikari1822-maker/VOICEAI`**, which was already created and
empty.

If you would rather have the `voice-cloudfrm` name, create it on
<https://github.com/new> (private, no README — this folder already has one) and
repoint the remote:

```bash
git remote set-url origin https://github.com/rupeshadhikari1822-maker/voice-cloudfrm.git
git push -u origin main
```

## 2. Push this folder

```bash
cd VOICEAI
git add .
git commit -m "Voice recording studio: recorder, QC, storage, export"
git push -u origin main
```

If GitHub asks for a password, it wants a Personal Access Token
(Settings → Developer settings → Tokens), not your account password.
Or use the GitHub CLI: `gh auth login`, then `git push -u origin main`.

## 3. Open in VS Code

```bash
code .
```

Install the recommended extensions when VS Code prompts (Python, Pylance, Ruff,
Claude Code). Then:

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
python scripts/init_db.py
python scripts/import_prompts.py data/prompts_ne.jsonl
python scripts/smoke_test.py       # should print "smoke test passed"
uvicorn app.main:app --reload
```

Open <http://localhost:8000>. `STORAGE_BACKEND=local` means no cloud account is
needed to try it — files land in `./storage_local/`.

The smoke test runs in its own sandbox (temp SQLite + temp storage directory),
so it never touches your working database and leaves nothing behind.

## 4. Claude Code

```bash
npm install -g @anthropic-ai/claude-code
cd VOICEAI
claude
```

`CLAUDE.md` in the repo root already carries the project rules, so Claude Code
picks up the constraints (uncompressed audio, no PII in keys, speaker-disjoint
splits) automatically.

Useful first prompts:

- `Build a /review page where a second person listens to clips flagged 'passed' and marks them verified or rejected. Follow the rules in CLAUDE.md.`
- `Add resumable sessions: a signed link that lets a speaker return later and continue where they left off.`
- `Add rate limiting to /api/speakers and /api/clips/init.`

## 5. Get a public HTTPS link for testing

Microphone access needs HTTPS. For a quick shareable link while developing:

```bash
cloudflared tunnel --url http://localhost:8000
```

Then set `PUBLIC_BASE_URL` in `.env` to the URL it prints and restart uvicorn —
otherwise the presigned local-upload URLs point at `localhost` and uploads fail
from the contributor's phone.

For production, see `docs/deployment.md`.

## 6. Deploying to voice.cloudfrm.ai

`voice.cloudfrm.ai` currently serves a v0-generated "coming soon" page deployed
straight from v0, with no Git repository behind it. It is not connected to this
code.

To point the domain at this app you need a host that runs a long-lived Python
process — this is a stateful FastAPI server with an AudioWorklet frontend, not a
static site or a set of serverless functions. Any small VPS works; see
`docs/deployment.md` for the systemd unit and Caddy config.
