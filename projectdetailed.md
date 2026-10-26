# Automatic Generative IVR Calling System — Detailed Project Analysis

**Prepared for:** Founder review
**Document type:** Technical + business context brief
**Repo:** `Automatic-generative-IVR-calling-system`
**Version:** 1.2.0
**Runtime:** Python 3.10+ / FastAPI microservice

---

## 1. Executive Summary

This project is a **production-ready AI-driven outbound IVR (Interactive Voice Response) microservice** built for e-commerce operations, specifically to reduce **RTO (Return-to-Origin) losses** and automate **order confirmation / rejection handling** at scale. Instead of hiring a call-centre team to phone every COD (Cash-on-Delivery) customer, this service does it automatically — in nine Indian languages, with AI-generated voice, and integrates directly with the client's OMS, courier Excel flows, and ticketing system.

The architecture follows a **13-block spec** (Event Listener → Decision Engine → Call Manager → Telephony → IVR Flows → Webhook Handler → Action Engine → Retry Engine → Data Storage → Monitoring → Analytics → RTO/Excel Sync → Ops-team callback). It is deliberately built **cloud-agnostic** and with **open-source fallbacks** for every paid layer (TTS, ticketing) so that operating cost stays near-zero except for the unavoidable telephony bill.

### Why this matters commercially

| Problem | This system's answer |
|---|---|
| RTO wipes 20-40% of COD margin for Indian D2C brands | Automated pre-delivery confirmation call filters out fake / uncertain orders before dispatch |
| Human tele-callers cost ₹15-30 per contact and don't scale | This costs ~₹0.30-1 per call (telephony only) and scales to thousands/day |
| Regional-language support requires multilingual staff | 9 Indian languages built-in, with AI voice + speech recognition |
| Post-RTO recovery is a spreadsheet nightmare | Excel-in / Excel-out flow directly with courier partners; auto-populates re-delivery queue |
| Founders can't see "why" calls succeed/fail | Full analytics layer: call-quality breakdown, retention scoring, retry effectiveness, language-conversion metrics |

### Cost comparison (1,000 calls/day, 2026 pricing)

| Setup | TTS | Tickets | Telephony | Monthly total |
|---|---|---|---|---|
| All-paid (Twilio + ElevenLabs + Zendesk) | ~$30 | ~$50/agent | ~$300 | **$400+** |
| **This project's default (Coqui + Chatwoot + Twilio/Ozonetel)** | $0 | $0 | ~$300 | **~$300** |

Savings compound quickly at higher volumes.

---

## 2. Tech Stack (Complete Inventory)

### 2.1 Application layer

| Layer | Technology | Why chosen |
|---|---|---|
| Web framework | **FastAPI 0.115** | Async-native, auto OpenAPI docs (`/docs`), Pydantic-validated I/O |
| ASGI server | **Uvicorn 0.32 (standard)** | Production-grade async workers |
| Data validation | **Pydantic 2.9 + pydantic-settings 2.6** | Typed config from `.env`, strongly-typed request/response schemas |
| ORM | **SQLAlchemy 2.0.36** | Same code on SQLite (dev) and Postgres/Supabase (prod) |
| DB driver (prod) | **psycopg2-binary 2.9.10** | Cross-platform Postgres driver, no compile needed |
| DB (dev) | **SQLite** (`db.sqlite3`) | Zero-setup local dev |
| DB (prod) | **PostgreSQL / Supabase** | Managed Postgres, RLS, views, triggers |
| Task queue | **Celery 5.4 + Redis 5.2** | Delayed retry scheduling (`apply_async(countdown=...)`), Celery beat for cron jobs |
| HTTP client | **httpx 0.27** | Async, supports both Twilio & Ozonetel outbound APIs |
| Excel I/O | **openpyxl 3.1.5** | RTO import + redelivery export in XLSX |
| Timezone | **pytz** | `Asia/Kolkata` working-hours logic |
| File uploads | **python-multipart 0.0.12** | Multi-part form parsing for Excel uploads |
| Env loader | **python-dotenv 1.0.1** | Twelve-factor config |

