"""Add a staging-only broker probe and keep historical video notices paused."""

from django.conf import settings

from amaris_cms.celery import app

if settings.SUPABASE_PROJECT_REF != 'atyhhjwwxgzeurnwayay':
    raise RuntimeError('The AWS staging Celery settings require the staging Supabase project.')

app.conf.beat_schedule = {
    name: entry for name, entry in app.conf.beat_schedule.items() if name != 'deliver-video-request-notifications'
}


@app.task(name='amaris.staging.celery_probe', bind=True, ignore_result=False)
def probe(self):
    return {'status': 'ok', 'queue': self.request.delivery_info['routing_key']}
