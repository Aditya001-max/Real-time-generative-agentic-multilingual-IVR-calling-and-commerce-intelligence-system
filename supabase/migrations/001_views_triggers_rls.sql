-- =====================================================================
-- AI Call Automation — Supabase Migration
-- =====================================================================
-- Run this once in Supabase SQL Editor AFTER your FastAPI app has
-- started up at least once (so SQLAlchemy creates the 8 tables).
--
-- This migration adds:
--   • Analytics views for the /rto/insights and /analytics endpoints
--   • DB trigger that auto-creates a redelivery row when a customer
--     accepts re-attempt (mirrors the Python logic in action_engine.py)
--   • Helper function mark_redeliveries_exported()
--   • Row-Level Security policies (only matter if a frontend talks
--     to Supabase directly; FastAPI uses service_role and bypasses RLS)
--
-- Tables created by SQLAlchemy:
--   users, call_logs, retries, tickets, audit_logs,
--   orders, redeliveries, file_imports
-- =====================================================================

-- =====================================================================
-- ANALYTICS VIEWS — read these from /rto/insights and /analytics endpoints
-- =====================================================================

-- View 1: Working / non-working / beneficial call breakdown per day
CREATE OR REPLACE VIEW v_call_quality_breakdown AS
SELECT
  DATE(timestamp) AS call_date,
  call_type,
  language,
  COUNT(*) AS total_calls,
  COUNT(*) FILTER (WHERE status IN ('ANSWERED','COMPLETED'))     AS working_calls,
  COUNT(*) FILTER (WHERE status NOT IN ('ANSWERED','COMPLETED')) AS non_working_calls,
  COUNT(*) FILTER (WHERE response IN ('1','confirm','accept'))    AS beneficial_calls,
  COUNT(*) FILTER (WHERE response IN ('2','cancel'))              AS resolved_negative,
  COUNT(*) FILTER (WHERE response IS NULL AND status = 'COMPLETED') AS no_response,
  ROUND(
    100.0 * COUNT(*) FILTER (WHERE status IN ('ANSWERED','COMPLETED'))
          / NULLIF(COUNT(*), 0), 2
  ) AS answer_rate_pct,
  ROUND(
    100.0 * COUNT(*) FILTER (WHERE response IN ('1','confirm','accept'))
          / NULLIF(COUNT(*), 0), 2
  ) AS beneficial_rate_pct
FROM call_logs
GROUP BY DATE(timestamp), call_type, language;

-- View 2: Per-customer retention scoring.
-- retention_score is in [0.000, 1.000] to match app/services/retention.py
-- (positive_orders / counting_orders). The Python writer is the source of
-- truth for users.retention_score; this view computes the same number on demand.
DROP VIEW IF EXISTS v_customer_retention;
CREATE VIEW v_customer_retention AS
SELECT
  u.user_id,
  u.phone_number,
  u.preferred_language,
  COUNT(DISTINCT cl.call_id) AS total_calls_received,
  COUNT(DISTINCT cl.call_id) FILTER (WHERE cl.status IN ('ANSWERED','COMPLETED')) AS calls_answered,
  COUNT(DISTINCT cl.call_id) FILTER (WHERE cl.response = '1') AS confirmations,
  COUNT(DISTINCT o.order_id) AS total_orders,
  COUNT(DISTINCT o.order_id) FILTER (WHERE o.oms_status = 'CONFIRMED')   AS orders_confirmed,
  COUNT(DISTINCT o.order_id) FILTER (WHERE o.oms_status = 'CANCELLED')   AS orders_cancelled,
  COUNT(DISTINCT o.order_id) FILTER (WHERE o.oms_status = 'REDELIVERED') AS orders_recovered,
  COALESCE(SUM(o.order_value)
    FILTER (WHERE o.oms_status IN ('CONFIRMED','REDELIVERED')), 0) AS lifetime_value,
  ROUND(
    CASE
      WHEN COUNT(DISTINCT o.order_id) FILTER (
        WHERE o.oms_status IN
          ('CONFIRMED','REDELIVERED','RE_ATTEMPT_DELIVERY','DELIVERED',
           'CANCELLED','RTO_PENDING')
      ) = 0 THEN 0.0
      ELSE
        COUNT(DISTINCT o.order_id) FILTER (
          WHERE o.oms_status IN
            ('CONFIRMED','REDELIVERED','RE_ATTEMPT_DELIVERY','DELIVERED')
        )::NUMERIC
        /
        COUNT(DISTINCT o.order_id) FILTER (
          WHERE o.oms_status IN
            ('CONFIRMED','REDELIVERED','RE_ATTEMPT_DELIVERY','DELIVERED',
             'CANCELLED','RTO_PENDING')
        )::NUMERIC
    END,
    3
  ) AS retention_score,
  MAX(cl.timestamp) AS last_contacted_at
