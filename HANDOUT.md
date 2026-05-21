# Divine Hindu — AI Call System Build Handout

> **How to use this file:** Paste each prompt into Claude Code in VS Code, **one at a time, in order.** Wait for tests/manual check to pass before moving on. Do NOT paste the whole document — Claude Code does best with one scoped change at a time.
>
> **Source of truth for current state:** [`CLAUDE.md`](CLAUDE.md). This handout extends it.

---

## 0. Where you are right now (don't redo this)

✅ Already built:
- FastAPI app + SQLite (db.sqlite3) + Redis + Celery worker
- Multi-language IVR with **Edge TTS neural voices** for all 9 Indian languages (free)
- Models: `User`, `CallLog`, `Order`, `Redelivery`, `Ticket`, `RetryRecord`, `AuditLog`, `FileImport`
- Routes: `/event/`, `/webhook/voice-start`, `/webhook/language-select`, `/webhook/voice`, `/webhook/handle`, `/webhook/status`, `/rto/import`, `/rto/redeliveries/export`, `/rto/insights`, `/analytics/summary`, `/analytics/export/excel`
- Action engine: confirmation → `Order.oms_status='CONFIRMED'`; rejection-accept → `Redelivery` row; rejection-reject → `Order.oms_status='CANCELLED'`; help → `Ticket` row via Chatwoot
- Working-hours **flag** in `app/core/working_hours.py` (just a True/False check, no per-day config yet)
- Edge TTS, gTTS, ElevenLabs in TTS chain; Chatwoot ticket integration

❌ The gap (what this handout adds):
1. `team_call_logs` table — record what happens when ops team calls a customer back
2. `working_hours_config` table — per-team start/end/days, replace `.env`-only config
3. `help_router.py` service — decide live transfer vs queued callback at help time
4. `POST /team/call-result` endpoint — ops team logs the result of their callback
5. **5 Postgres analytics views** — funnel, hourly heatmap, retention, language perf, team-vs-IVR, working-hours split
6. **Customer retention score** field on `User` + auto-recompute on order status change
7. **Daily Excel export Celery task** (cron at 22:00 IST) — currently endpoint-only
8. **Migration to Supabase Postgres** (optional but recommended for analytics + RLS + backups)

---

## 1. Database plan — SQLite now, Supabase Pro later

You can run **everything in this handout on the existing SQLite first** and migrate to Supabase Pro when you're ready to go live. The models below work in both.

### Why Supabase Pro for production
- Managed Postgres (~$25/mo) — analytics views, indexes, triggers all just work
- Row-level security, daily backups, point-in-time recovery
- Better than SQLite for concurrent writes (Celery worker + webhook hits)

### Migration path
1. Build all the new tables/code on SQLite first (Prompts 1–7)
2. Once stable, point `DATABASE_URL` at Supabase Postgres
3. Run `Base.metadata.create_all` once to create the schema
4. Recreate the `audio_cache/` directory on the new host (or move to S3/R2)

---

## 2. New tables (Prompt 1)

### `team_call_logs`
| col | type | notes |
|---|---|---|
| id | INT PK | autoincrement |
| ticket_id | INT FK → tickets | which help-ticket spawned this callback |
| order_id | INT FK → orders | the order being discussed |
| call_log_id | INT FK → call_logs (nullable) | original IVR call that asked for help |
| agent_id | VARCHAR(64) | ops staff member id |
| called_at | DATETIME | when the team dialed |
| duration_seconds | INT | call length |
| outcome | VARCHAR(32) | `accepted` \| `rejected` \| `wants_callback` \| `no_response` \| `wrong_number` |
| notes | TEXT | free-form |
| is_within_working_hours | BOOLEAN | whether the team called inside business hours |
| created_at | DATETIME | |

