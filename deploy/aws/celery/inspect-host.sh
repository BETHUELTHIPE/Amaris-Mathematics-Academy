#!/usr/bin/env bash
set -euo pipefail
id="$(docker ps -q --filter label=com.amazonaws.ecs.task-definition-family=amaris-ecs-staging-alb-web --filter label=com.amazonaws.ecs.container-name=backend)"
[[ "$id" =~ ^[a-f0-9]{12,64}$ ]]
free -m
docker exec -i "$id" python - <<'PY'
import os
import sys
from collections import Counter
from datetime import timedelta

for line in os.environ['AMARIS_RUNTIME_ENV'].splitlines():
    name, _, value = line.partition('=')
    os.environ[name] = value
os.environ.update(CELERY_BROKER_URL='redis://127.0.0.1:6379/2', CELERY_RESULT_BACKEND='redis://127.0.0.1:6379/3')
try:
    import django
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'amaris_cms.settings')
    django.setup()
    from amaris_cms.celery import app
    from content import models, tasks
    from content.tutor_finance_models import TutorPayout
    from django.conf import settings
    from django.core.mail import get_connection
    from django.db import connection, transaction
    from django.db.models import Q
    from django.utils import timezone
    from redis import Redis

    assert settings.SUPABASE_PROJECT_REF == 'atyhhjwwxgzeurnwayay'
    redis = Redis.from_url(settings.CELERY_BROKER_URL, socket_timeout=4)
    assert redis.ping()
    print('Broker available. Existing queue depths:', {q:redis.llen(q) for q in ('default','critical','notifications')}, flush=True)
    print('Running Celery worker replies:', len(app.control.ping(timeout=2)), flush=True)
    print('Scheduled application jobs:', len(settings.CELERY_BEAT_SCHEDULE), flush=True)
    with transaction.atomic():
        with connection.cursor() as cur:
            cur.execute('SET TRANSACTION READ ONLY')
        counts = {}
        counts['payment_emails'] = tasks.NotificationOutbox.objects.filter(status='queued').count()
        counts['class_confirmations'] = tasks._pending_live_class_confirmations().count()
        now = timezone.now()
        counts['class_reminders'] = models.LiveClassBooking.objects.filter(status='confirmed', confirmation_sent_at__isnull=False, reminder_sent_at__isnull=True, slot__starts_at__gt=now, slot__starts_at__lte=now+timedelta(minutes=30)).count()
        counts['video_notices'] = models.VideoRequest.objects.filter(Q(status='queued', confirmation_sent_at__isnull=True) | Q(status='queued', position_one_sent_at__isnull=True) | Q(status='recording', recording_sent_at__isnull=True) | Q(status='ready', ready_notification_sent_at__isnull=True)).count()
        counts['payout_receipts'] = TutorPayout.objects.filter(state='paid',confirmed_at__isnull=False,receipt_emailed_at__isnull=True).exclude(provider_reference='').count()
        print('Pending notices by type:', counts, flush=True)
    if settings.EMAIL_BACKEND == 'django.core.mail.backends.smtp.EmailBackend':
        with get_connection(timeout=8):
            print('SMTP connected and authenticated; no message sent.', flush=True)
    else:
        print('SMTP is not configured on the live staging task.', flush=True)
except Exception as error:
    print('Preflight stopped:', type(error).__name__, flush=True)
    sys.exit(1)
PY
