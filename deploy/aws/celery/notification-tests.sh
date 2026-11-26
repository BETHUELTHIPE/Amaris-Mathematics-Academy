#!/usr/bin/env bash
set -euo pipefail
for attempt in {1..20}; do
  backend="$(docker ps -q --filter label=com.amazonaws.ecs.task-definition-family=amaris-ecs-staging-alb-web --filter label=com.amazonaws.ecs.container-name=backend --filter health=healthy)"
  if [[ "$backend" =~ ^[a-f0-9]{12,64}$ ]]; then break; fi
  sleep 4
done
[[ "$backend" =~ ^[a-f0-9]{12,64}$ ]]
image="$(docker inspect --format '{{.Image}}' "$backend")"
[[ "$image" =~ ^sha256:[a-f0-9]{64}$ ]]
cd /tmp
docker run --rm --network none --memory=384m --cpus=0.75 --entrypoint python \
  -e DJANGO_DEBUG=true -e DATABASE_URL=sqlite:///:memory: -e SUPABASE_DATABASE_REQUIRED=false \
  -e EMAIL_BACKEND=django.core.mail.backends.locmem.EmailBackend "$image" manage.py test --noinput \
  content.test_live_classes.LiveClassBookingTests.test_synthetic_full_booking_payment_email_and_reminder_journey \
  content.test_live_classes.LiveClassBookingTests.test_reminder_is_sent_once_inside_thirty_minute_window \
  content.test_live_classes.LiveClassBookingTests.test_reminders_drain_multiple_bookings_in_one_schedule_tick \
  content.test_video_requests.VideoRequestWorkflowTests.test_notifications_attach_invoice_then_send_ready_message