### `working_hours_config`
| col | type | notes |
|---|---|---|
| id | INT PK | |
| team_name | VARCHAR(64) UNIQUE | `default`, `escalations`, etc. |
| start_hour | INT | 9 |
| end_hour | INT | 19 |
| days_of_week | VARCHAR(32) | `mon,tue,wed,thu,fri,sat` (lowercase, comma-separated) |
| timezone | VARCHAR(64) | `Asia/Kolkata` |
| live_transfer_enabled | BOOLEAN | true |
| updated_at | DATETIME | |

Seed one row at startup: `team_name='default'`, `start_hour=9`, `end_hour=19`, `days='mon,tue,wed,thu,fri,sat'`, `timezone='Asia/Kolkata'`.

### `users` — add one column
| col | type | notes |
|---|---|---|
| retention_score | NUMERIC(4,3) DEFAULT 0 | 0.000–1.000, recomputed when order status changes |

---

### Prompt 1 — Add the new tables + retention column

```
Add three database changes to the existing project:

1. NEW model file `app/models/team_call_log.py` for table `team_call_logs` with the columns from §2 of HANDOUT.md. Use SQLAlchemy patterns matching `app/models/ticket.py`. Add to `app/models/__init__.py` exports.

2. NEW model file `app/models/working_hours_config.py` for table `working_hours_config` from §2. Add to `__init__.py`.

3. EDIT `app/models/user.py` — add a `retention_score` column (Numeric(4,3), default=0, nullable=False). Do NOT touch any other column.

4. In `app/main.py` lifespan startup, after `Base.metadata.create_all(...)`, add a one-shot seed: if `working_hours_config` has zero rows, insert a row with team_name='default', start_hour=9, end_hour=19, days_of_week='mon,tue,wed,thu,fri,sat', timezone='Asia/Kolkata', live_transfer_enabled=True.

After applying, run `python -c "from app.db.session import Base, engine; Base.metadata.create_all(bind=engine)"` so SQLite gets the new tables. Verify with `sqlite3 db.sqlite3 ".tables"` — should now include team_call_logs and working_hours_config.

Do not change any existing model fields, do not touch routes, do not touch services.
```

---

## 3. Help router service (Prompt 2)

Right now [app/routes/webhook.py](app/routes/webhook.py) has this placeholder when help is requested during working hours:
```python
if is_help and is_working_hours():
    response.dial("+10000000000")
```

We need a real **help_router** that:
- Reads `working_hours_config` row for `team_name='default'`
- Converts UTC → IST and checks if NOW falls inside any active window
- If **inside hours** → `<Dial>` to the team hunt-group number, mark ticket `routing='connected_to_team'`
- If **outside hours** → compute the next working slot, store it on ticket as `scheduled_callback_at`, mark `routing='queued_after_hours'`, and have the IVR speak "Our team will call you back at <time>" in the user's language

### Prompt 2 — Build help_router

```
Create `app/services/help_router.py` with a single public function:

    def route_help_request(
        db: Session,
        *,
        ticket_id: int,
        call_id: int,
        order_id: int,
        user_phone: str,
        lang: str = "en",
    ) -> dict

Behavior:
1. Read working_hours_config WHERE team_name='default'. If missing, fall back to start=9 end=19 days=mon-sat tz=Asia/Kolkata.
2. Convert datetime.utcnow() to that timezone (use pytz; install via `pip install pytz` and add to requirements.txt).
3. Compute is_open = (today's weekday in days_of_week) AND (start_hour <= hour < end_hour) AND live_transfer_enabled.
4. If is_open: update Ticket row with status='OPEN', external fields routing='connected_to_team', priority='live'. Return {'mode': 'live_transfer', 'dial_number': settings.TEAM_HUNT_GROUP, 'spoken_message': t(P_AGENT_TRANSFER, lang)}. Add a TEAM_HUNT_GROUP setting to app/core/config.py (default empty string) and to .env.example.
5. If closed: compute next_working_slot (next occurrence of an active weekday + start_hour in the configured timezone). Store on Ticket as scheduled_callback_at (add this DateTime column to the Ticket model + create_all). Update ticket routing='queued_after_hours'. Return {'mode': 'queued', 'next_slot': next_working_slot_iso, 'spoken_message': <"Our team will call you back at <time>" translated to lang — add P_CALLBACK_QUEUED to translations.py for all 9 languages>}.
6. Append to AuditLog: event_type='HELP_ROUTED', description=f'ticket={ticket_id} mode={mode} ...', source='help_router'.

Do not modify webhook.py in this prompt — that's prompt 3. Add unit tests in tests/test_help_router.py covering: weekday business hours (Tuesday 14:00 IST → live_transfer), weekday after-hours (Tuesday 22:00 IST → queued, next_slot=Wednesday 09:00), Sunday (any hour → queued, next_slot=Monday 09:00).
```