### 2.2 Telephony providers (Block 7)

| Provider | Status | Notes |
|---|---|---|
| **Ozonetel KooKoo / CloudAgent** | Primary | India-first, TRAI-compliant, natively supports Google Wavenet in `<playtext>`, CloudAgent IVR Flows or raw CPaaS |
| **Twilio** | Alternative | International, better docs, higher per-minute cost |
| Fallback path | Twilio `<Say>` / Ozonetel `<playtext type="ggl">` | Never breaks — if AI voice fails, telco's own TTS speaks the line |

### 2.3 TTS (Text-to-Speech) chain (Block A)

Configured via `TTS_PROVIDERS=coqui,elevenlabs` — first available wins, others act as fallback.

| Backend | File | Role |
|---|---|---|
| **Coqui XTTS-v2** | `app/services/tts/coqui_backend.py` | Open-source, self-hosted, supports voice cloning from a 6-sec WAV sample, 15+ languages |
| **ElevenLabs** | `app/services/tts/elevenlabs_backend.py` | Paid, highest quality, `eleven_flash_v2_5` model default |
| **Microsoft Edge TTS** | `app/services/tts/edge_tts_backend.py` | Free tier via Microsoft |
| **gTTS (Google)** | `app/services/tts/gtts_backend.py` | Free, used for menu prompts |

**Cache is content-addressed**: filename = `sha256(text + backend_name + voice_settings)`. Any repeat phrase (welcome line, prompt) is synthesised **once** and reused forever. Startup pre-warms the cache across all 9 languages so the first real call has **zero synthesis latency**.

### 2.4 Ticketing chain (Block 9)

Configured via `TICKET_PROVIDERS=chatwoot,http`.

| Backend | File | Role |
|---|---|---|
| **Chatwoot** | `app/services/tickets/chatwoot_backend.py` | Open-source Zendesk alternative, self-hosted via Docker |
| **Generic HTTP** | `app/services/tickets/http_backend.py` | Adapter for Zendesk / Freshdesk / any REST ticket API |
| Local DB | `app/models/ticket.py` | Every ticket also mirrors to local `tickets` table so nothing is ever lost even if external system is down |

### 2.5 Infra & DevOps

| Component | Purpose |
|---|---|
| **Docker + docker-compose.yml** | Local one-command boot of API + Redis + Celery worker + Chatwoot |
| **Dockerfile** | Multi-stage Python 3.10 image for deploys |
| **Makefile** | Standardised commands: `make run`, `make worker`, `make smoke`, `make docker-up` |
| **render.yaml** | Render.com deploy manifest (API + worker + Redis) |
| **scripts/setup.sh** | Interactive first-time setup (creates venv, installs deps, prompts for provider choices) |
| **supabase/migrations/001_views_triggers_rls.sql** | Analytics views, auto-redelivery trigger, row-level security |
| **ngrok** | Local dev — Twilio/Ozonetel webhooks need a public URL |

### 2.6 Test & tooling

| Component | Purpose |
|---|---|
| `tests/` | Pytest suite: `test_logic.py`, `test_languages.py`, `test_regions.py`, `test_retention.py`, `test_tickets.py`, `test_tts.py`, `test_help_router.py` |
| `scripts/smoke_test.sh` | End-to-end smoke run against a live deployment |
| `scripts/prewarm_voice.py` | Force-generate all static prompts across all 9 languages |
| `scripts/init_db.py` | Bootstrap schema in a fresh DB |
| `scripts/send_test_event.py` | Simulate an ORDER_PLACED event |

---

## 3. Architecture — the 13 blocks

Every architectural block in the design spec maps to a real code module:

