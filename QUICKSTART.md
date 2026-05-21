# Quick Start (10 minutes to first call)

If you just want the fastest path from zero to a working IVR call. For the full guide with explanations, see `SETUP_GUIDE.md`.

## Prereqs (install once)

- Python 3.10+
- Redis running locally (`brew install redis && brew services start redis` on macOS)
- A free Twilio account with one phone number and your destination number verified
- ngrok installed (`brew install ngrok` and run `ngrok config add-authtoken YOUR_TOKEN`)

## Setup (5 minutes)

```bash
# 1. Get the project
unzip ai-call-system-updated.zip
cd ai-call-system-updated

# 2. Configure environment
cp .env.example .env
# Edit .env: set TWILIO_SID, TWILIO_AUTH, TWILIO_NUMBER (leave DATABASE_URL as SQLite)

# 3. Create virtualenv and install
python3 -m venv .venv
source .venv/bin/activate           # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# 4. Initialize the database (creates 8 tables in db.sqlite3)
python -m scripts.init_db
```

## Run (3 terminals)

```bash
# Terminal 1: API
source .venv/bin/activate
make run

# Terminal 2: Retry worker
source .venv/bin/activate
make worker

# Terminal 3: Public tunnel for Twilio
ngrok http 8000
# Copy the https://xxxxx.ngrok-free.app URL,
# update BASE_URL in .env,
# then Ctrl+C and restart Terminal 1 (make run) to pick up the change.
```

## Test (2 minutes)

```bash
# Health check
curl http://localhost:8000/monitoring/health

# Import the sample RTO Excel
curl -X POST http://localhost:8000/rto/import \
  -F "file=@samples/rto_orders_sample.xlsx"

# Trigger a real IVR call to YOUR phone (must be Twilio-verified)
curl -X POST http://localhost:8000/event/ \
  -H "Content-Type: application/json" \
  -d '{"order_id":10001,"user_phone":"+91YOURNUMBER","event_type":"ORDER_REJECTED"}'

# After the call, check the insights
curl http://localhost:8000/rto/insights | python -m json.tool

# Download the pending redeliveries Excel
curl -o redeliveries.xlsx http://localhost:8000/rto/redeliveries/export
```

## Switch to Supabase (later)

When you want to replace SQLite with Supabase:

1. Get Connection String → URI from Supabase Settings → Database (use **Session** pooler, port 5432)
2. Update `DATABASE_URL` in `.env` to that string
3. Restart the API — SQLAlchemy creates the 8 tables automatically
4. In Supabase SQL Editor, run `supabase/migrations/001_views_triggers_rls.sql` once

That's it. Same code; data now in Supabase.

## When something breaks

See the **Troubleshooting** section in `SETUP_GUIDE.md` — covers the 12 most common errors with fixes.
