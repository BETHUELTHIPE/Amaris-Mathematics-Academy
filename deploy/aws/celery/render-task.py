"""Reuse the deployed Amaris backend image and staging settings for Celery."""

import copy
import json
import sys

STAGING_FAMILY = 'amaris-ecs-staging-alb-web'
CELERY_VOLUME = 'staging-celery-config'


def celery_container(backend, name, reserve, limit, arguments):
    pid = f'/tmp/amaris-{name}.pid'
    return {
        'name': name,
        'image': backend['image'],
        'entryPoint': backend['entryPoint'],
        'secrets': backend['secrets'],
        'environment': backend.get('environment', []),
        'essential': False,
        'cpu': 64 if name == 'celery-worker' else 32,
        'memoryReservation': reserve,
        'memory': limit,
        'stopTimeout': 45,
        'restartPolicy': {'enabled': True, 'restartAttemptPeriod': 60},
        'dependsOn': [{'containerName': 'valkey', 'condition': 'HEALTHY'}],
        'logConfiguration': backend['logConfiguration'],
        'mountPoints': [
            {'sourceVolume': CELERY_VOLUME, 'containerPath': '/app/staging_celery.py', 'readOnly': True}
        ],
        'command': ['python', '-m', 'celery', '-A', 'staging_celery:app', *arguments, f'--pidfile={pid}'],
        'healthCheck': {
            'command': ['CMD-SHELL', f'test -s {pid} && kill -0 "$(cat {pid})"'],
            'interval': 20,
            'timeout': 5,
            'retries': 3,
            'startPeriod': 45,
        },
    }


def main():
    original = json.load(sys.stdin)
    if original.get('family') != STAGING_FAMILY or original.get('networkMode') != 'awsvpc':
        raise SystemExit('The live private Amaris staging task is required.')
    writable = (
        'family', 'taskRoleArn', 'executionRoleArn', 'networkMode', 'containerDefinitions', 'volumes',
        'placementConstraints', 'requiresCompatibilities', 'cpu', 'memory', 'pidMode', 'ipcMode',
        'proxyConfiguration', 'inferenceAccelerators', 'ephemeralStorage', 'runtimePlatform',
        'enableFaultInjection',
    )
    task = {name: copy.deepcopy(original[name]) for name in writable if name in original}
    containers = {container['name']: container for container in task['containerDefinitions']}
    if set(containers) != {'backend', 'frontend', 'cms', 'valkey'}:
        raise SystemExit('The live task does not match the expected one-task staging setup.')
    backend = containers['backend']
    if not any(entry['name'] == 'AMARIS_RUNTIME_ENV' for entry in backend['secrets']):
        raise SystemExit('The staging task must use the existing encrypted configuration.')
    if 'redis://127.0.0.1:6379/2' not in ' '.join(backend['entryPoint']):
        raise SystemExit('The task does not use the expected local staging broker.')
    task['volumes'].append({
        'name': CELERY_VOLUME, 'host': {'sourcePath': '/opt/amaris-staging/celery/staging_celery.py'},
    })
    worker = celery_container(backend, 'celery-worker', 192, 416, [
        'worker', '--queues=notifications,critical,default', '--loglevel=INFO', '--concurrency=1',
        '--prefetch-multiplier=1', '--max-tasks-per-child=100', '--max-memory-per-child=220000',
        '--hostname=amaris-staging-worker@%h',
    ])
    beat = celery_container(backend, 'celery-beat', 96, 220, [
        'beat', '--loglevel=INFO', '--max-interval=10', '--schedule=/tmp/amaris-aws-staging-beat',
    ])
    beat['dependsOn'].append({'containerName': 'celery-worker', 'condition': 'HEALTHY'})
    task['containerDefinitions'].extend([worker, beat])
    json.dump(task, sys.stdout, indent=2)
    print()


if __name__ == '__main__':
    main()
