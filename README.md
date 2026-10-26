<div align="center">

# 🤖 Real-Time Generative Agentic Multilingual IVR<br/>& Commerce Intelligence System

<p><strong>Enterprise-grade AI voice agent for Indian e-commerce & D2C — real-time inbound/outbound IVR across 9 Indian languages, 9+ ML tasks (XGBoost & LightGBM), courier OMS integration, and automated RTO recovery with Meta Graph API.</strong></p>

[![Python](https://img.shields.io/badge/Python-3.10+-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115-009688?style=for-the-badge&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![XGBoost](https://img.shields.io/badge/XGBoost-Models-EB5B28?style=for-the-badge&logo=xgboost&logoColor=white)](https://xgboost.readthedocs.io)
[![LightGBM](https://img.shields.io/badge/LightGBM-Models-2E8540?style=for-the-badge)](https://lightgbm.readthedocs.io)
[![Celery](https://img.shields.io/badge/Celery-5.4-37814A?style=for-the-badge&logo=celery&logoColor=white)](https://docs.celeryq.dev)
[![Redis](https://img.shields.io/badge/Redis-5.2-DC382D?style=for-the-badge&logo=redis&logoColor=white)](https://redis.io)
[![Supabase](https://img.shields.io/badge/Supabase-Postgres-3ECF8E?style=for-the-badge&logo=supabase&logoColor=white)](https://supabase.com)
[![Meta Graph API](https://img.shields.io/badge/Meta_Graph_API-WhatsApp-25D366?style=for-the-badge&logo=whatsapp&logoColor=white)](https://developers.facebook.com)
[![Docker](https://img.shields.io/badge/Docker-Compose-2496ED?style=for-the-badge&logo=docker&logoColor=white)](https://docker.com)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow?style=for-the-badge)](LICENSE)

</div>

---

## 📌 Executive Summary & Core Highlights

> **"Built inbound / outbound voice agent supporting 9 Indian languages, real-time conversations on COD, RTO, payments failure, and escalation • Developed XGBoost and LightGBM models across 9+ ML tasks, including intent, sentiment, churn, RTO, fraud, CLV, segmentation, and ranking • Added courier APIs with OMS, Meta Graph API, automating RTO recovery, redelivery confirmation, delivery updates, and customer feedback."**

This production-ready microservice transforms high-friction voice communications for e-commerce by replacing manual tele-calling teams with an **agentic, multilingual AI voice system** paired with an advanced **machine learning commerce intelligence engine**.

```
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                                 CORE VALUE PROPOSITIONS                                │
├──────────────────────────┬─────────────────────────────┬───────────────────────────────┤
│ 🎙️ Multilingual Agentic  │ 🧠 Commerce Intelligence    │ 🔄 Logistics & Omnichannel    │
│    Voice IVR             │    Layer (9+ ML Models)     │    Orchestration              │
├──────────────────────────┼─────────────────────────────┼───────────────────────────────┤
│ • Inbound & outbound IVR │ • XGBoost & LightGBM        │ • Real-time OMS sync          │
│ • 9 Indian languages     │ • Intent & Sentiment        │ • Automated Courier APIs      │
│ • COD confirmation calls │ • Churn & RTO prediction    │ • Meta Graph API (WhatsApp)   │
│ • Payment failure & RTO  │ • Fraud detection & CLV     │ • Redelivery confirmation     │
│ • Smart escalation loop  │ • Segmentation & Ranking    │ • Post-call customer feedback │
└──────────────────────────┴─────────────────────────────┴───────────────────────────────┘
```

---

## 🎯 The Problem & Commercial Impact

For Indian e-commerce and Direct-to-Consumer (D2C) brands, **Cash on Delivery (COD)** represents 60–75% of total orders. However, **Return to Origin (RTO)** wipes out **20% to 40% of net retail margins** due to forward-and-reverse freight, dead inventory, and non-delivery costs.

| Operational Challenge | Traditional Method | This System's Solution |
|---|---|---|
| **RTO & COD Leakage** | Manual call centers calling customers 1-by-1 (expensive, slow, unscalable) | **Automated pre-dispatch confirmation & instant rejection re-attempt IVR** |
| **Language Barriers** | Agents typically speak only Hindi or English; regional customers drop off | **9 Indian languages supported** with state-aware auto-routing & persistent preference memory |
| **Operational Costs** | ₹15–₹30 per customer call via human tele-callers | **~₹0.30–₹1.00 per contact** (telephony-only, zero marginal software cost) |
| **Logistics Coordination** | Manual Excel exports sent back and forth to courier partners | **Automated bi-directional Courier API & Excel sync** with auto-scheduled redelivery |
| **Omnichannel Friction** | Disconnected voice, SMS, and WhatsApp alerts | **Automated WhatsApp notifications via Meta Graph API** for redelivery & instant feedback |

---

## ✨ System Architecture & 13-Block Pipeline

```
                                  [ EXTERNAL SOURCES ]
                OMS  │  Courier APIs (XLSX)  │  Meta Graph API  │  Webhooks
                                           │
                                           ▼ POST /event/
 ┌───────────────────────────────────────────────────────────────────────────────────────┐
 │ [2] Event Listener (routes/event.py)                                                  │
 │     Validates payload, lazy-creates User & Order records, pushes to Decision Engine   │
 └─────────────────────────────────────────┬─────────────────────────────────────────────┘
                                           │
                                           ▼
 ┌───────────────────────────────────────────────────────────────────────────────────────┐
 │ [3] Decision Engine & ML Pre-Scoring (services/decision_engine.py)                    │
 │     • Evaluates operational window (Working Hours check: 09:00 - 18:00 IST)          │
 │     • Executes LightGBM RTO Risk Model & XGBoost Churn / Fraud scoring                │
 │     • Maps event to call flow: CONFIRMATION (COD) vs. REJECTION (RTO)                 │
 └─────────────────────────────────────────┬─────────────────────────────────────────────┘
                                           │
                                           ▼
 ┌───────────────────────────────────────────────────────────────────────────────────────┐
 │ [4] Call Manager & [5] Retry Engine (services/call_manager.py · Celery + Redis)       │
 │     • Exponential backoff retry cadence: 0 min → +30 min → +2 hours → +24 hours       │
 │     • Dynamic cancellation: automatically halts pending retries upon customer reply   │
 └─────────────────────────────────────────┬─────────────────────────────────────────────┘
                                           │
                                           ▼
 ┌───────────────────────────────────────────────────────────────────────────────────────┐
 │ [7] Telephony Provider Layer (services/telephony.py)                                  │
 │     • Ozonetel KooKoo CPaaS outbound.php / CloudAgent Campaign API (Primary)          │
 │     • Twilio Voice API fallback                                                       │
 └─────────────────────────────────────────┬─────────────────────────────────────────────┘
                                           │ Customer Answers
                                           ▼
 ┌───────────────────────────────────────────────────────────────────────────────────────┐
 │ [6] Webhook Handler & [8] Multilingual IVR Flows (routes/webhook.py · kookoo_xml.py)  │
 │     • Region-aware 9-Language Selector (DTMF 1–9) with zero-latency audio cache       │
 │     • Real-time flows: COD Confirmation (1=Confirm, 2=Help)                           │
 │     • RTO Rejection Recovery (1=Re-attempt, 2=Cancel, 3=Help)                         │
 │     • Payment Failure recovery & Live Agent Escalation                                │
 └─────────────────────────────────────────┬─────────────────────────────────────────────┘
                                           │ Customer Inputs DTMF / Response
                                           ▼
 ┌───────────────────────────────────────────────────────────────────────────────────────┐
 │ [9] Action Engine & Omnichannel Sync (services/action_engine.py)                      │
 │     • OMS PATCH: Update status (CONFIRMED / CANCELLED / RE_ATTEMPT_DELIVERY)          │
 │     • Courier Redelivery: Auto-generate redeliveries record for courier re-dispatch   │
 │     • Meta Graph API: Send WhatsApp delivery updates & customer feedback templates    │
 │     • Help Router: Connects live agent hunt-group OR creates Chatwoot support ticket  │
 │     • Retention Engine: Recalculates dynamic customer retention & CLV score           │
 └─────────────────────────────────────────┬─────────────────────────────────────────────┘
                                           │
                     ┌─────────────────────┴─────────────────────┐
                     ▼                                           ▼
 ┌───────────────────────────────────────┐   ┌───────────────────────────────────────────┐
 │ [10] Persistent Storage               │   │ [11-13] Intelligence & Reporting Suites   │
 │ • 11 Relational Tables (SQLAlchemy)   │   │ • routes/monitoring.py (Health & Metrics) │
 │ • PostgreSQL / Supabase + SQLite      │   │ • routes/analytics.py (Conversion Views)  │
 │ • Row Level Security & Triggers       │   │ • routes/rto.py (Courier Import/Export)   │
 └───────────────────────────────────────┘   └───────────────────────────────────────────┘
```

---

## 🧠 Machine Learning Commerce Intelligence Layer (9+ Models)

The architecture embeds dedicated **XGBoost** and **LightGBM** models across the calling and order lifecycle to maximize conversion, eliminate fraud, and optimize customer lifetime value:

| # | Task | Objective & Business Logic | Algorithm | Key Features / Inputs |
|:---:|---|---|:---:|---|
| **1** | **Intent Classification** | Recognizes user intent across multi-digit DTMF keypresses and speech transcripts. | **XGBoost** | Call flow context, response latency, repeat keypresses, utterance embedding |
| **2** | **Sentiment Analysis** | Evaluates customer sentiment during live call interactions and feedback submissions. | **LightGBM** | Audio sentiment signals, interaction duration, response hesitation, survey scores |
| **3** | **Customer Churn Prediction** | Flags at-risk users before outbound triggers to adjust communication tone. | **XGBoost** | Order recency, order frequency, refund counts, historical cancellation rate |
| **4** | **RTO Risk Prediction** | Estimates RTO likelihood at the moment of order placement prior to dispatch. | **LightGBM** | Pincode tier, payment mode (COD vs Prepaid), product category, customer RTO history |
| **5** | **Fraud & Fake Order Detection** | Identifies anomalous orders and suspicious caller behavior patterns. | **XGBoost** | IP/phone mismatch, velocity of orders, high-risk delivery addresses, order value anomalies |
| **6** | **Customer Lifetime Value (CLV)** | Projects customer multi-year value for prioritizing agent transfers during escalation. | **LightGBM** | Historical GMV, repeat order interval, basket margin, retention score |
| **7** | **Customer Segmentation** | Groups buyers into actionable behavioral cohorts (e.g., Bargain Hunter, High-Intent Loyal). | **Ensemble (K-Means + LightGBM)** | Frequency, Monetary value, Average Order Value (AOV), Preferred language, Channel affinity |
| **8** | **Re-order Propensity Ranking** | Ranks post-delivery customers for high-ROI automated re-order & cross-sell campaigns. | **XGBoost** | Product consumption lifecycle, past reorder cadence, sentiment during last IVR call |
| **9** | **Call Outcome & Benefit Scoring** | Classifies calls into *beneficial*, *working*, or *non-working* for cost attribution. | **LightGBM** | Call duration, terminal IVR branch, retry count, status transition in OMS |

---

## 🌐 9 Indian Languages & Region-Aware Voice Synthesis

The IVR features zero-barrier access for India's diverse linguistic demographic:

| DTMF | Language | Script | Primary Voice Engine | Fallback Engine |
|:---:|---|---|---|---|
| **1** | English (Indian accent) | Latin | Coqui XTTS-v2 / ElevenLabs | KooKoo Native TTS |
| **2** | Hindi (हिन्दी) | Devanagari | Coqui XTTS-v2 / ElevenLabs | KooKoo Native TTS |
| **3** | Tamil (தமிழ்) | Tamil | Google Wavenet `ta-IN-Wavenet-D` | Pre-rendered High-Quality Audio |
| **4** | Telugu (తెలుగు) | Telugu | Google Wavenet `te-IN-Standard-A` | KooKoo Native TTS |
| **5** | Kannada (ಕನ್ನಡ) | Kannada | Google Wavenet `kn-IN-Wavenet-D` | Pre-rendered High-Quality Audio |
| **6** | Malayalam (മലയാളം) | Malayalam | Google Wavenet `ml-IN-Wavenet-D` | Pre-rendered High-Quality Audio |
| **7** | Bengali (বাংলা) | Bengali | Google Wavenet `bn-IN-Wavenet-D` | Pre-rendered High-Quality Audio |
| **8** | Marathi (मराठी) | Devanagari | Google Wavenet `mr-IN-Wavenet-D` | Pre-rendered High-Quality Audio |
| **9** | Gujarati (ગુજરાતી) | Gujarati | Google Wavenet `gu-IN-Wavenet-D` | Pre-rendered High-Quality Audio |

### ⚡ Region-Aware Routing & Content-Addressed Caching
- **Regional Dialect Routing:** The system maps the customer's state code (e.g., `TN` → Tamil, `GJ` → Gujarati, `WB` → Bengali) and automatically presents their native language as the first prompt.
- **Persistent Language Memory:** Once a customer selects a language, it is written to the `users.preferred_language` profile, bypassing the language menu on all subsequent calls.
- **Content-Addressed Audio Cache:** Audio prompts are synthesized once and hashed via `sha256(text + backend + voice)`. Repeat phrases have **0ms synthesis latency**.

---

## 🔄 Courier APIs, OMS & Meta Graph API Automation

### 1. Automated RTO Recovery Loop
```
  [Courier Partner] ──(Dispatches Excel/API)──► POST /rto/import
                                                     │
                                                     ▼
                                        Outbound ORDER_REJECTED Call
                                                     │
               ┌─────────────────────────────────────┴─────────────────────────────────────┐
               ▼ (Customer presses '1': Re-attempt)                                        ▼ (Customer presses '2': Cancel)
  • OMS status updated to RE_ATTEMPT_DELIVERY                               • OMS status updated to CANCELLED
  • Stored in `redeliveries` table with SCHEDULED state                     • Cancellation ticket logged in Chatwoot
  • Meta Graph API sends WhatsApp confirmation & dispatch update            • Meta Graph API sends cancellation confirmation
               │
               ▼
  GET /rto/redeliveries/export ──► Direct sync file returned to Courier for second delivery attempt
```

### 2. Meta Graph API (WhatsApp Business Integration)
- **Delivery Updates:** Real-time WhatsApp messages sent when delivery status updates to `OUT_FOR_DELIVERY`, `DELIVERED`, or `RE_ATTEMPT_DELIVERY`.
- **Redelivery Confirmation:** Customers who confirm re-attempt over IVR receive a rich WhatsApp message containing expected delivery date and COD payable amount.
- **Customer Feedback Collection:** Following successful delivery or agent escalation, an automated template message triggers an interactive WhatsApp quick-reply survey to record satisfaction.

### 3. Order Management System (OMS) Two-Way Sync
- Automatically fires secure `PATCH /orders/{id}` requests with bearer authorization to client OMS endpoints upon any status update (`CONFIRMED`, `CANCELLED`, `RE_ATTEMPT_DELIVERY`).
- Fault-tolerant fallback: if the external OMS is temporarily unreachable, events are logged to the local immutable `audit_logs` table for automated synchronization retry.

---

## 📞 Real-Time IVR Conversation Flows

```
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                        FLOW A: COD ORDER CONFIRMATION (ORDER_PLACED)                   │
├────────────────────────────────────────────────────────────────────────────────────────┤
│  📞 System calls customer                                                              │
│     └─ "Namaste! Calling from [Brand] regarding your Cash on Delivery order #1001..."  │
│     └─ Language Menu (Region prioritized)                                              │
│          ├─ Press 1: Order CONFIRMED                                                   │
│          │    └─ OMS status updated to CONFIRMED                                       │
│          │    └─ WhatsApp confirmation dispatched via Meta Graph API                   │
│          │    └─ Retention score dynamically recalculated                              │
│          └─ Press 2: Customer Requests Help / Modification                             │
│               ├─ During business hours (09:00 - 18:00 IST): Live agent bridge          │
│               └─ After hours: Automated Chatwoot ticket + queued callback              │
└────────────────────────────────────────────────────────────────────────────────────────┘

┌────────────────────────────────────────────────────────────────────────────────────────┐
│                        FLOW B: RTO & REJECTION RECOVERY (ORDER_REJECTED)               │
├────────────────────────────────────────────────────────────────────────────────────────┤
│  📞 System calls customer                                                              │
│     └─ "We noticed your package could not be delivered today..."                       │
│     └─ Options in customer's preferred language:                                       │
│          ├─ Press 1: Request RE-ATTEMPT                                                │
│          │    └─ Redelivery record created for courier dispatch                        │
│          │    └─ WhatsApp message sent with updated delivery window                    │
│          ├─ Press 2: CANCEL Order                                                      │
│          │    └─ OMS marked CANCELLED; Return freight initiated immediately           │
│          └─ Press 3: Speak to Support Agent / Reschedule                               │
└────────────────────────────────────────────────────────────────────────────────────────┘
```

---

## 🛠️ Complete Technical Stack

| Category | Component / Library | Version / Details | Purpose |
|---|---|---|---|
| **Core Framework** | `FastAPI` | `0.115.x` | High-performance asynchronous API layer with auto-generated OpenAPI documentation |
| **ASGI Server** | `Uvicorn` | `0.32.x` | Production-grade ASGI runtime with standard event loops |
| **Machine Learning** | `XGBoost` & `LightGBM` | Latest stable | Powers 9+ ML tasks: intent, sentiment, churn, RTO, fraud, CLV, segmentation, and ranking |
| **Task Queue & Cron** | `Celery` + `Redis` | `Celery 5.4` / `Redis 5.2` | Exponential backoff retries, background workers, and nightly Excel sync tasks |
| **Database & ORM** | `SQLAlchemy` + `PostgreSQL` | `2.0.x` / `Supabase` | Dual-engine: SQLite for instant local dev, Supabase PostgreSQL with RLS in production |
| **Telephony CPaaS** | `Ozonetel KooKoo` & `Twilio` | Enterprise | TRAI-compliant Indian telephony (KooKoo CPaaS & CloudAgent) with Twilio fallback |
| **Generative Voice (TTS)** | `Coqui XTTS-v2` & `ElevenLabs` | Multi-backend | Open-source self-hosted voice cloning (Coqui) with ElevenLabs paid fallback |
| **Omnichannel Messaging** | `Meta Graph API` | v19.0+ | Automated WhatsApp Business messaging for delivery updates, confirmation, & feedback |
| **Ticketing & Support** | `Chatwoot OSS` & Generic HTTP | Self-hosted | Open-source omnichannel customer support ticketing with Zendesk/Freshdesk webhook support |
| **Data Validation** | `Pydantic` & `pydantic-settings`| `2.9.x` | Strict type validation, environment variable isolation, and request/response schemas |
| **Logistics Processing** | `openpyxl` | `3.1.x` | Multi-column Excel data parser and generator for courier RTO sheets |
| **DevOps & Containers** | `Docker` & `Docker Compose` | Multi-stage | Containerized orchestration for API, Redis, Celery worker, and Chatwoot stack |

---

## 🗄️ Relational Database Schema (11 Tables)

```
┌─────────────────┐       ┌─────────────────┐       ┌─────────────────┐
│      users      │1     *│     orders      │1     *│    call_logs    │
├─────────────────┤◄──────├─────────────────┤◄──────├─────────────────┤
│ phone_number PK │       │ order_id PK     │       │ call_id PK      │
│ preferred_lang  │       │ user_phone FK   │       │ order_id FK     │
│ retention_score │       │ oms_status      │       │ sid, status     │
│ clv_score       │       │ rto_risk_score  │       │ duration, digit │
│ delivery_state  │       │ cod_amount      │       │ sentiment_score │
└─────────────────┘       └─────────────────┘       └─────────────────┘
                                   │1
                                   ├────────────────────────┬────────────────────────┐
                                   ▼*                       ▼*                       ▼*
                          ┌─────────────────┐      ┌─────────────────┐      ┌─────────────────┐
                          │  redeliveries   │      │     tickets     │      │     retries     │
                          ├─────────────────┤      ├─────────────────┤      ├─────────────────┤
                          │ redelivery_id PK│      │ ticket_id PK    │      │ retry_id PK     │
                          │ order_id FK     │      │ order_id FK     │      │ order_id FK     │
                          │ delivery_status │      │ issue_type      │      │ attempt_number  │
                          │ exported_to_xlsx│      │ chatwoot_id     │      │ scheduled_at    │
                          └─────────────────┘      └─────────────────┘      └─────────────────┘
```

Other supporting tables: `audit_logs` (immutable event ledger), `help_requests` (callback routing queue), `file_imports` (Excel processing logs), `team_call_logs` (manual ops callback logs), and `working_hours_config` (dynamic schedule rules).

---

## 🚀 Quick Start & Installation

### 1. Clone & Configure
```bash
git clone https://github.com/Aditya001-max/Real-time-generative-agentic-multilingual-IVR-calling-and-commerce-intelligence-system.git
cd Real-time-generative-agentic-multilingual-IVR-calling-and-commerce-intelligence-system

# Create environment file from template
cp .env.example .env
```

### 2. Configure Environment Variables (`.env`)
```ini
# Telephony (Ozonetel KooKoo or CloudAgent)
OZONETEL_API_KEY=your_ozonetel_key
OZONETEL_USERNAME=your_username
OZONETEL_DID=your_did_number
BASE_URL=https://your-public-domain-or-ngrok.ngrok-free.app

# Meta Graph API (WhatsApp Notifications & Feedback)
META_API_URL=https://graph.facebook.com/v19.0
META_API_TOKEN=your_meta_system_user_token

# Machine Learning & AI Voice
USE_AI_VOICE=true
TTS_PROVIDERS=coqui,elevenlabs

# Task Queue & Database
DATABASE_URL=sqlite:///./db.sqlite3
REDIS_URL=redis://localhost:6379/0
```

### 3. Launch Services

#### Option A: Native Development (3 Terminals)
```bash
# Terminal 1 — Start FastAPI Server
make run
# Swagger documentation available at http://localhost:8000/docs

# Terminal 2 — Start Celery Retry Worker
make worker

# Terminal 3 — Expose Local Port via ngrok (for Webhooks)
ngrok http 8000
```

#### Option B: Docker Compose (All-in-One)
```bash
# Spins up API, Redis, Celery Worker, and Chatwoot stack
make docker-up

# Verify health check across components
make smoke
```

---

## 📡 Key API Endpoints Reference

| Category | Method | Endpoint | Description |
|---|:---:|---|---|
| **Event Ingestion** | `POST` | `/event/` | Ingests `ORDER_PLACED` or `ORDER_REJECTED` from OMS to trigger decision & IVR pipeline |
| **Telephony Webhook**| `GET/POST`| `/webhook/voice-start` | Entry webhook invoked by Ozonetel/Twilio when caller picks up; serves dynamic XML |
| **IVR Input** | `GET/POST`| `/webhook/voice-response` | Receives DTMF input, maps intent, triggers Action Engine, updates OMS |
| **Courier RTO Sync** | `POST` | `/rto/import` | Uploads courier `.xlsx` file; auto-seeds orders, users, and initiates IVR calls |
| **Courier Export** | `GET` | `/rto/redeliveries/export` | Downloads processed redelivery requests in formatted Excel to hand back to couriers |
| **Commerce Metrics** | `GET` | `/analytics/summary` | Real-time breakdown of call outcomes, conversion rates, and language performance |
| **RTO Intelligence** | `GET` | `/rto/insights` | Deep-dive analytics on beneficial calls, recovered revenue, and courier efficiency |
| **Monitoring** | `GET` | `/health` | Health probe validating database connection, Redis broker, and TTS backend status |

---

## 🧪 Testing & Verification

The test suite validates telephony XML builders, language localization, regional menus, retention scoring, and ticket fallback chains:

```bash
# Execute entire test suite
make test

# Execute individual test targets
pytest tests/test_languages.py      # Validates 9-language prompt completeness
pytest tests/test_regions.py        # Verifies state-to-language mappings
pytest tests/test_retention.py      # Verifies mathematical retention scoring logic
pytest tests/test_logic.py          # Validates action engine & OMS state machine
```

---

## 🗺️ Engineering Roadmap

- [x] Inbound / outbound voice agent supporting 9 Indian languages.
- [x] XGBoost and LightGBM models across 9+ commerce intelligence tasks.
- [x] OMS integration and bi-directional Courier Excel RTO sync.
- [x] Meta Graph API WhatsApp notifications for delivery updates and feedback.
- [ ] End-to-end Whisper / Conformer speech-to-text integration for free-form speech input.
- [ ] Real-time LLM streaming agent (OpenAI Realtime API / Gemini Live) integration.
- [ ] Self-service Merchant Analytics Dashboard in React / Next.js.

---

## 📄 License & Attribution

This project is open-source and released under the **[MIT License](LICENSE)**.

<div align="center">

**Built for Indian E-Commerce & D2C Brands · 9 Languages · 9+ ML Tasks · Production Ready**

⭐ **Star this repository if you find it valuable!**

</div>
