# AI Call Automation Microservice

Production-ready FastAPI implementation of the **Automated Call System** architecture, with **open-source replacements for paid services** wherever they make sense.

| Layer | Open-source (free) | Paid fallback |
|---|---|---|
| TTS / AI voice | **Coqui XTTS-v2** | ElevenLabs |
| Ticketing | **Chatwoot** | Zendesk / Freshdesk (any HTTP API) |
| Telephony | — | Twilio (no good OSS replacement at low scale) |
| Database | PostgreSQL (self-host) | Managed Postgres |
| Queue | Redis (self-host) | Managed Redis |

You can mix providers — e.g. Coqui as primary, ElevenLabs as fallback.

---

## Quick reference: which command to run

| Goal | Command |
|---|---|
| First-time setup (interactive) | `make setup` |
| Just install dependencies | `make install` |
| Add open-source TTS | `make install-tts` |
| Start the API in dev mode | `make run` |
| Start the retry worker | `make worker` |
| Run tests | `make test` |
| Verify a running system | `make smoke` |
| Start everything in Docker | `make docker-up` |
| Add open-source ticketing | `make chatwoot-up` |
| Stop everything | `make docker-down` |

---

## Step-by-step: running this project from scratch

### 0. Prerequisites

Install on your machine (one-time):
- **Python 3.10+**
- **Redis** (or Docker, which installs Redis automatically)
- **Twilio account** with at least one phone number and trial credit — get from https://www.twilio.com
- **ngrok** for local development — get from https://ngrok.com

If you want **open-source TTS (Coqui)**:
- **ffmpeg** — `sudo apt-get install ffmpeg` (Ubuntu) or `brew install ffmpeg` (macOS)
- ~3 GB free disk space (for PyTorch + the XTTS-v2 model)

If you want **open-source ticketing (Chatwoot)**:
- **Docker** + Docker Compose

### 1. Clone and configure

```bash
git clone <your-repo> ai-call-system
cd ai-call-system

cp .env.example .env
# Edit .env — minimum required:
#   TWILIO_SID, TWILIO_AUTH, TWILIO_NUMBER
```

### 2. Pick your installation depth

**Option A — Cheapest possible (recommended):** Open-source everything that has a real OSS replacement.

```bash
./scripts/setup.sh --full
# Installs: core + Coqui XTTS-v2 + starts Chatwoot
# Total cost: $0 (after Twilio's trial credit) for TTS and ticketing
```

**Option B — Core only:** Twilio for telephony, Twilio's built-in voice, no ticketing system. Good for first-day testing.

```bash
./scripts/setup.sh --core
```

**Option C — Interactive (let the script ask):**

```bash
./scripts/setup.sh
```

### 3. Start the services

The setup script tells you what to run, but here it is explicitly. Open **3 terminals**:

**Terminal 1 — API:**
```bash
source .venv/bin/activate
make run
# API is now at http://localhost:8000  (docs at http://localhost:8000/docs)
```

**Terminal 2 — Celery worker (the retry engine):**
```bash
source .venv/bin/activate
make worker
```

**Terminal 3 — ngrok** (only needed for real Twilio calls):
```bash
ngrok http 8000
# Copy the https://...ngrok.io URL
# Edit .env → set BASE_URL to that URL
# Restart Terminal 1
```

### 4. Verify everything is wired up

```bash
make smoke
```

Expected output:
- `database: ok`
- `redis_configured: True`
- `ai_voice_active_backends: ['coqui']` (or `['elevenlabs']` if you went paid-only)
- `ticket_active_backends: ['chatwoot']` (if Chatwoot is configured)

### 5. Configure Chatwoot (one-time, if you chose the OSS ticketing option)

After `make chatwoot-up`:

1. Open http://localhost:3000 — create your admin account (the first signup is the admin)
2. Settings → Inboxes → **Add Inbox → API channel**
   - Give it a name (e.g. "AI Call System")
   - Note the inbox ID from the URL after creation