| # | Block | File | Responsibility |
|---|---|---|---|
| 1 | Event Source | External | Client's OMS / order-management system fires HTTP POST |
| 2 | Event Listener | `app/routes/event.py` | Validates payload, lazy-creates User + Order rows, hands off to Decision Engine |
| 3 | Decision Engine | `app/services/decision_engine.py` | Maps event → call type (CONFIRMATION / REJECTION), checks working hours |
| 4 | Call Manager | `app/services/call_manager.py` | Selects language, builds IVR script, calls Telephony provider |
| 5 | Retry Engine | `app/workers/retry_tasks.py` | Celery task chain — 3 attempts, 2 h apart, stops early on user response |
| 6 | Webhook Handler | `app/routes/webhook.py` | Receives DTMF / speech callbacks from telco, normalises input, invokes Action Engine |
| 7 | Telephony Provider | `app/services/telephony.py`, `app/services/kookoo_xml.py` | Twilio + Ozonetel CloudAgent + KooKoo CPaaS |
| 8 | IVR Flows | `app/services/ivr_scripts.py` | Confirmation & Rejection scripts, DTMF + speech normalisation, 9-language aliases |
| 9 | Action Engine | `app/services/action_engine.py`, `app/services/tickets/` | Updates OMS, creates tickets, spawns redelivery rows |
| 10 | Data Storage | `app/models/*.py` | 11 tables (see §5) |
| 11 | Monitoring & Alerts | `app/routes/monitoring.py` | `/health`, `/system-health` for backend liveness |
| 12 | Analytics & Reporting | `app/routes/analytics.py` | Dashboards: call quality, retention, retry effectiveness, language usage |
| 13 | RTO Recovery & Excel Sync | `app/routes/rto.py`, `app/workers/excel_export.py` | Excel import from courier, export of pending redeliveries |
| 14 | Ops-team callbacks | `app/routes/team.py`, `app/services/help_router.py` | Live-transfer during hours; callback queue after hours |
| 15 | Customer-care follow-up | `app/routes/customer_care.py` | Dashboard for help-request follow-through |
| — | TTS Chain | `app/services/tts/` | Coqui / ElevenLabs / Edge / gTTS with content-addressed cache |
| — | Working Hours | `app/core/working_hours.py` | Per-team, DB-configurable, timezone-aware |

---

## 4. End-to-end request flow (happy path)

```
┌──────────────────┐         POST /event/
│  Client's OMS    │ ───────────────────────────► ┌────────────────────────┐
└──────────────────┘                              │ FastAPI                │
                                                  │  routes/event.py       │
                                                  │  ├── validate payload  │
                                                  │  ├── decision_engine   │
                                                  │  ├── ensure User/Order │
                                                  │  └── schedule_retry_   │
                                                  │      chain()           │
                                                  └───────────┬────────────┘
                                                              │ Celery apply_async
                                                              ▼
                                                  ┌────────────────────────┐
                                                  │  Redis queue           │
                                                  └───────────┬────────────┘
                                                              │
                                                              ▼
                                                  ┌────────────────────────┐
                                                  │ Celery Worker          │
                                                  │  workers/retry_tasks.py│
                                                  │  → call_manager        │
                                                  │  → telephony (Twilio / │
                                                  │    Ozonetel)           │
                                                  └───────────┬────────────┘
                                                              │  Outbound call
                                                              ▼
                                                  ┌────────────────────────┐
                                                  │  Customer's phone      │
                                                  │  "Namaste, your order  │
                                                  │   1234 is out for      │
                                                  │   delivery. Press 1..."│
                                                  └───────────┬────────────┘
                                                              │  DTMF / speech
                                                              ▼
                                                  ┌────────────────────────┐
                                                  │ Telco webhook →        │
                                                  │  routes/webhook.py     │
                                                  │  → normalize_input()   │
                                                  │  → action_engine       │
                                                  │    ├── update OMS      │
                                                  │    ├── create ticket   │
                                                  │    │   (Chatwoot/HTTP) │
                                                  │    └── create          │
                                                  │        redelivery row  │
                                                  └────────────────────────┘
```

### Order Confirmation Call (event = `ORDER_PLACED`)