---

## 4. Wire help_router into the webhook (Prompt 3)

### Prompt 3 — Replace the placeholder dial in webhook.py

```
Edit `app/routes/webhook.py`:

In the `/handle` endpoint, replace:

    if is_help and is_working_hours():
        response.dial("+10000000000")

with a call to the new help_router. The flow becomes:

1. When digit is "2" (CONFIRMATION) or "3" (REJECTION), the action_engine already creates a Ticket row. Capture the ticket_id from action_engine's return.
2. Call `help_router.route_help_request(db, ticket_id=..., call_id=call.call_id, order_id=call.order_id, user_phone=user_phone, lang=lang)`.
3. If the returned mode == 'live_transfer' AND a TEAM_HUNT_GROUP is configured: build_say(response, result['spoken_message'], lang=lang); response.dial(result['dial_number']).
4. If mode == 'queued' OR mode == 'live_transfer' but TEAM_HUNT_GROUP is empty: build_say(response, result['spoken_message'], lang=lang). Do not Dial.

Also update action_engine functions handle_confirmation_response and handle_rejection_response to RETURN the created ticket_id (or None) alongside the spoken message — change return signature from `str` to `tuple[str, int|None]`. Update all call sites.

Do not change anything else.
```

---

## 5. Team result endpoint (Prompt 4)

When the ops team dials the customer back (after a queued callback), they need to log the outcome. This is what closes the loop and lets analytics compare "IVR-only" vs "IVR-then-team" success.

### Prompt 4 — Build POST /team/call-result

```
Create `app/routes/team.py` with one endpoint:

    POST /team/call-result
    Body (JSON):
      ticket_id: int
      agent_id: str
      duration_seconds: int
      outcome: "accepted" | "rejected" | "wants_callback" | "no_response" | "wrong_number"
      notes: str | None
      next_action: "create_redelivery" | "cancel_order" | None  (only for REJECTION tickets)

    Behavior:
      1. Look up ticket → order_id, call_log_id
      2. Insert team_call_logs row with all fields + is_within_working_hours computed via help_router or pytz
      3. If outcome='accepted' on a REJECTION ticket and next_action='create_redelivery': insert Redelivery row (delivery_status='SCHEDULED'), update Order.oms_status='RE_ATTEMPT_DELIVERY'
      4. If outcome='accepted' on a CONFIRMATION ticket: update Order.oms_status='CONFIRMED', confirmed_at=NOW()
      5. If outcome='rejected': update Order.oms_status='CANCELLED', cancelled_at=NOW()
      6. If outcome='wants_callback': insert RetryRecord scheduled +2h
      7. Update Ticket.status='CLOSED', assigned_to=agent_id
      8. Recompute users.retention_score for the user_phone (helper from Prompt 5)
      9. Append AuditLog event_type='TEAM_CALL_LOGGED', source='team'

    Wire into app/main.py.

Add tests/test_team_call_result.py covering each outcome + each next_action.
```

---

## 6. Retention score (Prompt 5)

### Prompt 5 — Auto-compute retention_score