3. Profile menu (top-right) → **Profile Settings** → **Access Token** → copy it
4. Update `.env`:
   ```
   CHATWOOT_API_TOKEN=<your_token>
   CHATWOOT_INBOX_ID=<inbox_id>
   ```
5. Restart the API (`make run`)

### 6. Pre-warm the voice cache (optional, recommended)

If you enabled AI voice, generate the static prompts once so the first real call has zero TTS latency:

```bash
python -m scripts.prewarm_voice
# ✓ 13/13 succeeded
```

Note: the first run downloads the XTTS-v2 model (~2GB) from HuggingFace. Subsequent runs are instant.

### 7. Trigger your first test event

```bash
curl -X POST http://localhost:8000/event/ \
  -H "Content-Type: application/json" \
  -d '{
    "order_id": 1001,
    "user_phone": "+919876543210",
    "event_type": "ORDER_PLACED"
  }'
```

If `BASE_URL` is set to your ngrok URL and Twilio is configured, you'll get a real phone call.

---

## How the open-source stack works

### TTS Provider Chain

The chain is configured by `TTS_PROVIDERS` in `.env`:

```
TTS_PROVIDERS=coqui,elevenlabs
```

For every spoken line, the system tries Coqui first. If Coqui is unavailable or crashes mid-synthesis, it falls back to ElevenLabs. If both fail (or both are disabled), it falls back to Twilio's built-in `<Say>` voice — calls never break.

The **cache** is content-addressed: `sha256(text + backend_name + voice_settings)` becomes the filename. Repeat phrases (like the welcome line) are synthesized exactly once and reused forever.

### Ticket Provider Chain

Same pattern via `TICKET_PROVIDERS`:

```
TICKET_PROVIDERS=chatwoot,http
```

Tickets always get persisted to your local DB regardless of whether external creation succeeded. If Chatwoot is up, the conversation is also created there. If Chatwoot is down but you have a paid HTTP fallback configured, that runs instead.

---

## Architecture → Code Map

Every block in the diagram maps to a real module:

| # | Block | File |
|---|---|---|
| 1 | Event Source | External (POST `/event/`) |
| 2 | Event Listener | `app/routes/event.py` |
| 3 | Decision Engine | `app/services/decision_engine.py` |
| 4 | Call Manager | `app/services/call_manager.py` |
| 5 | Retry Engine | `app/workers/retry_tasks.py` |
| 6 | Webhook Handler | `app/routes/webhook.py` |
| 7 | Telephony Provider | `app/services/telephony.py` |
| 8 | IVR Flows | `app/services/ivr_scripts.py` |
| 9 | Action Engine | `app/services/action_engine.py` + `app/services/tickets/` |
| 10 | Data Storage (8 tables) | `app/models/` |
| 11 | Monitoring & Alerts | `app/routes/monitoring.py` |
| 12 | Analytics & Reporting | `app/routes/analytics.py` |
| 13 | RTO Recovery & Excel Sync | `app/routes/rto.py` |
| — | TTS Chain | `app/services/tts/` |
| — | Working Hours | `app/core/working_hours.py` |

---

## IVR flows

**Confirmation Call** (event = `ORDER_PLACED`):
- Press 1 / say "confirm" → updates OMS to CONFIRMED
- Press 2 / say "help" → connects to agent (working hours) or creates a Chatwoot ticket (after hours)

**Rejection Call** (event = `ORDER_REJECTED`):
- Press 1 / say "accept" → updates OMS to RE_ATTEMPT_DELIVERY
- Press 2 / say "cancel" → updates OMS to CANCELLED + creates ticket
- Press 3 / say "help" → agent transfer or ticket

Retries: attempt 1 immediately, then +30 min, +2 h, +24 h. Stops automatically as soon as the user responds.

---

## RTO Recovery & Excel Sync (Block 13)

For e-commerce stores running RTO (Return-to-Origin) recovery campaigns. Three endpoints:

| Endpoint | Purpose |
|---|---|
| `POST /rto/import` | Upload a courier .xlsx of RTO orders → populates `orders` table |
| `GET /rto/redeliveries/export` | Download .xlsx of pending redeliveries → send to courier |
| `GET /rto/insights` | RTO-specific dashboard metrics (working/non-working/beneficial calls, retention, language usage) |

