# WhatsApp notifications for Amaris bookings (draft PR #426)

**Source-only implementation. WhatsApp is OFF by default and production stays unchanged. The existing booking, email, and invoice flows continue.**

## Student workflow

1. Verified student opens Student Dashboard > WhatsApp reminders.
2. Student enters an international (E.164) number and explicitly checks the Amaris Mathematics Academy booking-message consent checkbox. A number in a registration form is NOT consent.
3. Student chooses tutor/time and completes PayFast checkout.
4. Django must verify the PayFast payment and mark the live-class booking CONFIRMED with a non-null paid_at before WhatsApp is eligible.
5. Celery Beat scans for a confirmation every minute; an eligible opted-in recipient receives the approved Meta Utility confirmation template once per booking and class start time.
6. Celery Beat scans the next 30 minutes of classes; at 30 minutes before class (within the next one-minute scan), the student and separately opted-in tutor receive an approved Meta Utility reminder. All dates in the message are Africa/Johannesburg / SAST (UTC+2).
7. Each message contains booking reference, topic, start time and tutor. The recipient opens the authenticated dashboard for Zoom details. No meeting URL or payment secret is sent on WhatsApp.
8. Students can turn WhatsApp off on their dashboard, or reply STOP, UNSUBSCRIBE, CANCEL, QUIT or END to the WhatsApp number. A valid, signed Meta inbound webhook disables future WhatsApp reminders for that phone number. Email continues.
9. START replies do not silently grant consent again; a new explicit opt-in is required in the authenticated dashboard.

## Reliability, idempotency and delivery states

- One database-backed outbox event per booking, preference, event kind and class start. Re-running Beat must not send duplicates.
- Atomic database row locking claims an event before calling Meta. Pending items are skipped if payment/consent/class status/time no longer qualifies.
- A provider message ID means 'accepted by Meta', not 'delivered'. Signed webhook statuses are stored separately as sent/delivered/read/failed. Duplicate/out-of-order receipts cannot overwrite read with an earlier status.
- Only explicit HTTP 429 rejections are automatically retried (maximum three attempts, exponential 60/120 second backoff); every retry rechecks opt-in and class eligibility.
- Network timeouts, missing response IDs, HTTP 5xx and crashed senders are uncertain because Meta might have accepted the request. Mark UNKNOWN for manual review, never blindly retry.
- Enable only one Celery Beat scheduler, with a working notifications Celery queue and Redis broker. Email processing remains independent.

## Staging configuration (all secrets must stay out of Git)

- WHATSAPP_NOTIFICATIONS_ENABLED=false
- WHATSAPP_GRAPH_API_VERSION=<currently supported vXX.X>
- WHATSAPP_PHONE_NUMBER_ID=<Meta phone number id>
- WHATSAPP_CLOUD_TOKEN=<rotated secure access token>
- WHATSAPP_APP_SECRET=<Meta app secret, for webhook HMAC>
- WHATSAPP_WEBHOOK_VERIFY_TOKEN=<random webhook verification token>
- WHATSAPP_TEMPLATE_LANGUAGE=en
- WHATSAPP_CONFIRMATION_TEMPLATE=amaris_booking_confirmation
- WHATSAPP_REMINDER_TEMPLATE=amaris_class_reminder

Both Meta templates must be approved as Utility templates before staging use. Each template receives exactly four ordered body parameters:
(1) booking reference, (2) topic, (3) start time in SAST, (4) tutor name.

Suggested confirmation: Amaris Mathematics Academy. Your online lesson booking is confirmed. Booking reference: {{1}}. Topic: {{2}}. Date and time: {{3}}. Tutor: {{4}}. Please open your Amaris dashboard for the Zoom meeting details.

Suggested reminder: Amaris Mathematics Academy. Reminder: Your booked online lesson starts soon. Booking reference: {{1}}. Topic: {{2}}. Date and time: {{3}}. Tutor: {{4}}. Please open your Amaris dashboard to join your Zoom lesson.

The signed webhook endpoint is the deployed Django route /api/v1/whatsapp/webhook/ when the application's API prefix is /api/v1/. Verify the actual route prefix before registering it with Meta. Subscribe to WhatsApp messages events.

## Release gates still open

1. Run makemigrations --check --dry-run, migrate and migration graph checks against an isolated staging database. Reconcile branch migration 0015 before merging.
2. Run Django Black/Ruff, backend tests, frontend typecheck/lint, and GitHub Actions CI.
3. Confirm staging Redis, notifications worker and single Beat scheduler are healthy; previously reported HTTP 503 and staging service issues must be rechecked.
4. Confirm Meta has approved BOTH templates, rotated/stored credentials, and account WhatsApp opt-in/legal/compliance requirements.
5. Complete a new sandbox PayFast booking and confirm student WhatsApp confirmation, 30-minute reminder, signature-verified delivered/read callbacks, and no duplicate messages.
6. Verify no sends for unpaid, cancelled, past, unconsented and opted-out bookings. Test STOP, invalid signatures, 429, timeout uncertainty, and repeated callbacks.
7. Confirm continued student/tutor/admin booking emails and unchanged professional invoice attachments, costs and rollback.
8. DO NOT deploy to production or enable sending until separate review and approval.

No live WhatsApp messages were sent by developing this branch.