```
Create `app/services/retention.py` with a single function:

    def recompute_retention_score(db: Session, user_phone: str) -> float:
        """
        retention_score = lifetime_confirmed_orders / max(1, lifetime_orders)
        Counts orders where oms_status IN ('CONFIRMED','REDELIVERED','RE_ATTEMPT_DELIVERY','DELIVERED')
        as confirmed; total includes 'CANCELLED','RTO_PENDING' too.
        Updates users.retention_score and returns the new score.
        """

Call this helper from:
  - action_engine.handle_confirmation_response (after order status update)
  - action_engine.handle_rejection_response (after order status update)
  - team route POST /team/call-result (after order status update)

Add tests in tests/test_retention.py: a user with 4 confirmed of 5 orders has score 0.800.
```

---

## 7. Analytics views + endpoints (Prompt 6)

The current `/analytics/summary` returns aggregate counts. The handout's KPIs need a richer view layer. **On SQLite we use Python computation; on Postgres we use proper VIEWs** — the route layer is the same.

### Prompt 6 — Build analytics views and endpoints

```
Add to `app/routes/analytics.py` four new endpoints (keep the existing /summary and /export/excel as-is):

    GET /analytics/funnel?from=YYYY-MM-DD&to=YYYY-MM-DD
        Per (day, call_type): called, connected, responded, accepted, acceptance_pct.
        Implementation: SQLAlchemy group_by date + call_type on call_logs.

    GET /analytics/hourly
        24x7 grid (hour-of-day x day-of-week) of acceptance_pct, last 30 days.
        Implementation: group_by extract('hour', timestamp), extract('dow', timestamp).

    GET /analytics/retention
        Per-user list (top 100 by score): user_phone, preferred_language, retention_score, last_order_at, lifetime_orders.

    GET /analytics/team-vs-ivr?days=90
        Per order in the window: order_id, final_status, resolved_by_ivr (bool), resolved_by_team (bool), ivr_attempts, team_attempts.
        Then summary at top: total_orders, ivr_only_resolved, team_assisted_resolved, both, neither, team_assist_lift_pct.

    GET /analytics/language-performance
        Per language: total_calls, acceptance_pct, avg_call_duration_seconds, retry_count.

    GET /analytics/working-hours-split
        live_transfer_attempts, live_transfer_acceptance_pct,
        queued_callback_attempts, queued_callback_acceptance_pct,
        difference (lift).

For each endpoint, build a Python computation that works on SQLite. Wrap each function so that if settings.DATABASE_URL starts with 'postgresql' it can be swapped for a raw SQL view query later — for now just compute in Python.

Also add cache: import functools.lru_cache OR use the existing redis client (settings.REDIS_URL) to cache each response for 300s keyed by query string.

Tests: tests/test_analytics_views.py — seed 10 calls of each type, assert each endpoint returns expected shape and arithmetic.
```

### When you migrate to Supabase Pro (later)

Add a migration `supabase/migrations/0001_analytics_views.sql` with these views. The Python endpoints can then `SELECT * FROM v_acceptance_funnel` etc. instead of computing in Python.

