#!/usr/bin/env bash
# =====================================================================
# AI Call System — one-shot setup and runner script.
#
# Usage:
#   ./scripts/setup.sh            # interactive setup
#   ./scripts/setup.sh --core     # core only (no Coqui, no Chatwoot)
#   ./scripts/setup.sh --full     # everything (Coqui + Chatwoot)
#   ./scripts/setup.sh --check    # just check what's installed
# =====================================================================
set -euo pipefail

# ---------- helpers ----------

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"

color() { printf '\033[%sm%s\033[0m' "$1" "$2"; }
ok()    { echo "  $(color '32' '✓') $1"; }
warn()  { echo "  $(color '33' '!') $1"; }
err()   { echo "  $(color '31' '✗') $1"; }
hdr()   { echo; echo "$(color '1;36' "── $1")"; }

# ---------- checks ----------

check_command() {
  local cmd="$1"
  local label="${2:-$cmd}"
  if command -v "$cmd" >/dev/null 2>&1; then
    ok "$label found ($(command -v "$cmd"))"
    return 0
  else
    err "$label NOT FOUND"
    return 1
  fi
}

check_python() {
  if ! command -v python3 >/dev/null 2>&1; then
    err "Python 3 not installed"
    return 1
  fi
  local v
  v=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
  if [[ "$v" < "3.10" ]]; then
    err "Python $v found — need 3.10+"
    return 1
  fi
  ok "Python $v"
}

check_redis_running() {
  if redis-cli -u "${REDIS_URL:-redis://localhost:6379/0}" ping >/dev/null 2>&1; then
    ok "Redis is running"
  else
    warn "Redis is NOT running — start with: redis-server (or docker compose up redis -d)"
  fi
}

check_env_file() {
  if [[ ! -f .env ]]; then
    warn ".env missing — creating from .env.example"
    cp .env.example .env
    ok ".env created. Edit it before running calls!"
  else
    ok ".env exists"
  fi
}

check_ngrok_url() {
  local url
  url=$(grep '^BASE_URL=' .env 2>/dev/null | cut -d= -f2- || true)
  if [[ -z "$url" || "$url" == "https://your-ngrok-subdomain.ngrok.io" ]]; then
    warn "BASE_URL not set in .env — Twilio webhooks will not work"
    warn "  Run:  ngrok http 8000   then update BASE_URL in .env"
  else
    ok "BASE_URL=$url"
  fi
}

check_ozonetel() {
  local key did
  key=$(grep '^OZONETEL_API_KEY=' .env 2>/dev/null | cut -d= -f2- || true)
  did=$(grep '^OZONETEL_DID=' .env 2>/dev/null | cut -d= -f2- || true)
  if [[ -z "$key" || "$key" == "KKxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx" ]]; then
    warn "OZONETEL_API_KEY not configured — real calls will fail"
  elif [[ -z "$did" ]]; then
    warn "OZONETEL_DID not configured — real calls will fail"
  else
    ok "Ozonetel credentials configured (DID=$did)"
  fi
}

# ---------- install ----------

install_core() {
  hdr "Installing core dependencies"
  if [[ ! -d .venv ]]; then
    python3 -m venv .venv
    ok "Created virtualenv at .venv"
  fi
  # shellcheck source=/dev/null
  source .venv/bin/activate
  pip install --upgrade pip --quiet
  pip install -r requirements.txt --quiet
  ok "Core dependencies installed"
}

