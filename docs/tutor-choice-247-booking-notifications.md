# Live tutoring: choose any available tutor, 24/7

## Student booking journey

- The booking form offers a preferred-tutor selector populated from published, unreserved sessions for the chosen programme and grade. "Any available tutor" sorts by the next available time.
- The student may request a morning (05:00–11:59), afternoon (12:00–16:59), evening (17:00–21:59) or overnight (22:00–04:59) start in Africa/Johannesburg time. The calendar is searchable at any time of day.
- **24/7 booking does not mean every tutor guarantees every hour.** Tutor slots must be explicitly published, active and unreserved; pending payment holds expire under the existing worker. An unavailable tutor cannot be booked.
- The hourly price remains server-controlled at R250, and private Zoom URLs do not appear in the public listing.
- The existing PayFast provider-verification and idempotent checkout remain authoritative. No tutor/admin confirmation is emitted before a verified and confirmed paid booking.

## Three independent confirmation emails

After a verified PayFast payment, the notification worker sends:

1. Student: class and tutor details, secure Zoom link, invoice number and attached PDF.
2. Selected tutor: student name, email and optional phone; programme, subject, level, topic, start/end times in SAST, duration, amount paid, invoice, booking reference and Zoom details.
3. Django admin: the same operational details and a missing-tutor-email alert if needed. The message is sent via **BCC** to active Django superusers, the configured SiteSettings contact email and any addresses in `BOOKING_ADMIN_NOTIFICATION_EMAILS`. Duplicate addresses are removed.

Existing bookings are marked `staff_notification_required=False` during migration 0011, so past classes never trigger misleading new-booking notifications. New ORM-created bookings default to `True`. The new `confirmation_sent_at`, `tutor_confirmation_sent_at`, and `admin_confirmation_sent_at` markers are visible (read-only) in Django Admin. Each is written only after its own email backend accepts the message. They protect the student from receiving duplicate invoices when a tutor/admin message fails.

Mail submission is not proof of recipient inbox delivery. SMTP delivery and destination inbox receipt must be checked separately in staging. The student reminder remains scheduled 30 minutes before the session.

## Release and acceptance

1. Back up and verify restore capability for **the correct staging database** and apply `content.0011_liveclass_recipient_notifications` there. Confirm there is no conflicting migration on the deployed production backend branch; migrate production only after a real backup and isolated restore check.
2. Configure functioning transactional SMTP on the **notification worker** and `BOOKING_ADMIN_NOTIFICATION_EMAILS` if an additional shared inbox is required; confirm active Django superusers have verified, monitored addresses.
3. Verify worker and Celery Beat schedule for `deliver_live_class_confirmation` and `deliver_live_class_reminder`.
4. Run `python manage.py test content.test_live_classes`, Django migration checks, frontend TypeScript, unit tests and 320/834/1440 browser checks for CAPS/IEB Grades 7–12, TVET and University selections.
5. Seed two approved tutors with separate overlapping programme slots, including a 23:30 SAST slot; check named-tutor filtering, "any tutor" sorting, no-schedule messaging, and selection resets.
6. Execute **one isolated PayFast sandbox checkout** with synthetic data, let PayFast send an actual provider-verified notification, then verify separate student/tutor/admin emails and matching invoice PDF inside each intended inbox. Confirm duplicates and a simulated SMTP failure do not cause repeat invoice emails. Do not use live funds.
7. Confirm student owns invoice download, nonstudents cannot see private Zoom links, no other student can see the booking, and 30-minute reminder is sent only once.
8. Promote backend (after migration and worker readiness) then frontend. Confirm Render versions, smoke checks, mail queues and rollback reference. Do not promote if staging email acceptance or backup/restore evidence is absent.