```sql
-- v_acceptance_funnel
CREATE OR REPLACE VIEW v_acceptance_funnel AS
SELECT
  date_trunc('day', timestamp) AS day,
  call_type,
  COUNT(*) AS called,
  COUNT(*) FILTER (WHERE status IN ('ANSWERED','COMPLETED')) AS connected,
  COUNT(*) FILTER (WHERE response IS NOT NULL) AS responded,
  COUNT(*) FILTER (
    WHERE (call_type = 'CONFIRMATION' AND response = '1')
       OR (call_type = 'REJECTION' AND response = '1')
  ) AS accepted,
  ROUND(100.0 * COUNT(*) FILTER (
    WHERE (call_type = 'CONFIRMATION' AND response = '1')
       OR (call_type = 'REJECTION' AND response = '1')
  ) / NULLIF(COUNT(*), 0), 2) AS acceptance_pct
FROM call_logs
GROUP BY 1, 2 ORDER BY 1 DESC, 2;

-- v_team_vs_ivr
CREATE OR REPLACE VIEW v_team_vs_ivr AS
SELECT
  o.order_id,
  o.oms_status AS final_status,
  EXISTS (SELECT 1 FROM call_logs WHERE order_id = o.order_id AND response IN ('1')) AS resolved_by_ivr,
  EXISTS (SELECT 1 FROM team_call_logs WHERE order_id = o.order_id AND outcome = 'accepted') AS resolved_by_team,
  (SELECT COUNT(*) FROM call_logs WHERE order_id = o.order_id) AS ivr_attempts,
  (SELECT COUNT(*) FROM team_call_logs WHERE order_id = o.order_id) AS team_attempts
FROM orders o
WHERE o.created_at > NOW() - INTERVAL '90 days';

-- v_language_performance
CREATE OR REPLACE VIEW v_language_performance AS
SELECT
  language,
  COUNT(*) AS total_calls,
  ROUND(100.0 * COUNT(*) FILTER (WHERE response = '1') / NULLIF(COUNT(*), 0), 2) AS acceptance_pct
FROM call_logs
WHERE language IS NOT NULL
GROUP BY language ORDER BY total_calls DESC;
```

---

## 8. Daily Excel export job (Prompt 7)

`/rto/redeliveries/export` already exists as an on-demand endpoint. Production needs a Celery beat task that runs nightly.

### Prompt 7 — Schedule the daily Excel export

```
Edit `app/workers/retry_tasks.py` (or create `app/workers/excel_export.py` if you prefer to keep concerns separate):

1. Add a Celery task `daily_redelivery_export()` that:
   - Queries Redelivery WHERE delivery_status='SCHEDULED' AND exported_to_excel=False
   - Generates an .xlsx workbook with columns: order_id, user_phone, address, preferred_date, preferred_time_slot, courier_partner
   - Writes to `EXCEL_EXPORT_DIR/redeliveries_YYYYMMDD.xlsx` (add EXCEL_EXPORT_DIR to config.py, default './exports')
   - If `EXCEL_EXPORT_EMAIL` is set: send via SMTP (use settings.SMTP_*; add those settings + email helper)
   - Sets exported_to_excel=True, excel_export_at=NOW(), excel_file_name=...
   - Inserts FileImport row with file_type='xlsx_export' and status='completed'

2. In `app/workers/celery_worker.py` add a beat schedule:
       beat_schedule = {
           'daily-redelivery-export': {
               'task': '<full task name>',
               'schedule': crontab(hour=22, minute=0),  # 22:00 UTC = 03:30 IST next day; use 16:30 UTC for 22:00 IST
           }
       }
   Use UTC in the cron expression; document the IST equivalent in a comment.

3. Run `celery -A app.workers.celery_worker beat -l info` in addition to the existing worker process. Document this in CLAUDE.md §7.

Tests: tests/test_excel_export.py — seed 3 unfulfilled redeliveries, run the task, verify file written + rows marked exported.
```

---

## 9. Acceptance criteria — when is the build done?

After all 7 prompts succeed, manually verify each:

### Phase 1 — Confirmation
- [ ] `POST /event/ {event_type:'ORDER_PLACED'}` creates `Order` (status `PLACED`), queues call.
- [ ] Call answered, press `1` → `Order.oms_status='CONFIRMED'`, `confirmed_at` set, `User.retention_score` recomputed.
- [ ] Call answered, press `2` → `Ticket` created. If working hours: live transfer dialed. If after hours: ticket has `scheduled_callback_at` set to next 09:00 IST.
- [ ] No answer → 4 retry attempts on schedule, then ticket auto-created with note 'unreachable'.
- [ ] Every state change appears in `audit_logs`.

