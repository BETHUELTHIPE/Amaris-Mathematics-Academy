from django.conf import settings
from django.db import connection
from redis import Redis


def database_available() -> bool:
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            return cursor.fetchone() == (1,)
    except Exception:
        # Health checks expose the result only.
        return False


def broker_available() -> bool:
    try:
        with Redis.from_url(settings.CELERY_BROKER_URL, socket_connect_timeout=1.5, socket_timeout=1.5) as client:
            return bool(client.ping())
    except Exception:
        return False
