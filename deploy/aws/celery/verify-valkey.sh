#!/usr/bin/env bash
set -euo pipefail

private_ip="$1"
[[ "$private_ip" =~ ^10\.86\.0\.[0-9]+$ ]]
family=amaris-ecs-staging-alb-web
find_container() {
  docker ps -q --filter "label=com.amazonaws.ecs.task-definition-family=$family" \
    --filter "label=com.amazonaws.ecs.container-name=$1" --filter health=healthy
}
backend="$(find_container backend)"
worker="$(find_container celery-worker)"
broker="$(find_container valkey)"
for container in "$backend" "$worker" "$broker"; do
  [[ "$container" =~ ^[a-f0-9]{12,64}$ ]]
done
if timeout 4 bash -c 'exec 3<>"/dev/tcp/$1/6379"' _ "$private_ip" 2>/dev/null; then
  echo 'Valkey accepted a connection from outside the ECS task.' >&2
  exit 1
fi
echo 'Valkey port 6379 is inaccessible from the EC2 host at the task IPv4 address.'

docker exec -i "$backend" python - "$private_ip" <<'PY'
import hashlib
import http.client
import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path
from urllib.parse import urlsplit
from uuid import uuid4


def active_environment():
    for item in Path('/proc/1/environ').read_bytes().split(b'\0'):
        if item:
            key, _, value = item.decode().partition('=')
            os.environ[key] = value


def assert_loopback(url, db):
    parsed = urlsplit(url)
    assert (parsed.scheme, parsed.hostname, parsed.port, parsed.path) == ('redis', '127.0.0.1', 6379, f'/{db}')


def request_bootstrap(path):
    connection = http.client.HTTPConnection('127.0.0.1', 8000, timeout=12)
    try:
        connection.request('GET', path, headers={
            'Host': '16.171.164.5', 'X-Forwarded-Proto': 'https', 'Accept': 'application/json',
        })
        res = connection.getresponse()
        body = res.read(2_000_000)
        assert res.status == 200 and 'settings' in json.loads(body)
        return hashlib.sha256(body).digest(), res.headers['Expires']
    finally:
        connection.close()


def main():
    active_environment()
    import django
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'amaris_cms.settings')
    django.setup()
    from django.conf import settings
    from django.core.cache import caches
    from django.test import RequestFactory
    from django.utils.cache import _generate_cache_header_key, get_cache_key
    from redis import Redis

    assert settings.SUPABASE_PROJECT_REF == 'atyhhjwwxgzeurnwayay'
    aliases = {'default': 0, 'public_content': 1}
    for alias, db in aliases.items():
        assert_loopback(settings.CACHES[alias]['LOCATION'], db)
    assert_loopback(settings.CELERY_BROKER_URL, 2)
    assert_loopback(settings.CELERY_RESULT_BACKEND, 3)
    clients = [Redis(host='127.0.0.1', port=6379, db=db, socket_timeout=3) for db in range(4)]
    server = clients[2]
    assert all(client.ping() for client in clients)
    config = {name: server.config_get(name)[name] for name in ('bind', 'protected-mode', 'maxmemory-policy')}
    assert config['bind'] == '127.0.0.1' and config['protected-mode'] == 'yes'
    assert config['maxmemory-policy'] == 'noeviction'
    try:
        with socket.create_connection((sys.argv[1], 6379), timeout=3):
            raise AssertionError('Task interface must not accept Valkey connections.')
    except ConnectionRefusedError:
        pass
    print('Valkey listens on loopback only, with protected mode and no automatic eviction.', flush=True)
    memory = server.info('memory')
    disk = server.info('persistence')
    print(f"Valkey memory: {memory['used_memory']} of {memory['maxmemory']} bytes. Last RDB save: {disk['rdb_last_bgsave_status']}.", flush=True)
    assert disk['rdb_last_bgsave_status'] == 'ok'

    marker = f'aws-valkey-smoke-{uuid4().hex}'
    try:
        for alias, db in aliases.items():
            cache = caches[alias]
            value = {'status': 'ok', 'alias': alias}
            key = cache.make_key(marker)
            cache.set(marker, value, timeout=30)
            assert 0 < clients[db].ttl(key) <= 30, 'The wrapper may have used its in-process fallback.'
            assert all(not client.exists(key) for other, client in enumerate(clients) if db != other)
            subprocess.run([sys.executable, '-c', '''
import django,sys
django.setup()
from django.core.cache import caches
alias,key=sys.argv[1:]
assert caches[alias].get(key)=={'status':'ok','alias':alias}
''', alias, marker], check=True, timeout=12, capture_output=True)
            print(f'Django {alias} wrote a TTL key to DB {db} and a separate process read it.', flush=True)
    finally:
        for alias, db in aliases.items():
            clients[db].delete(caches[alias].make_key(marker))

    path = f'/api/v1/bootstrap/?amaris_cache_probe={marker}'
    request = RequestFactory().get(path, secure=True, HTTP_HOST='16.171.164.5', HTTP_ACCEPT='application/json')
    prefix = 'public-api-v1'
    cache = caches['public_content']
    header_key = _generate_cache_header_key(prefix, request)
    page_key = None
    try:
        assert not clients[1].exists(cache.make_key(header_key))
        first = request_bootstrap(path)
        page_key = get_cache_key(request, key_prefix=prefix, method='GET', cache=cache)
        assert page_key and 0 < clients[1].ttl(cache.make_key(page_key)) <= 60
        time.sleep(2)
        second = request_bootstrap(path)
        assert first[1] and first == second, 'The repeat response must reuse the original cache expiry.'
        assert not clients[0].exists(cache.make_key(page_key)) and not clients[2].exists(cache.make_key(page_key))
        print('Public /api/v1/bootstrap/ populated DB 1 and the repeat HTTP request used its existing cache entry.', flush=True)
    finally:
        if page_key:
            clients[1].delete(cache.make_key(page_key))
        clients[1].delete(cache.make_key(header_key))
        for client in clients:
            client.close()


try:
    main()
except Exception as error:
    message = str(error) if isinstance(error, AssertionError) else ''
    print(f'Django/Valkey verification failed: {type(error).__name__}. {message}', file=sys.stderr)
    sys.exit(1)
PY

docker exec -i "$worker" python - <<'PY'
import os
import sys
from pathlib import Path

try:
    for item in Path('/proc/1/environ').read_bytes().split(b'\0'):
        if item:
            key, _, value = item.decode().partition('=')
            os.environ[key] = value
    from staging_celery import app
    from redis import Redis

    assert app.conf.broker_url == 'redis://127.0.0.1:6379/2'
    assert app.conf.result_backend == 'redis://127.0.0.1:6379/3'
    clients = [Redis(db=db, socket_timeout=3) for db in range(4)]
    for queue in ('default', 'critical', 'notifications'):
        result = app.send_task('amaris.staging.celery_probe', queue=queue, expires=30)
        key = app.backend.get_key_for_task(result.id)
        try:
            assert result.get(timeout=20) == {'status': 'ok', 'queue': queue}
            assert 0 < clients[3].ttl(key) and all(not client.exists(key) for client in clients[:3])
            print(f'Celery {queue} completed a test job via broker DB 2 and stored the result in DB 3.', flush=True)
        finally:
            result.forget()
    for client in clients:
        client.close()
except Exception as error:
    print(f'Celery/Valkey verification failed: {type(error).__name__}.', file=sys.stderr)
    sys.exit(1)
PY
