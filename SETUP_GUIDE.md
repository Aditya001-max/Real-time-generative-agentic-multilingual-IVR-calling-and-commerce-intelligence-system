# Complete Setup Guide — AI Call Automation System

This guide takes you from a fresh machine to a fully running system with Supabase, Twilio, IVR calls, RTO recovery, and Excel sync. Read top to bottom; don't skip steps.

---

## Table of Contents

1. [What you'll have at the end](#what-youll-have-at-the-end)
2. [Prerequisites — install once on your machine](#1-prerequisites)
3. [Get the project files](#2-get-the-project-files)
4. [Create a Supabase project (10 minutes)](#3-create-a-supabase-project)
5. [Create a Twilio account (10 minutes)](#4-create-a-twilio-account)
6. [Configure environment variables](#5-configure-environment-variables)
7. [Install Python dependencies](#6-install-python-dependencies)
8. [Initialize the database](#7-initialize-the-database)
9. [Run the migration in Supabase](#8-run-the-supabase-migration)
10. [Start the API](#9-start-the-api)
11. [Start the Celery retry worker](#10-start-the-celery-worker)
12. [Expose to internet via ngrok (for Twilio)](#11-expose-to-internet-via-ngrok)
13. [Run end-to-end smoke tests](#12-end-to-end-smoke-tests)
14. [Daily workflows](#13-daily-workflows)
15. [Troubleshooting](#14-troubleshooting)
16. [Going to production](#15-going-to-production)

---

## What you'll have at the end

- A FastAPI server on `http://localhost:8000` exposing 4 functional areas:
  - `/event/` — trigger an IVR call when an order is placed or rejected
  - `/webhook/*` — Twilio calls these during a live IVR call
  - `/rto/*` — upload RTO Excel, export pending redeliveries, view insights
  - `/analytics/*` — call-level metrics and Excel export
- A Celery worker that retries failed calls automatically (30 min → 2 hr → 24 hr)
- Supabase Postgres holding 8 tables and 6 analytics views
- Twilio making real outbound calls to real phone numbers
- A multi-language IVR (English, Hindi, Tamil, Telugu, Kannada, Malayalam, Bengali, Marathi, Gujarati)

---

## 1. Prerequisites

Install these on your machine **once**. Skip anything you already have.

### 1.1 Python 3.10 or newer

**Windows:** Download from [python.org/downloads](https://www.python.org/downloads/). During install, check **"Add Python to PATH"**.

**macOS:**
```bash
brew install python@3.12
```

**Ubuntu/Debian:**
```bash
sudo apt update
sudo apt install python3.12 python3.12-venv python3-pip
```

Verify:
```bash
python3 --version
# Should print: Python 3.10.x or higher
```

### 1.2 Redis (for the retry queue)

Redis stores queued retry jobs. Celery reads from it.

**macOS:**
```bash
brew install redis
brew services start redis
```

**Ubuntu/Debian:**
```bash
sudo apt install redis-server
sudo systemctl start redis-server
sudo systemctl enable redis-server
```

**Windows:** The easiest path is Docker (see 1.3) and run `docker run -d -p 6379:6379 redis:7`.

Verify:
```bash
redis-cli ping
# Should print: PONG
```

### 1.3 Docker (optional but recommended)

Used for Chatwoot (open-source ticketing) and for running everything if you don't want to install Python locally.

- Download Docker Desktop from [docker.com](https://www.docker.com/products/docker-desktop/)
- After install, open it once so the daemon starts.

Verify:
```bash
docker --version
# Should print: Docker version 24.x or higher
```

### 1.4 ngrok (for local Twilio testing)

Twilio's servers need to reach your local machine to fire webhooks. ngrok creates a public HTTPS URL that tunnels to localhost.

1. Sign up free at [ngrok.com](https://ngrok.com/)
2. Download the binary for your OS
3. Add it to your PATH
4. Set your auth token (from the ngrok dashboard):
   ```bash
   ngrok config add-authtoken YOUR_TOKEN
   ```

Verify:
```bash
ngrok version
```

### 1.5 Git (to clone repos and version-control your changes)

**Windows:** Download from [git-scm.com](https://git-scm.com/)
**macOS:** `brew install git`
**Ubuntu:** `sudo apt install git`

---

## 2. Get the project files

Unzip the file you received:

```bash
unzip ai-call-system-updated.zip
cd ai-call-system-updated
```

Verify the structure:
```bash
ls
# Should show: app/ samples/ scripts/ supabase/ tests/ Dockerfile Makefile
#              README.md SETUP_GUIDE.md docker-compose.yml requirements.txt
#              .env.example
```

---

## 3. Create a Supabase project

You said you have **Supabase Pro**. Use it.

### 3.1 Create the project

1. Go to [supabase.com/dashboard](https://supabase.com/dashboard)
2. Click **New Project**
3. Fill in:
   - **Name:** `ai-call-system` (or whatever)
   - **Database Password:** generate a strong one and **copy it somewhere safe** — you need it in step 5
   - **Region:** pick the one closest to your users (for India: `Mumbai (ap-south-1)`)
   - **Pricing plan:** Pro
4. Click **Create new project** and wait ~2 minutes for provisioning.

### 3.2 Get the connection string

1. In the Supabase dashboard, go to **Settings** (gear icon, bottom-left) → **Database**
2. Scroll to **Connection string** → click the **URI** tab
3. You'll see two options:
   - **Transaction pooler** (port 6543) — for stateless functions
   - **Session pooler** (port 5432) — **use this one**, because Celery holds connections open
4. Copy the URI. It looks like:
   ```
   postgresql://postgres.abcdefghij:[YOUR-PASSWORD]@aws-0-ap-south-1.pooler.supabase.com:5432/postgres
   ```
5. Replace `[YOUR-PASSWORD]` with the password you set in step 3.1.

### 3.3 Get the API keys (only needed if you'll use Storage later)

1. **Settings → API**
2. Copy three values:
   - `Project URL` (looks like `https://abcdefghij.supabase.co`)
   - `service_role` secret key (long JWT — keep this secret, it bypasses RLS)
   - `anon` public key (only matters if you build a frontend later)

### 3.4 (Optional) Create a Storage bucket for uploaded Excel files

1. **Storage** → **Create a new bucket**
2. Name: `imports`, Public: **off**
3. Click Create

You don't need this immediately — uploaded Excel files are processed in memory and not currently saved to Storage. If you want to keep them for audit, see [Going to production](#15-going-to-production).

---

## 4. Create a Twilio account

Twilio is paid but has a free trial. The trial gives you ~$15 in credits — enough for ~200 test calls.

### 4.1 Sign up and verify

1. Go to [twilio.com/try-twilio](https://www.twilio.com/try-twilio)
2. Sign up, verify your email and phone number.

### 4.2 Buy a phone number

1. In the Twilio Console, **Phone Numbers → Manage → Buy a number**
2. Filter by your country (e.g., India / United States), pick one with **Voice** capability.
3. For Indian numbers there's KYC paperwork — for testing, a US number works fine and can call any country.
4. Click Buy. Cost: ~$1/month for the number itself, ~$0.013/min outbound voice.

### 4.3 Note your credentials

From the Twilio Console **Account Dashboard**:
- **Account SID** (starts with `AC...`)
- **Auth Token** (click to reveal)
- **Phone number** you just bought (e.g. `+15551234567` — full E.164 format with `+` and country code)

### 4.4 (Trial accounts only) Verify the destination number

Twilio trial accounts can only call **verified** phone numbers. Add your own mobile to the verified list:

1. **Phone Numbers → Manage → Verified Caller IDs → Add**
2. Enter your number, get the OTP via SMS, verify.
3. Now you can make test calls to that number.

When you upgrade to a paid plan ($20+ minimum), the verified-caller restriction is lifted and you can call anyone.

---

## 5. Configure environment variables

Copy the template:
```bash
cp .env.example .env
```

Now edit `.env` (use any text editor). Here's a minimum-viable config:

```bash
# ===== Twilio (REQUIRED for real calls) =====
TWILIO_SID=ACxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
TWILIO_AUTH=your_auth_token_here
TWILIO_NUMBER=+15551234567

# Public URL (set this after starting ngrok in step 11; for now leave default)
BASE_URL=http://localhost:8000

# ===== Database =====
# For first-time testing, keep SQLite — runs without any external service:
DATABASE_URL=sqlite:///./db.sqlite3

# For production / your real Supabase, replace with:
# DATABASE_URL=postgresql://postgres.abcdefghij:YourPass@aws-0-ap-south-1.pooler.supabase.com:5432/postgres

# ===== Supabase (only for Storage uploads / future direct client use) =====
SUPABASE_URL=https://abcdefghij.supabase.co
SUPABASE_SERVICE_ROLE_KEY=eyJhbGciOi...long...JWT...
SUPABASE_ANON_KEY=eyJhbGciOi...long...JWT...
SUPABASE_STORAGE_BUCKET=imports

# ===== Redis / Celery =====
REDIS_URL=redis://localhost:6379/0

# ===== Working hours =====
WORKING_HOURS_START=9
WORKING_HOURS_END=18
TIMEZONE=Asia/Kolkata

# ===== AI Voice — start with Twilio's built-in voice for now =====
# Save the open-source TTS setup for later; it requires 3 GB of disk and a model download.
USE_AI_VOICE=false

# ===== Tickets — disable until Chatwoot is set up =====
TICKET_PROVIDERS=none
```

### Two-stage approach (recommended)

**Stage 1 — Get it running on SQLite first.** Use `DATABASE_URL=sqlite:///./db.sqlite3`. No Supabase setup needed yet. Confirm everything works with a real Twilio call.

**Stage 2 — Switch to Supabase.** Once stage 1 works, change `DATABASE_URL` to your Supabase connection string. Restart. Run the migration (step 8). Done.

---

## 6. Install Python dependencies

### 6.1 Create a virtual environment

A virtualenv isolates the project's Python packages from your system Python.

```bash
python3 -m venv .venv
```

Activate it:

**macOS/Linux:**
```bash
source .venv/bin/activate
```

**Windows (Command Prompt):**
```cmd
.venv\Scripts\activate
```

**Windows (PowerShell):**
```powershell
.venv\Scripts\Activate.ps1
```

Your terminal prompt should now start with `(.venv)`.

### 6.2 Install the core packages

```bash
pip install --upgrade pip
pip install -r requirements.txt
```

This installs FastAPI, SQLAlchemy, Twilio SDK, Celery, Redis client, openpyxl, psycopg2 (Postgres driver), and ~10 other packages. Takes 1–2 minutes.

### 6.3 (Optional) Install open-source TTS

Skip this for now if you just want to test. You can come back later.

```bash
pip install -r requirements-tts.txt
```

This installs PyTorch and Coqui TTS (~2 GB download). Then set `USE_AI_VOICE=true` and `USE_COQUI_TTS=true` in `.env`.

---

## 7. Initialize the database

### 7.1 First-time table creation

Run the init script — it creates all 8 tables in whichever database `DATABASE_URL` points at (SQLite or Supabase Postgres):

```bash
python -m scripts.init_db
```

Expected output:
```
✓ Database tables created
```

If you're on SQLite, you'll now see a file `db.sqlite3` in your project folder. If you're on Supabase, the tables show up in Supabase Studio → Table Editor.

### 7.2 Verify the tables

**SQLite check:**
```bash
sqlite3 db.sqlite3 ".tables"
# Should print: audit_logs   call_logs   file_imports  orders
#               redeliveries retries     tickets       users
```

**Supabase check:** Go to your Supabase project → **Table Editor** (left sidebar) → you should see all 8 tables.

---

## 8. Run the Supabase migration

**Skip this section if you're still on SQLite for stage 1.** This adds analytics views, the auto-redelivery trigger, and RLS policies — all Postgres-specific.

### 8.1 Open the Supabase SQL Editor

1. Supabase Dashboard → **SQL Editor** (left sidebar)
2. Click **New query**

### 8.2 Paste and run the migration

1. Open `supabase/migrations/001_views_triggers_rls.sql` in your code editor.
2. Copy the entire contents.
3. Paste into the Supabase SQL Editor.
4. Click **Run** (bottom-right) or press `Ctrl+Enter`.

Expected: `Success. No rows returned.`

If you see an error like `relation "call_logs" does not exist`, you forgot step 7 — go back and run `python -m scripts.init_db` against your Supabase `DATABASE_URL` first.

### 8.3 Verify the views

In Supabase Studio → **Database → Views**, you should see:
- `v_call_quality_breakdown`
- `v_customer_retention`
- `v_retry_effectiveness`
- `v_pending_redelivery_export`
- `v_language_usage`
- `v_working_hours_split`

Test one:
```sql
SELECT * FROM v_call_quality_breakdown LIMIT 5;
```
Returns 0 rows (no calls yet) but no error means the view works.

---

## 9. Start the API

In your activated virtualenv:

```bash
make run
```

Or, if `make` isn't available (Windows without WSL):
```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Expected output:
```
INFO:     Will watch for changes in these directories: ['/path/to/ai-call-system-updated']
INFO:     Uvicorn running on http://0.0.0.0:8000
INFO:     Started reloader process
INFO:     Started server process
INFO:     Application startup complete.
```

### Quick health check

Open a new terminal (leave the API running) and run:
```bash
curl http://localhost:8000/
```

Expected JSON response:
```json
{
  "service": "AI Call Automation Microservice",
  "status": "running",
  "ai_voice": {"enabled": false, "active_backends": []},
  "tickets": {"active_backends": []},
  "docs": "/docs"
}
```

Open `http://localhost:8000/docs` in your browser. You'll see Swagger UI with every endpoint listed and try-it-out buttons.

---

## 10. Start the Celery worker

The Celery worker handles call retries (30 min, 2 hr, 24 hr). Without it, failed calls won't be retried.

Open **a third terminal**, activate the virtualenv, and run:

```bash
make worker
```

Or directly:
```bash
celery -A app.workers.celery_worker worker --loglevel=info --beat
```

Expected:
```
[INFO] celery@yourmachine ready.
[INFO] beat: Starting...
```

Leave this running in its own terminal. It connects to Redis and waits for retry jobs to be queued.

---

## 11. Expose to internet via ngrok

Twilio's servers need to send HTTP requests to your machine when a call connects. `localhost:8000` is not reachable from the public internet, so you tunnel it via ngrok.

Open **a fourth terminal**:

```bash
ngrok http 8000
```

You'll see something like:
```
Forwarding   https://abcd-1234-5678.ngrok-free.app -> http://localhost:8000
```

Copy the `https://...ngrok-free.app` URL (yours will be different). Then:

1. Open `.env`
2. Update `BASE_URL`:
   ```
   BASE_URL=https://abcd-1234-5678.ngrok-free.app
   ```
3. **Restart the API** (`Ctrl+C` in terminal 1 → `make run` again) so it picks up the new value.

> **Important:** ngrok free tier rotates the URL every time you restart it. For a stable URL, claim a free static domain in the ngrok dashboard or upgrade to a paid plan.

---

## 12. End-to-end smoke tests

Now confirm everything talks to everything.

### 12.1 Health check

```bash
make smoke
```

Or:
```bash
curl http://localhost:8000/monitoring/health
```

Expected:
```json
{
  "database": "ok",
  "redis_configured": true,
  "ai_voice_active_backends": [],
  "ticket_active_backends": []
}
```

`database: "ok"` means SQLAlchemy can talk to your DB. If you switched to Supabase and this says `error`, your `DATABASE_URL` is wrong.

### 12.2 Import an Excel of RTO orders

Use the bundled sample:
```bash
curl -X POST http://localhost:8000/rto/import \
  -F "file=@samples/rto_orders_sample.xlsx"
```

Expected:
```json
{
  "import_id": 1,
  "file_name": "rto_orders_sample.xlsx",
  "imported": 5,
  "skipped": 0,
  "failed": 0,
  "errors": []
}
```

Verify in Supabase / SQLite — the `orders` table now has 5 rows.

### 12.3 Trigger an IVR call

This actually places a real call. Use a phone number you've verified with Twilio (or your own).

```bash
curl -X POST http://localhost:8000/event/ \
  -H "Content-Type: application/json" \
  -d '{
    "order_id": 10001,
    "user_phone": "+919876543210",
    "event_type": "ORDER_REJECTED"
  }'
```

(Replace `+919876543210` with your actual verified number.)

Expected response:
```json
{"status": "queued", "call_id": 1}
```

Within a few seconds, your phone should ring. The IVR will:
1. Greet you in English with the language picker
2. Press `2` for Hindi (or whatever you want)
3. Then play the rejection IVR in Hindi
4. Press `1` to accept re-attempt → IVR confirms → call ends

### 12.4 Check what got recorded

```bash
curl http://localhost:8000/analytics/summary
```

Expected:
```json
{
  "total_calls": 1,
  "answered_calls": 1,
  "answer_rate": 1.0,
  "confirmation_count": 0,
  "rejection_cancel_count": 0,
  "retry_attempts_total": 0,
  "tickets_created": 0,
  ...
}
```

```bash
curl http://localhost:8000/rto/insights
```

Should show:
- `calls.total: 1`, `calls.beneficial: 1`
- `rto_funnel.recovery_in_progress: 1`
- `redeliveries.total: 1, pending_export: 1`

### 12.5 Export the redeliveries Excel

```bash
curl -o redeliveries.xlsx http://localhost:8000/rto/redeliveries/export
```

Open `redeliveries.xlsx` — you'll see one row with order 10001, the customer's address, COD amount, etc. This is the file you'd send to your courier partner.

After download, calling the same endpoint again returns `404 No pending redeliveries` because the row got marked `exported_to_excel = true`.

---

## 13. Daily workflows

### Morning: import yesterday's RTO list

Your courier partner sends you a `.xlsx` with yesterday's RTOs. Upload it:
```bash
curl -X POST https://your-domain.com/rto/import -F "file=@rtos_2026_05_04.xlsx"
```

### Throughout the day: IVR calls happen automatically

Either:
- Your e-commerce backend hits `POST /event/` for each RTO with `event_type=ORDER_REJECTED`, or
- A scheduled script reads pending orders from the DB and fires calls in batches (you'd write this — see [Going to production](#15-going-to-production))

The retry worker handles the +30 min, +2 hr, +24 hr cadence automatically.

### Evening: export the Excel and send to courier

```bash
curl -o todays_redeliveries.xlsx https://your-domain.com/rto/redeliveries/export
```

Email this to your courier dispatch team.

### Weekly: review insights

In Supabase SQL Editor:
```sql
-- This week's daily call metrics
SELECT * FROM v_call_quality_breakdown
WHERE call_date >= CURRENT_DATE - INTERVAL '7 days'
ORDER BY call_date DESC;

-- Top 50 customers worth retaining
SELECT * FROM v_customer_retention
WHERE retention_score > 70
ORDER BY lifetime_value DESC LIMIT 50;

-- Which IVR language converts best?
SELECT * FROM v_language_usage;

-- Should you cap retries at 3 instead of 4?
SELECT * FROM v_retry_effectiveness;

-- Are after-hours calls worth running?
SELECT * FROM v_working_hours_split;
```

---

## 14. Troubleshooting

### `make: command not found`
Use the explicit commands instead:
- `make run` → `uvicorn app.main:app --reload --port 8000`
- `make worker` → `celery -A app.workers.celery_worker worker --loglevel=info --beat`
- `make smoke` → `curl http://localhost:8000/monitoring/health`

### `ModuleNotFoundError: No module named 'app'`
You forgot to activate the virtualenv. Run `source .venv/bin/activate` (macOS/Linux) or `.venv\Scripts\activate` (Windows).

### `connection to server ... failed: SSL connection has been closed unexpectedly`
Your Supabase `DATABASE_URL` uses the wrong pooler. Long-running workers need the **Session pooler** (port 5432), not Transaction (6543).

### `redis.exceptions.ConnectionError: Error 111 connecting to localhost:6379`
Redis isn't running. Start it (`brew services start redis` or `sudo systemctl start redis-server`) or change `REDIS_URL` to point at your Redis instance.

### Twilio calls return 502 / 12300 errors
`BASE_URL` in `.env` is wrong, or ngrok isn't running, or you didn't restart the API after updating `BASE_URL`. Fix and restart.

### Trial-account "The number +91XXX is unverified" error
Twilio trial only calls verified numbers. Add the destination to **Phone Numbers → Manage → Verified Caller IDs** OR upgrade your Twilio account.

### IVR plays English even though user picked Hindi
First-time callers see the language picker. After they pick once, `User.preferred_language` is saved and the picker is skipped. Clear the user row or pass a different number to test the picker again.

### Excel import fails with "KeyError: 'order_id'"
Your Excel column headers don't match. Open `samples/rto_orders_sample.xlsx` to see the expected headers (case-insensitive): `order_id, user_phone, product_name, sku, quantity, order_value, cod_amount, payment_mode, address, city, state, pincode, awb_number, courier, rto_reason, rto_date`.

### `relation "call_logs" does not exist` when running the migration
You ran the SQL migration before the SQLAlchemy tables were created. Run `python -m scripts.init_db` first — that creates the tables. Then run the migration.

### Redelivery row not appearing after IVR press '1'
Check the API logs for `_ensure_redelivery_row` errors. Most common cause: the `orders` row for that `order_id` doesn't exist (you skipped the import step). The redelivery still gets created, but the order status update silently skips. Verify by querying `redeliveries` directly.

### Calls fire but TTS sounds robotic
You're on `USE_AI_VOICE=false`, which uses Twilio's basic Polly voice. To get higher-quality voices, install Coqui TTS (step 6.3) and set `USE_AI_VOICE=true` + `USE_COQUI_TTS=true`. Or pay for ElevenLabs and set `ELEVENLABS_API_KEY` + `TTS_PROVIDERS=elevenlabs`.

### `pip install psycopg2-binary` fails on Apple Silicon
```bash
pip install psycopg2-binary --no-cache-dir
```
If still failing, install via Homebrew first: `brew install postgresql@16` then retry.

---

## 15. Going to production

Once stage 1 (SQLite + ngrok + Twilio trial) works, harden it for real use.

### 15.1 Move to Supabase

In `.env`:
```
DATABASE_URL=postgresql://postgres.PROJECT_REF:PASSWORD@aws-0-REGION.pooler.supabase.com:5432/postgres
```
Restart API. Run the migration in Supabase SQL Editor (step 8).

### 15.2 Deploy the API somewhere stable

Options, cheapest first:
- **Railway** ($5/mo) — connects to your GitHub repo, auto-deploys on push, includes a free domain. Easiest.
- **Render** ($7/mo) — similar to Railway, free tier sleeps after 15 min of inactivity.
- **Fly.io** (~$5/mo) — Docker-based, gives you a global edge network.
- **Your own VPS** ($5–10/mo on Hetzner/DigitalOcean) — most control, most work.

For Railway: push the project to GitHub, click "Deploy from GitHub repo" in Railway, paste your `.env` values into the Railway dashboard, done.

### 15.3 Replace ngrok with the real domain

Once deployed (say at `https://api.yourshop.com`):
1. Update `.env` → `BASE_URL=https://api.yourshop.com`
2. Update Twilio webhook URL configurations if you've set any in their console (you usually don't need to — the project sets them per-call dynamically).

### 15.4 Run Celery worker on the same host

If using Railway/Render, define a second service:
- Same Docker image
- Different start command: `celery -A app.workers.celery_worker worker --loglevel=info --beat`

### 15.5 Schedule nightly RTO ingestion

If your courier emails you the RTO Excel daily, you have a few options:
- A cron job that downloads from their FTP/email and POSTs to `/rto/import`
- Supabase Edge Function on a schedule (Pro feature) that pulls and uploads
- Manual upload via a small admin frontend (next item)

### 15.6 Build an admin dashboard (optional)

A simple Next.js + Tailwind app that:
- Hits `/rto/insights` for the homepage charts
- Hits `/rto/redeliveries/export` with a "Download today's redeliveries" button
- Has a file upload widget that POSTs to `/rto/import`
- Shows a table from `v_customer_retention` with sortable columns

Use Supabase Auth on the frontend for login; verify the JWT in your FastAPI middleware. This is a 1–2 day build.

### 15.7 Monitoring

- Add **Sentry** for error tracking: `pip install sentry-sdk`, then `sentry_sdk.init(dsn=...)` in `app/main.py`.
- Use Supabase's built-in metrics dashboard (Reports tab) for DB-level observability.
- Set up Twilio's debugger webhook so failed calls show up in your logs.

### 15.8 Cost projection at 1,000 calls/day

| Item | Monthly cost |
|---|---|
| Twilio number + 1,000 calls/day × 1 min avg × $0.013/min | ~$390 |
| Supabase Pro (you have this) | $25 |
| Railway hosting | $5–10 |
| ngrok | $0 (replaced by real domain) |
| ElevenLabs TTS (skip if using Coqui) | ~$30 |
| Chatwoot self-hosted | $0 |
| **Total** | **~$425–450/mo** |

The biggest line item is Twilio. If your IVR conversation averages 30 seconds instead of 60, that halves to $195. That's a real engineering target.

---

## Quick reference card

```bash
# Daily startup (3 terminals, all from project root with .venv activated)
Terminal 1:  source .venv/bin/activate && make run
Terminal 2:  source .venv/bin/activate && make worker
Terminal 3:  ngrok http 8000   # only if local-dev with Twilio

# Smoke test
curl http://localhost:8000/monitoring/health

# Trigger a test call
curl -X POST http://localhost:8000/event/ -H "Content-Type: application/json" \
  -d '{"order_id":10001,"user_phone":"+91YOURNUMBER","event_type":"ORDER_REJECTED"}'

# Import RTO Excel
curl -X POST http://localhost:8000/rto/import -F "file=@your_file.xlsx"

# Export redeliveries
curl -o redeliveries.xlsx http://localhost:8000/rto/redeliveries/export

# View insights
curl http://localhost:8000/rto/insights | python -m json.tool

# Run the test suite
make test
```

You're done. If anything breaks, search this doc for the error message — most issues are covered in [Troubleshooting](#14-troubleshooting).
