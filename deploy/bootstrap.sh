#!/usr/bin/env bash
#
# Provision or update record.cloudfrm.ai on a fresh Debian/Ubuntu VPS.
#
#   curl -fsSL https://raw.githubusercontent.com/rupeshadhikari1822-maker/VOICEAI/main/deploy/bootstrap.sh -o bootstrap.sh
#   less bootstrap.sh          # read it before running it as root
#   sudo bash bootstrap.sh
#
# Idempotent: safe to re-run for a deploy. It will not overwrite an existing
# /srv/voice/.env, and it never touches the database except through Alembic.
#
# It deliberately stops before starting the service if .env is still the
# template, because a half-configured public recorder is worse than one that
# is not up yet.

set -euo pipefail

REPO="${REPO:-https://github.com/rupeshadhikari1822-maker/VOICEAI.git}"
BRANCH="${BRANCH:-main}"
APP_DIR="${APP_DIR:-/srv/voice}"
APP_USER="${APP_USER:-voice}"
DOMAIN="${DOMAIN:-record.cloudfrm.ai}"

say() { printf '\n\033[1;36m==>\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m warning:\033[0m %s\n' "$*"; }
die() { printf '\033[1;31m error:\033[0m %s\n' "$*" >&2; exit 1; }

[[ $EUID -eq 0 ]] || die "run as root (sudo bash bootstrap.sh)"

# --- 0. DNS sanity ------------------------------------------------------
# Caddy cannot obtain a certificate until this resolves here. Checking first
# turns a confusing ACME failure into an obvious message.
say "checking DNS for ${DOMAIN}"
if command -v dig >/dev/null 2>&1; then
    resolved="$(dig +short "${DOMAIN}" A | tail -1 || true)"
    public_ip="$(curl -fsS --max-time 10 https://api.ipify.org || true)"
    if [[ -z "${resolved}" ]]; then
        warn "${DOMAIN} does not resolve yet."
        warn "Create the A record pointing at ${public_ip:-this box} and wait for propagation."
        warn "Continuing: everything except the TLS certificate will still install."
    elif [[ -n "${public_ip}" && "${resolved}" != "${public_ip}" ]]; then
        warn "${DOMAIN} resolves to ${resolved}, but this box is ${public_ip}."
        warn "Caddy will fail to get a certificate until that matches."
    else
        echo "  ${DOMAIN} -> ${resolved}  (matches this box)"
    fi
fi

# --- 1. packages --------------------------------------------------------
say "installing packages"
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq \
    python3 python3-venv python3-pip git curl ca-certificates \
    debian-keyring debian-archive-keyring apt-transport-https dnsutils

if ! command -v caddy >/dev/null 2>&1; then
    say "installing Caddy"
    curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' \
        | gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
    curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' \
        > /etc/apt/sources.list.d/caddy-stable.list
    apt-get update -qq
    apt-get install -y -qq caddy
fi

# --- 2. user and code ---------------------------------------------------
if ! id -u "${APP_USER}" >/dev/null 2>&1; then
    say "creating ${APP_USER} user"
    useradd --system --create-home --home-dir "${APP_DIR}" --shell /usr/sbin/nologin "${APP_USER}"
fi
mkdir -p "${APP_DIR}"

if [[ -d "${APP_DIR}/.git" ]]; then
    say "updating code"
    sudo -u "${APP_USER}" git -C "${APP_DIR}" fetch --quiet origin "${BRANCH}"
    sudo -u "${APP_USER}" git -C "${APP_DIR}" reset --hard --quiet "origin/${BRANCH}"
else
    say "cloning ${REPO}"
    # Clone into a temp dir because /srv/voice already exists as the home dir.
    rm -rf /tmp/voice-clone
    git clone --quiet --branch "${BRANCH}" "${REPO}" /tmp/voice-clone
    cp -a /tmp/voice-clone/. "${APP_DIR}/"
    rm -rf /tmp/voice-clone
fi
chown -R "${APP_USER}:${APP_USER}" "${APP_DIR}"

# --- 3. python env ------------------------------------------------------
say "installing python dependencies"
if [[ ! -x "${APP_DIR}/.venv/bin/python" ]]; then
    sudo -u "${APP_USER}" python3 -m venv "${APP_DIR}/.venv"