FROM users u
LEFT JOIN call_logs cl ON cl.user_phone = u.phone_number
LEFT JOIN orders o     ON o.user_phone  = u.phone_number
GROUP BY u.user_id;

-- View 3: Retry engine effectiveness per attempt number
CREATE OR REPLACE VIEW v_retry_effectiveness AS
SELECT
  call_type,
  attempt_count,
  COUNT(*) AS retries_scheduled,
  COUNT(*) FILTER (WHERE status = 'COMPLETED') AS retries_succeeded,
  COUNT(*) FILTER (WHERE status = 'EXHAUSTED') AS retries_exhausted,
  COUNT(*) FILTER (WHERE status = 'STOPPED')   AS retries_stopped_early,
  ROUND(
    100.0 * COUNT(*) FILTER (WHERE status = 'COMPLETED') / NULLIF(COUNT(*), 0), 2
  ) AS success_rate_pct
FROM retries
GROUP BY call_type, attempt_count
ORDER BY call_type, attempt_count;

-- View 4: Pending redeliveries waiting for Excel export
CREATE OR REPLACE VIEW v_pending_redelivery_export AS
SELECT
  r.redelivery_id,
  o.order_id,
  o.user_phone,
  COALESCE(r.delivery_address_line1, o.address_line1) AS address_line1,
  COALESCE(r.delivery_city,    o.city)    AS city,
  COALESCE(r.delivery_state,   o.state)   AS state,
  COALESCE(r.delivery_pincode, o.pincode) AS pincode,
  o.product_name, o.product_sku, o.quantity, o.cod_amount,
  r.preferred_date, r.preferred_time_slot,
  r.courier_partner, o.awb_number AS original_awb,
  r.created_at AS scheduled_at
FROM redeliveries r
JOIN orders o ON o.order_id = r.order_id
WHERE r.exported_to_excel = FALSE
  AND r.delivery_status = 'SCHEDULED';

-- View 5: Language conversion comparison
CREATE OR REPLACE VIEW v_language_usage AS
SELECT
  language,
  COUNT(*) AS calls,
  COUNT(*) FILTER (WHERE status IN ('ANSWERED','COMPLETED')) AS answered,
  COUNT(*) FILTER (WHERE response = '1') AS positive_responses,
  ROUND(
    100.0 * COUNT(*) FILTER (WHERE response = '1') / NULLIF(COUNT(*), 0), 2
  ) AS conversion_pct
FROM call_logs
WHERE language IS NOT NULL
GROUP BY language
ORDER BY calls DESC;

-- View 6: Working hours vs after-hours performance
CREATE OR REPLACE VIEW v_working_hours_split AS
SELECT
  CASE
    WHEN EXTRACT(HOUR FROM timestamp AT TIME ZONE 'Asia/Kolkata') BETWEEN 9 AND 17
    THEN 'WORKING' ELSE 'AFTER_HOURS'
  END AS hours_bucket,
  COUNT(*) AS calls,
  COUNT(*) FILTER (WHERE status IN ('ANSWERED','COMPLETED')) AS answered,
  ROUND(
    100.0 * COUNT(*) FILTER (WHERE status IN ('ANSWERED','COMPLETED'))
          / NULLIF(COUNT(*), 0), 2
  ) AS answer_rate_pct
FROM call_logs
GROUP BY 1;