### Phase 2 — Rejection / Redelivery
- [ ] `POST /event/ {event_type:'ORDER_REJECTED'}` OR `POST /rto/import` of a row creates `Order` with `is_rto=true`, queues REJECTION call.
- [ ] Press `1` → `Redelivery` row inserted, `Order.oms_status='RE_ATTEMPT_DELIVERY'`.
- [ ] Press `2` → `Order.oms_status='CANCELLED'`, retention recomputed.
- [ ] Press `3` → `Ticket` created, help_router fires.
- [ ] Daily Celery beat at 22:00 IST writes `redeliveries_YYYYMMDD.xlsx` and flips `exported_to_excel=True`.

### Working hours
- [ ] Press 2 (help) at 14:00 Tuesday IST → ticket.routing='connected_to_team', live transfer dialed to TEAM_HUNT_GROUP.
- [ ] Press 2 at 22:00 Saturday IST → ticket.routing='queued_after_hours', scheduled_callback_at = next Mon 09:00.
- [ ] Press 2 on Sunday → queued, scheduled_callback_at = Mon 09:00.

### Team callback
- [ ] `POST /team/call-result` with outcome='accepted' on REJECTION ticket + next_action='create_redelivery' → Redelivery row appears, Order status updates, ticket closes.
- [ ] team_call_logs row records is_within_working_hours correctly.

### Analytics
- [ ] `GET /analytics/summary` works (existing).
- [ ] `GET /analytics/funnel?from=2026-05-01&to=2026-05-31` returns daily breakdown.
- [ ] `GET /analytics/hourly` returns 24×7 grid.
- [ ] `GET /analytics/retention` returns top users with scores.
- [ ] `GET /analytics/team-vs-ivr` returns per-order resolution attribution.
- [ ] `GET /analytics/language-performance` shows acceptance % per language.
- [ ] `GET /analytics/working-hours-split` shows live vs queued lift.

---

## 10. Required `.env` additions

```dotenv
# Team callback (set to your real ops phone or SIP)
TEAM_HUNT_GROUP=+91XXXXXXXXXX

# Excel export
EXCEL_EXPORT_DIR=./exports
EXCEL_EXPORT_EMAIL=ops@divinehindu.in     # optional, if set the export is emailed
SMTP_HOST=
SMTP_PORT=587
SMTP_USER=
SMTP_PASS=
SMTP_FROM=Divine Hindu IVR <ivr@divinehindu.in>

# Supabase (only when migrating from SQLite)
# DATABASE_URL=postgresql://postgres:<pwd>@db.<ref>.supabase.co:5432/postgres
# SUPABASE_URL=https://<ref>.supabase.co
# SUPABASE_SERVICE_ROLE_KEY=<service_role_key>     # backend only
```

---

## 11. How analytics will help other teams (the "why")

| Team | Metric they use | Decision it drives |
|---|---|---|
| **Sales** | `/analytics/retention` | Lock low-retention customers to prepaid; reward high-retention with discounts |
| **Marketing** | `/analytics/hourly` | Schedule promo SMS at peak conversion hours |
| **Operations** | `/analytics/working-hours-split` | Extend team hours only if queued-callback lift justifies it |
| **Product** | `/analytics/language-performance` | Add new languages where current ones underperform |
| **Finance** | `/analytics/team-vs-ivr` + cost feed | Cost-per-recovered-order, IVR ROI, cost-to-serve |
| **CX / Ops manager** | `/analytics/funnel` | Spot day-over-day funnel drops, find broken IVR steps fast |

---

## 12. Order of operations (TL;DR)

1. **Prompt 1** — add tables (5 min)
2. **Prompt 2** — help_router service (30 min)
3. **Prompt 3** — wire it into webhook (15 min)
4. **Prompt 4** — `/team/call-result` endpoint (30 min)
5. **Prompt 5** — retention score (15 min)
6. **Prompt 6** — analytics views (1–2 hr)
7. **Prompt 7** — daily Excel export Celery beat (45 min)

After everything works on SQLite → migrate to Supabase Pro per §1 (~1 hr including DNS/env update).

---

— End of Handout —