fi
sudo -u "${APP_USER}" "${APP_DIR}/.venv/bin/pip" install --quiet --upgrade pip
sudo -u "${APP_USER}" "${APP_DIR}/.venv/bin/pip" install --quiet -r "${APP_DIR}/requirements.txt"

# --- 4. configuration ---------------------------------------------------
if [[ ! -f "${APP_DIR}/.env" ]]; then
    say "creating ${APP_DIR}/.env from the template"
    cp "${APP_DIR}/deploy/env.production.example" "${APP_DIR}/.env"
    chown "${APP_USER}:${APP_USER}" "${APP_DIR}/.env"
    chmod 600 "${APP_DIR}/.env"
    # Generate the one secret that has no reason to be chosen by hand.
    generated="$(python3 -c 'import secrets;print(secrets.token_hex(32))')"
    sed -i "s|^SECRET_KEY=CHANGE_ME|SECRET_KEY=${generated}|" "${APP_DIR}/.env"
    echo "  SECRET_KEY generated"
else
    chmod 600 "${APP_DIR}/.env"
    echo "  ${APP_DIR}/.env already exists, left untouched"
fi

# --- 5. system units ----------------------------------------------------
say "installing systemd unit and Caddy config"
install -m 644 "${APP_DIR}/deploy/voice-recorder.service" /etc/systemd/system/voice-recorder.service
install -d -o caddy -g caddy /var/log/caddy
install -m 644 "${APP_DIR}/deploy/Caddyfile" /etc/caddy/Caddyfile
systemctl daemon-reload

# --- 6. refuse to start half-configured ---------------------------------
missing=()
grep -q '^SECRET_KEY=CHANGE_ME' "${APP_DIR}/.env" && missing+=("SECRET_KEY")
grep -q '^STORAGE_BACKEND=s3' "${APP_DIR}/.env" && {
    grep -qE '^S3_ACCESS_KEY_ID=.+' "${APP_DIR}/.env" || missing+=("S3_ACCESS_KEY_ID")
    grep -qE '^S3_SECRET_ACCESS_KEY=.+' "${APP_DIR}/.env" || missing+=("S3_SECRET_ACCESS_KEY")
    grep -qE '^S3_ENDPOINT_URL=https://[^<]' "${APP_DIR}/.env" || missing+=("S3_ENDPOINT_URL")
}

if (( ${#missing[@]} )); then
    cat <<MSG

------------------------------------------------------------------
  Stopping here on purpose. Still to fill in in ${APP_DIR}/.env:

$(printf '    - %s\n' "${missing[@]}")

  A public recorder that is up but misconfigured is worse than one
  that is not up yet: it collects clips it cannot store, or stores
  them somewhere with no backup.

  Edit it, then re-run this script:
      sudo nano ${APP_DIR}/.env
      sudo bash ${APP_DIR}/deploy/bootstrap.sh
------------------------------------------------------------------
MSG
    exit 1
fi

# --- 7. database and prompts -------------------------------------------
say "applying migrations"
sudo -u "${APP_USER}" env -C "${APP_DIR}" "${APP_DIR}/.venv/bin/python" scripts/init_db.py

say "importing prompts"
sudo -u "${APP_USER}" env -C "${APP_DIR}" "${APP_DIR}/.venv/bin/python" \
    scripts/import_prompts.py data/prompts_ne.jsonl

# --- 8. start -----------------------------------------------------------
say "starting services"
systemctl enable --quiet --now voice-recorder
systemctl restart voice-recorder
systemctl reload caddy || systemctl restart caddy

sleep 3
if ! systemctl is-active --quiet voice-recorder; then
    journalctl -u voice-recorder -n 40 --no-pager
    die "voice-recorder failed to start (log above)"
fi

say "local health check"
curl -fsS http://127.0.0.1:8000/healthz && echo

cat <<MSG

------------------------------------------------------------------
  Up. Now verify from a machine that is NOT this one:

      python scripts/check_deployment.py https://${DOMAIN}

  Then record one sentence on a real phone over mobile data. That
  step is not optional: bucket CORS is enforced by the browser, so
  every server-side check passes while a real phone still fails.
------------------------------------------------------------------
MSG