-- =====================================================================
-- TRIGGER: When CallLog.response is set → auto-create redelivery row +
--          update Order status. This duplicates what action_engine.py
--          does in Python — keeping both paths means consistency even
--          if a row is updated directly via SQL or Supabase Studio.
-- =====================================================================
CREATE OR REPLACE FUNCTION trg_create_redelivery_on_response()
RETURNS TRIGGER AS $$
BEGIN
  IF NEW.call_type = 'REJECTION' AND NEW.response = '1'
     AND (OLD.response IS NULL OR OLD.response IS DISTINCT FROM NEW.response) THEN
    INSERT INTO redeliveries (order_id, triggered_by_call_id, delivery_status)
    VALUES (NEW.order_id, NEW.call_id, 'SCHEDULED')
    ON CONFLICT DO NOTHING;
    UPDATE orders SET oms_status = 'RE_ATTEMPT_DELIVERY', updated_at = NOW()
    WHERE order_id = NEW.order_id;
  END IF;

  IF NEW.call_type = 'REJECTION' AND NEW.response = '2'
     AND (OLD.response IS NULL OR OLD.response IS DISTINCT FROM NEW.response) THEN
    UPDATE orders SET oms_status = 'CANCELLED', updated_at = NOW()
    WHERE order_id = NEW.order_id;
  END IF;

  IF NEW.call_type = 'CONFIRMATION' AND NEW.response = '1'
     AND (OLD.response IS NULL OR OLD.response IS DISTINCT FROM NEW.response) THEN
    UPDATE orders SET oms_status = 'CONFIRMED', updated_at = NOW()
    WHERE order_id = NEW.order_id;
  END IF;

  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_call_response ON call_logs;
CREATE TRIGGER trg_call_response
AFTER INSERT OR UPDATE OF response ON call_logs
FOR EACH ROW EXECUTE FUNCTION trg_create_redelivery_on_response();


-- =====================================================================
-- HELPER FUNCTION: Mark redeliveries as exported (called by /rto/redeliveries/export)
-- =====================================================================
CREATE OR REPLACE FUNCTION mark_redeliveries_exported(
  p_redelivery_ids INT[],
  p_file_name TEXT
) RETURNS INTEGER AS $$
DECLARE v_count INTEGER;
BEGIN
  UPDATE redeliveries
  SET exported_to_excel = TRUE,
      excel_export_at = NOW(),
      excel_file_name = p_file_name,
      updated_at = NOW()
  WHERE redelivery_id = ANY(p_redelivery_ids);
  GET DIAGNOSTICS v_count = ROW_COUNT;
  RETURN v_count;
END;
$$ LANGUAGE plpgsql;


-- =====================================================================
-- ROW LEVEL SECURITY
-- FastAPI uses the service_role key (set in DATABASE_URL connection
-- string with the service password) — that bypasses RLS automatically.
-- These policies only matter if you build a frontend that talks to
-- Supabase directly with the anon key.
-- =====================================================================
ALTER TABLE users         ENABLE ROW LEVEL SECURITY;
ALTER TABLE call_logs     ENABLE ROW LEVEL SECURITY;
ALTER TABLE retries       ENABLE ROW LEVEL SECURITY;
ALTER TABLE tickets       ENABLE ROW LEVEL SECURITY;
ALTER TABLE audit_logs    ENABLE ROW LEVEL SECURITY;
ALTER TABLE orders        ENABLE ROW LEVEL SECURITY;
ALTER TABLE redeliveries  ENABLE ROW LEVEL SECURITY;
ALTER TABLE file_imports  ENABLE ROW LEVEL SECURITY;

DO $$
DECLARE t TEXT;
BEGIN
  FOR t IN SELECT unnest(ARRAY['users','call_logs','retries','tickets','audit_logs',
                                'orders','redeliveries','file_imports'])
  LOOP
    EXECUTE format(
      'DROP POLICY IF EXISTS "auth_full_%I" ON %I;',
      t, t
    );
    EXECUTE format(
      'CREATE POLICY "auth_full_%I" ON %I FOR ALL TO authenticated USING (true) WITH CHECK (true);',
      t, t
    );
  END LOOP;
END $$;