install_coqui() {
  hdr "Installing Coqui XTTS-v2 (open-source TTS)"
  echo "  This installs PyTorch + Coqui (~2GB total). May take 5–10 minutes."
  read -r -p "  Continue? [y/N] " ans
  if [[ "$ans" != "y" && "$ans" != "Y" ]]; then
    warn "Skipped Coqui install"
    return
  fi

  # ffmpeg must exist for MP3 conversion
  if ! command -v ffmpeg >/dev/null 2>&1; then
    err "ffmpeg not installed. Install it first:"
    echo "       Ubuntu/Debian:  sudo apt-get install ffmpeg"
    echo "       macOS:          brew install ffmpeg"
    return 1
  fi

  # shellcheck source=/dev/null
  source .venv/bin/activate
  pip install -r requirements-tts.txt
  ok "Coqui XTTS-v2 ready (model will download on first use)"

  # Set USE_COQUI_TTS=true in .env if not already
  if ! grep -q '^USE_COQUI_TTS=true' .env; then
    sed -i.bak 's/^USE_COQUI_TTS=.*/USE_COQUI_TTS=true/' .env
    ok "Enabled USE_COQUI_TTS in .env"
  fi
}

install_chatwoot() {
  hdr "Starting Chatwoot (open-source ticketing)"
  if ! command -v docker >/dev/null 2>&1; then
    err "Docker required for Chatwoot. Install Docker Desktop first."
    return 1
  fi
  docker compose --profile chatwoot up -d chatwoot-db chatwoot
  ok "Chatwoot starting at http://localhost:3000 (takes ~30s on first boot)"
  echo
  echo "  Next steps for Chatwoot:"
  echo "    1. Wait ~30 seconds, then open http://localhost:3000"
  echo "    2. Create an admin account (first signup becomes admin)"
  echo "    3. Settings → Inboxes → Add Inbox → API channel"
  echo "       Name: 'AI Call System' — note the Inbox ID shown in URL"
  echo "    4. Profile → Access Token — copy it"
  echo "    5. Update .env:"
  echo "         CHATWOOT_API_TOKEN=<your_token>"
  echo "         CHATWOOT_INBOX_ID=<inbox_id>"
}

# ---------- run ----------

start_redis() {
  if redis-cli ping >/dev/null 2>&1; then
    ok "Redis already running"
    return
  fi
  if command -v docker >/dev/null 2>&1; then
    docker compose up -d redis
    ok "Redis started via Docker"
  else
    warn "Start Redis manually:  redis-server"
  fi
}

run_dev() {
  hdr "Starting development servers"
  cat <<'EOF'

  Open three terminals and run:

    Terminal 1 — API:
        source .venv/bin/activate
        uvicorn app.main:app --reload

    Terminal 2 — Celery worker (retries):
        source .venv/bin/activate
        celery -A app.workers.celery_worker.celery worker --loglevel=info

    Terminal 3 — ngrok (so Twilio can reach your webhooks):
        ngrok http 8000
        # Copy the https://...ngrok.io URL into BASE_URL in .env, then restart Terminal 1.

  Then trigger a test event:
        python -m scripts.send_test_event

EOF
}

# ---------- main ----------

mode="${1:---interactive}"

hdr "Pre-flight checks"
check_python || true
check_command redis-cli "Redis CLI" || true
check_command ngrok "ngrok" || warn "ngrok recommended for local Ozonetel webhooks"
check_command docker "Docker" || warn "Docker recommended (for Chatwoot, Redis)"
check_env_file
check_ngrok_url
check_ozonetel
check_redis_running

case "$mode" in
  --check)
    exit 0
    ;;
  --core)
    install_core
    start_redis
    run_dev
    ;;
  --full)
    install_core
    install_coqui
    install_chatwoot
    start_redis
    run_dev
    ;;
  --interactive|*)
    hdr "Interactive setup"
    echo "  1) core   — minimum (Twilio + ElevenLabs paid only)"
    echo "  2) +coqui — open-source TTS (FREE, replaces ElevenLabs)"
    echo "  3) full   — open-source TTS + open-source ticketing (Chatwoot)"
    read -r -p "  Choose [1/2/3]: " choice
    install_core
    case "$choice" in
      2) install_coqui ;;
      3) install_coqui; install_chatwoot ;;
    esac
    start_redis
    run_dev
    ;;
esac
