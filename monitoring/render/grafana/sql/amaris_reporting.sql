-- Amaris aggregate-only Grafana reporting. No learner identifiers or raw payment payloads.
-- Apply separately to staging and production after backup/change approval.
BEGIN;
CREATE SCHEMA IF NOT EXISTS amaris_reporting;
REVOKE ALL ON SCHEMA amaris_reporting FROM PUBLIC;

DO $role$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'amaris_grafana_ro') THEN
    CREATE ROLE amaris_grafana_ro NOLOGIN NOINHERIT CONNECTION LIMIT 3;
  END IF;
END
$role$;
GRANT USAGE ON SCHEMA amaris_reporting TO amaris_grafana_ro;
ALTER ROLE amaris_grafana_ro SET default_transaction_read_only = on;
ALTER ROLE amaris_grafana_ro SET statement_timeout = '5s';
ALTER ROLE amaris_grafana_ro SET idle_in_transaction_session_timeout = '5s';

CREATE OR REPLACE VIEW amaris_reporting.bookings_daily AS
SELECT date_trunc('day', created_at) AS bucket,
       count(*)::bigint AS bookings,
       count(*) FILTER (WHERE status='confirmed')::bigint AS confirmed,
       count(*) FILTER (WHERE status='pending_payment')::bigint AS awaiting_payment,
       count(*) FILTER (WHERE status='payment_review')::bigint AS review_required
FROM public.content_liveclassbooking
GROUP BY 1;

CREATE OR REPLACE VIEW amaris_reporting.payments_daily AS
SELECT date_trunc('day', paid_time) AS bucket, service,
       count(*)::bigint AS paid_transactions,
       COALESCE(sum(amount), 0)::numeric(14,2) AS revenue_zar
FROM (
  SELECT COALESCE(paid_at,gateway_verified_at) AS paid_time, 'Live classes'::text AS service, amount
  FROM public.content_liveclassbooking
  WHERE gateway_verified_at IS NOT NULL AND currency='ZAR'
  UNION ALL
  SELECT COALESCE(paid_at,gateway_verified_at), 'Courses'::text, amount
  FROM public.content_payment
  WHERE gateway_verified_at IS NOT NULL AND currency='ZAR'
  UNION ALL
  SELECT COALESCE(paid_at,gateway_verified_at), 'Video requests'::text, amount
  FROM public.content_videorequest
  WHERE gateway_verified_at IS NOT NULL AND currency='ZAR'
) verified
GROUP BY 1,2;

CREATE OR REPLACE VIEW amaris_reporting.invoices_daily AS
SELECT date_trunc('day', issued_time) AS bucket, service,
       count(*)::bigint AS invoices_issued
FROM (
  SELECT issued_at AS issued_time, 'Courses'::text AS service
  FROM public.content_invoice WHERE invoice_number <> ''
  UNION ALL
  SELECT COALESCE(gateway_verified_at,paid_at) AS issued_time, 'Live classes'::text
  FROM public.content_liveclassbooking WHERE invoice_number <> ''
  UNION ALL
  SELECT COALESCE(gateway_verified_at,paid_at) AS issued_time, 'Video requests'::text
  FROM public.content_videorequest WHERE invoice_number <> ''
) issued
WHERE issued_time IS NOT NULL
GROUP BY 1,2;

CREATE OR REPLACE VIEW amaris_reporting.students_daily AS
SELECT date_trunc('day',created_at) AS bucket, count(*)::bigint AS registrations
FROM public.content_studentrecord
GROUP BY 1;

CREATE OR REPLACE VIEW amaris_reporting.email_status_daily AS
SELECT date_trunc('day',created_at) AS bucket,
       count(*)::bigint AS bookings,
       count(*) FILTER (WHERE confirmation_sent_at IS NOT NULL)::bigint AS student_sent,
       count(*) FILTER (WHERE tutor_confirmation_sent_at IS NOT NULL)::bigint AS tutor_sent,
       count(*) FILTER (WHERE admin_confirmation_sent_at IS NOT NULL)::bigint AS admin_sent
FROM public.content_liveclassbooking
WHERE status='confirmed'
GROUP BY 1;

CREATE OR REPLACE VIEW amaris_reporting.video_requests_daily AS
SELECT date_trunc('day',created_at) AS bucket,
       count(*)::bigint AS requests,
       count(*) FILTER (WHERE gateway_verified_at IS NOT NULL)::bigint AS payments_verified
FROM public.content_videorequest GROUP BY 1;

REVOKE ALL ON ALL TABLES IN SCHEMA amaris_reporting FROM PUBLIC;
GRANT SELECT ON amaris_reporting.bookings_daily,
                amaris_reporting.payments_daily,
                amaris_reporting.invoices_daily,
                amaris_reporting.students_daily,
                amaris_reporting.email_status_daily,
                amaris_reporting.video_requests_daily TO amaris_grafana_ro;
COMMIT;
