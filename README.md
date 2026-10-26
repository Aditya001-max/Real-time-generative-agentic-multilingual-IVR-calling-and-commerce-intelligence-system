<div align="center">

<h1>🤖 Real-Time Generative Agentic Multilingual IVR<br/>& Commerce Intelligence System</h1>

<p><strong>Production-ready AI voice agent for Indian e-commerce — outbound/inbound IVR in 9 languages, ML-powered commerce intelligence, and end-to-end RTO recovery automation.</strong></p>

[![Python](https://img.shields.io/badge/Python-3.10+-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115-009688?style=for-the-badge&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![Celery](https://img.shields.io/badge/Celery-5.4-37814A?style=for-the-badge&logo=celery&logoColor=white)](https://docs.celeryq.dev)
[![Redis](https://img.shields.io/badge/Redis-5.2-DC382D?style=for-the-badge&logo=redis&logoColor=white)](https://redis.io)
[![Supabase](https://img.shields.io/badge/Supabase-Postgres-3ECF8E?style=for-the-badge&logo=supabase&logoColor=white)](https://supabase.com)
[![Docker](https://img.shields.io/badge/Docker-Compose-2496ED?style=for-the-badge&logo=docker&logoColor=white)](https://docker.com)
[![License](https://img.shields.io/badge/License-MIT-yellow?style=for-the-badge)](LICENSE)

</div>

---

## 🎯 What This System Does

This microservice automates the entire **outbound/inbound voice contact workflow** for Indian D2C and e-commerce businesses — replacing a human tele-caller team with a real-time AI voice agent that:

- 📞 **Calls customers automatically** on order placement, rejection, or RTO events
- 🗣️ **Speaks in 9 Indian languages** with regional language detection and preference memory
- 🤖 **Understands intent in real-time** — confirms orders, recovers RTOs, escalates to agents
- 🧠 **Runs 9+ ML models** for intent, sentiment, churn prediction, fraud detection, CLV scoring, RTO prediction, customer segmentation, and ranking
- 🔄 **Integrates with OMS, courier APIs, and Meta Graph API** for full automation of delivery lifecycle
- 📊 **Generates commerce intelligence** — retention scoring, call quality analytics, retry effectiveness, language conversion metrics

> **Impact:** Reduces RTO losses (which wipe 20–40% of COD margin for Indian D2C brands) and automates what would otherwise require a dedicated multilingual call centre team.

---

## ✨ Key Features

### 🎙️ Real-Time Generative Voice Agent
- **Inbound + outbound** IVR flows for order confirmation, RTO recovery, payment failure, and escalation
- **9 Indian languages:** English, Hindi, Tamil, Telugu, Kannada, Malayalam, Bengali, Marathi, Gujarati
- **Regional language routing** — detects caller's state and surfaces their preferred language first
- **AI voice synthesis chain:** Coqui XTTS-v2 (free, self-hosted) → ElevenLabs (paid) → Google Wavenet via Ozonetel → KooKoo native TTS
- **Content-addressed audio cache** — `sha256(text + backend + voice)` ensures zero synthesis latency on repeat calls
- **Startup pre-warming** across all 9 languages so the very first call has instant response

### 🧠 Machine Learning Intelligence Layer (9+ Models)
| Model | Task | Algorithm |
|---|---|---|
| Intent Classification | Detect customer intent from IVR keypresses + speech | XGBoost |
| Sentiment Analysis | Real-time sentiment scoring during call | LightGBM |
| Churn Prediction | Score at-risk customers before calling | XGBoost |
| RTO Prediction | Predict RTO likelihood before dispatch | LightGBM |
| Fraud Detection | Flag suspicious order patterns | XGBoost |
| Customer Lifetime Value (CLV) | Score and rank customers by value | LightGBM |
| Customer Segmentation | K-means + LightGBM clustering | Ensemble |
| Re-order Propensity Ranking | Rank customers for re-engagement | XGBoost |
| Call Outcome Prediction | Predict beneficial vs non-working calls | LightGBM |

### 🔗 Commerce & Logistics Integrations
- **OMS (Order Management System)** — real-time PATCH on CONFIRMED / CANCELLED / RE_ATTEMPT_DELIVERY
- **Courier APIs** — Excel-based import/export for RTO lists; auto-creates re-delivery rows
- **Meta Graph API** — WhatsApp Business notifications for delivery updates, order confirmation, and customer feedback collection
- **Chatwoot (OSS ticketing)** — auto-creates support conversations for escalations
- **Supabase / PostgreSQL** — views, triggers, and RLS policies for analytics and data governance

### ♻️ Automated RTO Recovery Pipeline
```
Courier XLSX  →  POST /rto/import  →  ORDER_REJECTED IVR Call
     ↓
Customer presses 1 (Re-attempt)  →  Redelivery row auto-created  →  OMS updated
     ↓
GET /rto/redeliveries/export  →  XLSX sent back to courier  →  Delivery re-attempted
```

### 📊 Commerce Intelligence & Analytics
- Call quality breakdown (working / non-working / beneficial) per language, per day
- Customer retention scoring recomputed on every OMS status change
- Retry engine effectiveness analysis (cap at 3 vs 4 retries?)
- Language conversion metrics (which language drives highest IVR conversion?)
- After-hours call ROI split
- Live SQL views in Supabase for real-time dashboard

---

## 🏗️ System Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                        EXTERNAL EVENT SOURCES                        │
│         OMS  │  Courier API  │  Meta Graph API  │  Manual POST      │
└──────────────────────────────┬──────────────────────────────────────┘
                               │  POST /event/
                               ▼
┌──────────────────────────────────────────────────────────────────────┐
│  [2] Event Listener          [3] Decision Engine                     │
│   routes/event.py             • Event → Call Type mapping            │
│                               • Working hours check                  │
│                               • ML: RTO prediction, churn score      │
└──────────────────────────────┬───────────────────────────────────────┘
                               │
                               ▼
┌──────────────────────────────────────────────────────────────────────┐
│  [4] Call Manager            [5] Retry Engine (Celery)               │
│   services/call_manager.py    • +0min → +30min → +2h → +24h         │
│                               • Stops on first customer response     │
└──────────────────────────────┬───────────────────────────────────────┘
                               │
                               ▼
┌──────────────────────────────────────────────────────────────────────┐
│  [7] Telephony Provider — Ozonetel KooKoo / CloudAgent               │
│   services/telephony.py                                              │
│   • CPaaS outbound.php  OR  CloudAgent Campaign API                 │
└──────────────────────────────┬───────────────────────────────────────┘
                               │  Customer answers
                               ▼
┌──────────────────────────────────────────────────────────────────────┐
│  [6] Webhook Handler         [8] IVR Flows (KooKoo XML)              │
│   routes/webhook.py           • 9-language picker (DTMF 1–9)        │
│   /voice-start                • Confirmation: 1=Confirm, 2=Help     │
│   /voice-response             • Rejection: 1=Re-attempt, 2=Cancel   │
│   /status                     • services/kookoo_xml.py builder      │
└──────────────────────────────┬───────────────────────────────────────┘
                               │  Customer presses digit
                               ▼
┌──────────────────────────────────────────────────────────────────────┐
│  [9] Action Engine           ML Intelligence Layer                   │
│   services/action_engine.py   • Intent / Sentiment scoring          │
│   • OMS PATCH                 • Retention recompute                 │
│   • Ticket creation           • Fraud / CLV / Churn signals         │
│   • Meta API notification     • Call outcome prediction             │
└──────┬──────────────────┬────┴───────────────────────────────────────┘
       │                  │
       ▼                  ▼
┌────────────┐   ┌───────────────────────────────────────────────────┐
│[10] Storage│   │  [11] Monitoring   [12] Analytics   [13] RTO Sync │
│ 11 tables  │   │  routes/monitoring  routes/analytics  routes/rto  │
│ SQLite/PG  │   │                                                   │
└────────────┘   └───────────────────────────────────────────────────┘
```

---

## 🌐 9-Language IVR Support

| Digit | Language | Script | TTS Engine |
|:---:|---|---|---|
| 1 | English | Latin | KooKoo Native |
| 2 | Hindi | Devanagari | KooKoo Native |
| 3 | Tamil | Tamil | Google Wavenet `ta-IN-Wavenet-D` |
| 4 | Telugu | Telugu | KooKoo Native |
| 5 | Kannada | Kannada | Google Wavenet `kn-IN-Wavenet-D` |
| 6 | Malayalam | Malayalam | Google Wavenet `ml-IN-Wavenet-D` |
| 7 | Bengali | Bengali | Google Wavenet `bn-IN-Wavenet-D` |
| 8 | Marathi | Devanagari | Google Wavenet `mr-IN-Wavenet-D` |
| 9 | Gujarati | Gujarati | Google Wavenet `gu-IN-Wavenet-D` |

The language picker is **region-aware** — callers from Tamil Nadu hear Tamil first; callers from Gujarat hear Gujarati first. Once a customer picks a language, it's stored in their profile and they skip the picker on all future calls.

---

## 🛠️ Tech Stack

| Layer | Technology |
|---|---|
| **API Framework** | FastAPI 0.115 + Uvicorn (async, auto OpenAPI docs at `/docs`) |
| **ML Models** | XGBoost + LightGBM (9+ tasks: intent, sentiment, churn, RTO, fraud, CLV, segmentation, ranking) |
| **Telephony** | Ozonetel KooKoo / CloudAgent (primary) · Twilio (alternative) |
| **AI Voice (TTS)** | Coqui XTTS-v2 → ElevenLabs → Microsoft Edge TTS → Google TTS via Ozonetel |
| **Task Queue** | Celery 5.4 + Redis (retry scheduling, daily Excel export cron) |
| **Database** | SQLite (dev) / Supabase PostgreSQL (prod) via SQLAlchemy 2.0 |
| **Ticketing** | Chatwoot OSS → Generic HTTP (Zendesk / Freshdesk fallback) |
| **Messaging** | Meta Graph API (WhatsApp Business notifications) |
| **Containerisation** | Docker + Docker Compose |
| **Deployment** | Render (render.yaml) |
| **Data Validation** | Pydantic 2.9 + pydantic-settings |
| **Excel I/O** | openpyxl 3.1 (RTO import/export) |

---

## 🚀 Quick Start

### Prerequisites
- Python 3.10+
- Redis
- Ozonetel KooKoo account (or Twilio)
- ngrok (for local webhook tunnelling)

### 1. Clone & Configure

```bash
git clone https://github.com/Aditya001-max/Real-time-generative-agentic-multilingual-IVR-calling-and-commerce-intelligence-system.git
cd Real-time-generative-agentic-multilingual-IVR-calling-and-commerce-intelligence-system

cp .env.example .env
# Fill in: OZONETEL_API_KEY, OZONETEL_USERNAME, OZONETEL_DID, BASE_URL
```

### 2. Install & Run

```bash
# Option A — Full (Coqui TTS + Chatwoot ticketing — recommended)
./scripts/setup.sh --full

# Option B — Core only (fast start, no local TTS)
./scripts/setup.sh --core
```

### 3. Start Services (3 terminals)

```bash
# Terminal 1 — API server
make run
# → http://localhost:8000  |  Docs: http://localhost:8000/docs

# Terminal 2 — Celery retry worker
make worker

# Terminal 3 — ngrok tunnel (for real calls)
ngrok http 8000
# Copy the https URL → set BASE_URL in .env → restart Terminal 1
```

### 4. Trigger Your First Call

```bash
curl -X POST http://localhost:8000/event/ \
  -H "Content-Type: application/json" \
  -d '{
    "order_id": 1001,
    "user_phone": "+919876543210",
    "event_type": "ORDER_PLACED"
  }'
```

The system will call the customer, play the 9-language picker, and handle their response — all in real time.

---

## 📋 Command Reference

| Goal | Command |
|---|---|
| First-time setup (interactive) | `make setup` |
| Install dependencies | `make install` |
| Add open-source TTS (Coqui) | `make install-tts` |
| Start API server (dev) | `make run` |
| Start Celery retry worker | `make worker` |
| Run test suite | `make test` |
| Verify live system health | `make smoke` |
| Start everything in Docker | `make docker-up` |
| Add Chatwoot ticketing | `make chatwoot-up` |
| Stop all containers | `make docker-down` |

---

## 📞 IVR Call Flows

### Order Confirmation Call (`ORDER_PLACED`)
```
📞 System calls customer
   └─ "Namaste, I am Kavya calling from [Brand]..."
   └─ Language picker: Press 1 for English, 2 for Hindi... (9 options)
        └─ In chosen language:
             ├─ Press 1 → ORDER → CONFIRMED ✅
             │   SMS sent · OMS updated · Retention score recalculated
             └─ Press 2 → Help requested
                  ├─ Working hours → Live agent transfer 📱
                  └─ After hours  → Chatwoot ticket + callback queued 🎫
```

### RTO / Rejection Call (`ORDER_REJECTED`)
```
📞 System calls customer
   └─ Language picker
        └─ In chosen language:
             ├─ Press 1 → RE_ATTEMPT_DELIVERY ♻️
             │   Redelivery row created · Courier notified
             ├─ Press 2 → CANCELLED ❌
             │   OMS updated · Cancellation ticket created
             └─ Press 3 → Help requested 🎫
```

**Retry schedule:** Attempt 1 (immediately) → +30 min → +2 h → +24 h. Auto-stops on first response.

---

## 🔄 RTO Recovery & Courier Integration

For e-commerce stores running RTO recovery campaigns:

| Endpoint | Method | Purpose |
|---|---|---|
| `/rto/import` | `POST` | Upload courier `.xlsx` → populates orders + users |
| `/rto/redeliveries/export` | `GET` | Download pending redeliveries → send to courier |
| `/rto/insights` | `GET` | RTO dashboard: beneficial calls, retention, language usage |

**Sample Excel format:** See `samples/rto_orders_sample.xlsx` — 16 columns including `order_id`, `user_phone`, `awb_number`, `courier`, `rto_reason`, `cod_amount`, etc.

---

## 📊 Analytics & Intelligence Queries

Once on Supabase, use built-in SQL views:

```sql
-- Call quality breakdown per language, per day
SELECT * FROM v_call_quality_breakdown WHERE call_date = CURRENT_DATE;

-- Top customers by retention score and lifetime value
SELECT * FROM v_customer_retention
WHERE retention_score > 70 ORDER BY lifetime_value DESC LIMIT 50;

-- Retry engine effectiveness
SELECT * FROM v_retry_effectiveness;

-- Language with highest IVR conversion rate
SELECT * FROM v_language_usage;

-- Are after-hours calls worth the cost?
SELECT * FROM v_working_hours_split;
```

---

## 🗄️ Database Schema (11 Tables)

| Table | Purpose |
|---|---|
| `users` | Customer profiles, preferred language, retention score |
| `orders` | Order details, OMS status, region, language |
| `call_logs` | Full call history — SID, status, duration, outcome |
| `retries` | Celery retry queue with attempt tracking |
| `tickets` | Support tickets linked to Chatwoot / HTTP backends |
| `help_requests` | NEED_HELP events and callback scheduling |
| `redeliveries` | Scheduled re-delivery rows after RTO recovery |
| `audit_logs` | Immutable audit trail for every status change |
| `team_call_logs` | Ops team callback results |
| `file_imports` | Excel import tracking and status |
| `working_hours_config` | Configurable working hours per team/timezone |

---

## 🧩 Architecture → Code Map

| Block | Description | File |
|---|---|---|
| 2 | Event Listener | `app/routes/event.py` |
| 3 | Decision Engine | `app/services/decision_engine.py` |
| 4 | Call Manager | `app/services/call_manager.py` |
| 5 | Retry Engine (Celery) | `app/workers/retry_tasks.py` |
| 6 | Webhook Handler | `app/routes/webhook.py` |
| 7 | Telephony Provider | `app/services/telephony.py` |
| 8 | IVR Flows + KooKoo XML | `app/services/ivr_scripts.py` · `app/services/kookoo_xml.py` |
| 9 | Action Engine | `app/services/action_engine.py` · `app/services/tickets/` |
| 10 | Data Storage | `app/models/` |
| 11 | Monitoring & Alerts | `app/routes/monitoring.py` |
| 12 | Analytics & Reporting | `app/routes/analytics.py` |
| 13 | RTO Recovery & Excel Sync | `app/routes/rto.py` |
| 14 | Ops Team Callbacks | `app/routes/team.py` |
| 15 | Customer Care Dashboard | `app/routes/customer_care.py` |
| — | TTS Provider Chain | `app/services/tts/` |
| — | 9-Language Translations | `app/services/translations.py` |
| — | Language Picker & Greetings | `app/services/greetings.py` |
| — | Regional Menu Routing | `app/services/regions.py` |
| — | Working Hours Logic | `app/core/working_hours.py` |

---

## 💰 Cost Comparison (1,000 calls/day)

| Setup | TTS | Ticketing | Telephony | Monthly Total |
|---|---|---|---|---|
| All-paid (ElevenLabs + Zendesk + Twilio) | ~$30 | ~$50/agent | ~$300 | **$400+** |
| **This project's default** | **$0** (Coqui OSS) | **$0** (Chatwoot self-hosted) | ~$300 (Ozonetel) | **~$300** |

The savings scale — at 10,000 calls/day, TTS savings alone exceed $300/month.

---

## 🔧 Environment Configuration

Copy `.env.example` to `.env` and configure:

```bash
# Telephony (required)
OZONETEL_API_KEY=your_key
OZONETEL_USERNAME=your_username
OZONETEL_DID=your_did_number
BASE_URL=https://your-ngrok-url.ngrok.io

# AI Voice (optional — defaults to KooKoo native TTS)
USE_AI_VOICE=true
TTS_PROVIDERS=coqui,elevenlabs

# Meta Graph API (WhatsApp notifications)
META_API_TOKEN=your_token

# Database (defaults to SQLite locally, set for Supabase in prod)
DATABASE_URL=sqlite:///./db.sqlite3

# Ticketing
CHATWOOT_BASE_URL=http://localhost:3000
CHATWOOT_API_TOKEN=your_token
```

See `.env.example` for the full list with descriptions.

---

## 🐳 Docker Deployment

```bash
# Start everything (API + Redis + Celery + Chatwoot)
make docker-up

# Health check
make smoke
# Expected: database: ok | redis: ok | ai_voice_active_backends: ['coqui']
```

---

## 🧪 Testing

```bash
make test
# Runs: test_logic, test_languages, test_regions, test_help_router,
#       test_retention, test_tickets, test_tts
```

---

## 🗺️ Roadmap

- [ ] GPT-4o / Gemini real-time voice integration for free-form conversation
- [ ] WhatsApp IVR flow via Meta Graph API (button-based menus)
- [ ] Live ML inference endpoint for real-time churn/RTO scoring during calls
- [ ] Grafana dashboard for call analytics
- [ ] Hindi + Tamil ASR (speech-to-text) for voice responses (not just DTMF)
- [ ] Multi-tenant SaaS mode with per-brand configuration

---

## 📄 License

MIT License — see [LICENSE](LICENSE)

---

<div align="center">

**Built for Indian e-commerce · 9 Languages · Real-time AI Voice · ML Commerce Intelligence**

⭐ Star this repo if it helped you — contributions welcome!

</div>