1. OMS POSTs `{order_id, user_phone, event_type: "ORDER_PLACED", state: "MH"}`
2. Decision Engine → CONFIRMATION flow
3. Retry Engine schedules attempt 1 immediately
4. Call Manager places call via Ozonetel/Twilio
5. Caller hears (in their language): "Namaste, this is a call about your recent order. Press 1 to confirm, press 2 for help."
6. Press **1** or say "confirm / haan / hoy" → OMS updated to `CONFIRMED`
7. Press **2** or say "help / madad" → if working hours, transferred to `TEAM_HUNT_GROUP`; else Chatwoot ticket created + callback queued
8. Retry chain stops as soon as `CallLog.response` is set

### Rejection Call (event = `ORDER_REJECTED`)

Same flow, three options:
- **1** — "Accept redelivery" → order → `RE_ATTEMPT_DELIVERY`, redelivery row created
- **2** — "Cancel" → order → `CANCELLED`, ticket created for internal review
- **3** — "Need help" → agent transfer or ticket, same as above

### Retry policy

| Attempt | Delay | Trigger |
|---|---|---|
| 1 | Immediate | On event receipt |
| 2 | +2 h | If no valid response |
| 3 | +2 h | If still no response |
| Stop | any time | `CallLog.response` becomes non-null (user pressed a valid key) |

**Idempotency**: a unique DB constraint `ux_retries_active_chain` on `(order_id, call_type)` for status ∈ (SCHEDULED, RUNNING) guarantees only one active chain per order. Duplicate events are logged and ignored.

---

## 5. Data model (11 tables)

**Core 5 (call automation):**

| Table | Model | Purpose |
|---|---|---|
| `users` | `User` | Phone → language, delivery state |
| `orders` | `Order` | Order + OMS status + RTO flag |
| `call_logs` | `CallLog` | Every attempt, response captured (early-stop signal) |
| `retry` | `RetryRecord` | Attempt count, next attempt time, status |
| `tickets` | `Ticket` | Local mirror of every ticket created externally |
| `audit_logs` | `AuditLog` | Immutable event trail — every decision, every retry, every duplicate |

**RTO & analytics 3:**

| Table | Model | Purpose |
|---|---|---|
| `redeliveries` | `Redelivery` | Auto-created when customer accepts re-attempt |
| `file_imports` | `FileImport` | Audit of every Excel upload |
| `working_hours_config` | `WorkingHoursConfig` | Per-team hours + timezone + live-transfer toggle |

**Ops team 2:**

| Table | Model | Purpose |
|---|---|---|
| `help_requests` | `HelpRequest` | Customer requested help; needs follow-through |
| `team_call_logs` | `TeamCallLog` | Ops-team outbound calls to help-requesters, outcome tracking |

### Supabase-side additions (`supabase/migrations/001_views_triggers_rls.sql`)

- `v_call_quality_breakdown` — working/non-working/beneficial calls per language per day
- `v_customer_retention` — lifetime value + retention score, prioritise customers worth keeping
- `v_retry_effectiveness` — should you cap retries at 3 instead of 4? Data-driven answer
- `v_language_usage` — which language has highest IVR conversion
- `v_working_hours_split` — after-hours call ROI
- Auto-trigger: pressing "1" on rejection call inserts redelivery row automatically at DB level
- RLS policies scope reads to authenticated staff

---

## 6. Multi-language IVR (9 languages)

| Code | Language |
|---|---|
| en | English |
| hi | Hindi |
| ta | Tamil |
| te | Telugu |
| kn | Kannada |
| ml | Malayalam |
| bn | Bengali |
| mr | Marathi |
| gu | Gujarati |

Language selection modes:
- **Auto by state**: Maharashtra → Marathi, Tamil Nadu → Tamil, etc. (`app/services/regions.py`)
- **Language picker**: If unknown, welcome menu offers digit-per-language selection
- **Sticky**: User's preferred language is remembered per phone; picker skipped on repeat calls (unless `FORCE_LANGUAGE_PICKER=true` in dev)

Speech recognition accepts **code-mixed input** ("cancel kar do", "confirm please") by matching the first word against both English and the chosen language's alias table.

---

## 7. RTO Recovery & Excel Sync (the commercial killer feature)

This is where the system pays for itself. Indian e-commerce loses billions to RTO. The flow:

1. **Courier delivers .xlsx** of RTO orders (columns: `order_id`, `user_phone`, `product_name`, `sku`, `quantity`, `order_value`, `cod_amount`, `payment_mode`, `address`, `city`, `state`, `pincode`, `awb_number`, `courier`, `rto_reason`, `rto_date`)
2. **`POST /rto/import`** — upload → parses Excel → populates `orders` table → creates/updates `users`
3. Existing `/event/` endpoint fires with `event_type=ORDER_REJECTED` → IVR triggers
4. Customer presses **1** (accept re-attempt) → `action_engine.py` auto-creates a `redeliveries` row + sets `orders.oms_status = RE_ATTEMPT_DELIVERY`
5. Daily, `GET /rto/redeliveries/export` → downloads Excel of pending redeliveries → send to courier
6. Rows marked `exported_to_excel=true` so they don't reappear tomorrow
7. Celery beat can automate daily export at 22:00 IST with SMTP email (`app/workers/excel_export.py`)

**Business outcome**: what was a manual, error-prone spreadsheet-and-phone process now runs on autopilot with a clean audit trail.

---

## 8. Analytics & insights

`app/routes/analytics.py` + Supabase views give the founder / ops team ready answers to:

- Which language converts best?
- Which state has highest RTO acceptance?
- Are after-hours calls worth the cost?
- Should we cap retries at 2, 3, or 4?
- Which customers are worth retaining (retention score > 70)?
- What's today's working / non-working / beneficial call split?

All queryable via HTTP endpoints or directly via SQL in Supabase.

---

## 9. Reliability & resilience

| Concern | How it's addressed |
|---|---|
| Telco outage | Retry chain resumes on next attempt; state persisted in DB |
| TTS provider outage | Fallback chain: Coqui → ElevenLabs → telco's native `<Say>` / `<playtext>` |
| Ticket provider outage | Local `tickets` table always written; external creation retried on next boot |
| Duplicate events | `ux_retries_active_chain` unique constraint + `EVENT_DUPLICATE_IGNORED` audit log |
| Zombie retry rows | Reuse-existing pattern: if a SCHEDULED/RUNNING row exists, update it rather than insert |
| DB migrations | SQLAlchemy `create_all` for dev + Alembic-ready structure; Supabase SQL file for prod views |
| Config drift | 12-factor via `.env` + `pydantic-settings` (typed, validated at boot) |
| Observability | Structured logs (`app/core/logging.py`), `AuditLog` table, `/system-health` endpoint |

---

## 10. Deployment options

| Target | How |
|---|---|
| Local dev | `make setup` → `make run` + `make worker` + `ngrok http 8000` |
| Docker (single host) | `make docker-up` (API + Redis + worker + optional Chatwoot) |
| Render.com | `render.yaml` provides web + worker + Redis blueprint |
| Supabase Pro (DB) | Set `DATABASE_URL`, run `001_views_triggers_rls.sql`, done |
| Any Postgres host | Same — vendor-neutral SQLAlchemy |

---

## 11. Security posture (current)

- All secrets in `.env` (not committed — a prior `git` incident removed leaked secrets, see `Removed secret files` commit)
- Twilio / Ozonetel webhooks currently trust the caller's IP + payload shape — **should add HMAC signature validation before prod for a security-sensitive client**
- Supabase RLS policies enabled for staff read scoping
- No customer PII beyond phone + state stored; addresses only during RTO flow

**Recommendations before shipping to an enterprise client:**
1. Add Twilio request signature validation (`X-Twilio-Signature`)
2. Add Ozonetel HMAC on webhook path
3. Move OMS/Notification API keys to a secrets manager (AWS SM / GCP SM / Doppler)
4. Enable audit-log immutability at the DB level (append-only trigger)
5. Add rate limits on `/event/` (currently unauthenticated)

---

## 12. Where the project is strong vs where it needs work

