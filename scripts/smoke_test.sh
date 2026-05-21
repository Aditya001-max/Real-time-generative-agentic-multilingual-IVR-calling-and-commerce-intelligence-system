#!/usr/bin/env bash
# =====================================================================
# Smoke test — checks that all services respond correctly.
# =====================================================================
set -e

API_URL="${API_URL:-http://localhost:8000}"

color() { printf '\033[%sm%s\033[0m' "$1" "$2"; }
ok()    { echo "  $(color '32' '✓') $1"; }
err()   { echo "  $(color '31' '✗') $1"; exit 1; }

echo "Smoke-testing $API_URL ..."

# 1. Health
curl -fsS "$API_URL/monitoring/health" >/dev/null \
  && ok "API alive" || err "API not responding"

# 2. System health (DB, Redis, Twilio, AI voice, tickets)
SYS=$(curl -fsS "$API_URL/monitoring/system-health")
echo "$SYS" | python3 -c "
import json, sys
d = json.load(sys.stdin)
print('  System status:')
for k, v in d.items():
    print(f'    {k}: {v}')
"

# 3. TTS test (will use whatever backend is configured)
TTS=$(curl -fsS -X POST "$API_URL/monitoring/tts-test" \
  -H 'Content-Type: application/json' \
  -d '{"text":"Hello, smoke test."}')
echo "  TTS test: $TTS"

# 4. Analytics summary
SUMMARY=$(curl -fsS "$API_URL/analytics/summary")
echo "  Analytics: $SUMMARY"

ok "All checks passed"