### Flow
1. Courier sends RTO list as Excel (sample at `samples/rto_orders_sample.xlsx`)
2. `POST /rto/import` populates `orders` + creates/updates `users`
3. Your existing `/event/` endpoint with `event_type=ORDER_REJECTED` triggers IVR
4. Customer presses `1` (re-attempt) on the IVR → `action_engine.py` auto-creates a `redeliveries` row + sets order status to `RE_ATTEMPT_DELIVERY`
5. Daily, your team hits `GET /rto/redeliveries/export` to download the Excel of pending redeliveries to send to the courier; rows are marked `exported_to_excel=true` so they don't appear next time

### Sample Excel format
See `samples/rto_orders_sample.xlsx` — 16 columns: `order_id`, `user_phone`, `product_name`, `sku`, `quantity`, `order_value`, `cod_amount`, `payment_mode`, `address`, `city`, `state`, `pincode`, `awb_number`, `courier`, `rto_reason`, `rto_date`.

### Switching to Supabase Pro

The same code runs on SQLite (dev) or Supabase Postgres (prod). To switch:

1. Get your Supabase connection string: **Settings → Database → Connection string → URI** (use Session pooler on port 5432 since Celery holds connections open)
2. Set `DATABASE_URL` in `.env` to that string
3. Restart the app — SQLAlchemy creates the 8 tables automatically
4. Run `supabase/migrations/001_views_triggers_rls.sql` once in the Supabase SQL Editor (adds analytics views, the auto-redelivery trigger, and RLS policies)
5. Done. Same FastAPI code; same Twilio webhooks; data now lives in Supabase.

### Insight queries

Once on Supabase, use these views in the SQL Editor or via your dashboard:

```sql
-- Today's working/non-working/beneficial calls per language
SELECT * FROM v_call_quality_breakdown WHERE call_date = CURRENT_DATE;

-- Top customers worth keeping
SELECT * FROM v_customer_retention
WHERE retention_score > 70 ORDER BY lifetime_value DESC LIMIT 50;

-- Retry engine effectiveness — should you cap retries at 3 instead of 4?
SELECT * FROM v_retry_effectiveness;

-- Which language has highest IVR conversion?
SELECT * FROM v_language_usage;

-- Are after-hours calls worth the cost?
SELECT * FROM v_working_hours_split;
```

---

## Cost comparison

For a system placing **1,000 calls/day** (rough estimate, 2026 prices):

| Setup | TTS | Tickets | Telephony | Total/month |
|---|---|---|---|---|
| All-paid (Twilio + ElevenLabs + Zendesk) | ~$30 | ~$50/agent | ~$300 | $400+ |
| **Hybrid (this project's default)** | $0 (Coqui) | $0 (Chatwoot self-hosted) | ~$300 (Twilio) | **~$300** |

The big savings come from TTS and ticketing. Telephony stays paid because no open-source option is genuinely cheaper at this scale once you account for engineering and ops.

---

## Troubleshooting

**`make run` fails with `ModuleNotFoundError`**
You forgot `source .venv/bin/activate`. Run `make install` first if you haven't.

**Coqui install fails on M1/M2 Mac**
Coqui needs PyTorch with arm64 support. The `coqui-tts` package handles this, but make sure you're on Python 3.10+ and have run `xcode-select --install`.

**Chatwoot won't start**
First boot takes 30+ seconds while it migrates the database. Check `docker compose logs chatwoot`. If it fails repeatedly, the Postgres volume may be stale — run `docker compose --profile chatwoot --profile chatwoot-db down -v` and restart.

**Twilio webhook calls return 502**
Your `BASE_URL` is wrong. Check ngrok is running and the URL in `.env` matches.

**No audio plays during calls**
- If `ai_voice_active_backends` is empty, your TTS is misconfigured — check the system-health endpoint.
- If Twilio falls back to `<Say>` repeatedly, your `BASE_URL` is unreachable from Twilio's servers. ngrok must be live and reachable.