### Strong
- Clean 13-block separation → easy to swap any layer (telephony, TTS, tickets)
- Zero-cost open-source path validated end-to-end
- 9-language IVR with real speech normalisation, not just DTMF
- Idempotency + retry logic hardened by real bugs found in test data
- Excel-in / Excel-out RTO flow is production-shaped, not a demo
- Content-addressed TTS cache is genuinely elegant

### Needs work before enterprise pilot
- Webhook signature verification (Twilio + Ozonetel)
- Alembic migrations instead of `create_all`
- Structured metrics (Prometheus / OpenTelemetry) not just logs
- Multi-tenant awareness (currently one client per deploy)
- CI/CD pipeline (currently manual `make` commands)
- Dashboard UI — analytics exist as JSON endpoints, no visualisation layer

---

## 13. Suggested next steps (founder-facing)

1. **Pilot with one D2C brand** doing 200-500 COD orders/day. Measure RTO reduction over 30 days.
2. **Multi-tenant refactor** — one deploy, many `client_id` scopes — so second and third clients don't need separate infra.
3. **Build a lightweight dashboard** (Next.js + the existing analytics endpoints) so the client sees results, not raw JSON.
4. **Harden security** (webhook sigs, rate limits, secrets manager) before signing an enterprise deal.
5. **Package as SAIF-style delivery** under saasinator AI: fixed-price pilot with clear phase gates.

---

## 14. Appendix — key file map

```
app/
├── main.py                        # FastAPI entry, lifespan, TTS pre-warm
├── core/
│   ├── config.py                  # All env-driven settings (Pydantic)
│   ├── logging.py                 # Structured logger
│   └── working_hours.py           # Timezone-aware hours check
├── db/session.py                  # SQLAlchemy engine + session factory
├── models/                        # 11 SQLAlchemy tables
├── routes/
│   ├── event.py                   # Block 2 — event ingestion
│   ├── webhook.py                 # Block 6 — telco callback handling
│   ├── audio.py                   # Serve cached TTS audio to telco
│   ├── monitoring.py              # Health checks
│   ├── analytics.py               # Insights endpoints
│   ├── rto.py                     # RTO import / export
│   ├── team.py                    # Ops-team callback logging
│   └── customer_care.py           # Follow-up dashboard endpoints
├── services/
│   ├── decision_engine.py         # Block 3
│   ├── call_manager.py            # Block 4
│   ├── telephony.py               # Twilio + Ozonetel outbound
│   ├── kookoo_xml.py              # Ozonetel KooKoo XML dialect
│   ├── ivr_scripts.py             # Block 8 — IVR menus, speech normalisation
│   ├── action_engine.py           # Block 9 — OMS + ticket + redelivery
│   ├── help_router.py             # Live-transfer vs after-hours ticket
│   ├── retention.py               # Scoring
│   ├── regions.py                 # State → language mapping
│   ├── greetings.py               # Language menu + defaults
│   ├── translations.py            # 9-language prompt strings
│   ├── tts/                       # TTS chain (coqui, elevenlabs, edge, gtts)
│   └── tickets/                   # Ticket chain (chatwoot, http)
├── workers/
│   ├── celery_worker.py           # Celery app
│   ├── retry_tasks.py             # Block 5 — retry chain
│   └── excel_export.py            # Daily RTO Excel export beat task
└── schemas/                       # Pydantic request/response models

scripts/
├── setup.sh                       # Interactive first-run
├── smoke_test.sh                  # End-to-end smoke
├── prewarm_voice.py               # Pre-generate all static prompts
├── generate_audio.py              # Regenerate Ozonetel-format WAVs
├── init_db.py                     # Bootstrap DB
└── send_test_event.py             # Trigger a test call

supabase/migrations/001_views_triggers_rls.sql   # Analytics + triggers + RLS
tests/                                            # Pytest suite
samples/rto_orders_sample.xlsx                    # Reference Excel format
```

---

**Bottom line**: this is a well-architected, cost-conscious, production-shaped microservice that solves a real, measurable e-commerce problem (RTO) with a modern open-source-first stack. It is one security hardening pass and one multi-tenancy refactor away from being a genuine saasinator AI product line, not just an internal tool.
