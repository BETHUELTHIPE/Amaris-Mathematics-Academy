"""Generate the ECS task definition for the existing Amaris staging release."""

import argparse
import json
import re
import sys

ACCOUNT = "110156539003"
REGION = "eu-north-1"
REPO = f"{ACCOUNT}.dkr.ecr.{REGION}.amazonaws.com/amaris-staging-frontend"
FRONTEND = f"{REPO}@sha256:e7c552b73296ca721e15da94d1ff2e8fbd6a41244666b4f310960b4b304fb6a3"
BACKEND = f"{REPO}@sha256:7e39cc9ca036ea4e37fa07be0c912901570ddf602e0b5edcac4dfa96d3665217"
ROOT = "/opt/amaris-staging/ecs"
LOAD_SETTINGS = """\
while IFS= read -r setting; do
  if [ -n "$setting" ]; then
    export "$setting"
  fi
done <<AMARIS_SETTINGS
$AMARIS_RUNTIME_ENV
AMARIS_SETTINGS
unset AMARIS_RUNTIME_ENV
exec "$@"
"""


def image_ref(value, repos):
    repo, _, digest = value.partition("@")
    if repo not in repos or not re.fullmatch(r"sha256:[a-f0-9]{64}", digest):
        raise ValueError("Unexpected staging sidecar repository or digest.")
    return value


def container(name, image, reserved, limit, cpu):
    return {
        "name": name,
        "image": image,
        "essential": True,
        "cpu": cpu,
        "memoryReservation": reserved,
        "memory": limit,
        "logConfiguration": {
            "logDriver": "json-file",
            "options": {"max-size": "10m", "max-file": "2"},
        },
    }


def health(command, start=0):
    return {
        "command": ["CMD", *command],
        "interval": 20,
        "timeout": 7,
        "retries": 3,
        "startPeriod": start,
    }


def settings(name, command):
    return {
        "secrets": [{
            "name": "AMARIS_RUNTIME_ENV",
            "valueFrom": f"arn:aws:ssm:{REGION}:{ACCOUNT}:parameter/amaris/aws-staging/{name}",
        }],
        "entryPoint": ["/bin/sh", "-ec", LOAD_SETTINGS, "amaris-settings"],
        "command": command,
    }


def task(address, role, nginx, redis):
    valkey = {
        **container("valkey", redis, 100, 192, 64),
        "command": ["valkey-server", "--maxmemory", "128mb", "--maxmemory-policy", "noeviction", "--save", "60", "1"],
        "mountPoints": [{"sourceVolume": "valkey-data", "containerPath": "/data"}],
        "healthCheck": health(["valkey-cli", "ping"], 10),
    }
    backend = {
        **container("backend", BACKEND, 384, 640, 256),
        **settings("backend", ["/app/entrypoint.sh", "gunicorn", "amaris_cms.asgi:application", "--config", "/app/gunicorn.conf.py"]),
        "links": ["valkey:amaris-redis"],
        "dependsOn": [{"containerName": "valkey", "condition": "HEALTHY"}],
        "portMappings": [{"containerPort": 8000, "hostPort": 18000, "protocol": "tcp"}],
        "healthCheck": health([
            "python", "-c", "import http.client; conn=http.client.HTTPConnection('127.0.0.1',8000,timeout=5); "
            f"conn.request('GET','/health/ready/',headers={{'Host':'{address}','X-Forwarded-Proto':'https'}}); "
            "raise SystemExit(conn.getresponse().status != 200)",
        ], 90),
    }
    gateway = {
        **container("cms", nginx, 24, 64, 32),
        "links": ["backend:amaris-backend"],
        "dependsOn": [{"containerName": "backend", "condition": "HEALTHY"}],
        "mountPoints": [{"sourceVolume": "cms-proxy", "containerPath": "/etc/nginx/conf.d/default.conf", "readOnly": True}],
    }
    frontend = {
        **container("frontend", FRONTEND, 192, 400, 128),
        **settings("frontend", ["node", ".output/server/index.mjs"]),
        "links": ["cms:amaris-gateway"],
        "dependsOn": [{"containerName": "cms", "condition": "START"}],
        "portMappings": [{"containerPort": 3000, "hostPort": 13000, "protocol": "tcp"}],
        "healthCheck": health([
            "node", "-e", "fetch('http://127.0.0.1:3000/health/ready').then(r=>process.exit(r.ok?0:1)).catch(()=>process.exit(1))",
        ], 45),
    }
    return {
        "family": "amaris-ecs-staging-web",
        "networkMode": "bridge",
        "requiresCompatibilities": ["EC2"],
        "runtimePlatform": {"cpuArchitecture": "ARM64", "operatingSystemFamily": "LINUX"},
        "executionRoleArn": role,
        "containerDefinitions": [valkey, backend, gateway, frontend],
        "volumes": [
            {"name": "valkey-data", "host": {"sourcePath": f"{ROOT}/valkey"}},
            {"name": "cms-proxy", "host": {"sourcePath": f"{ROOT}/cms.conf"}},
        ],
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("address", choices=["16.171.164.5"])
    parser.add_argument("role")
    parser.add_argument("nginx")
    parser.add_argument("redis")
    args = parser.parse_args()
    if not re.fullmatch(rf"arn:aws:iam::{ACCOUNT}:role/[\w+=,.@/-]+", args.role):
        parser.error("The execution role must be in Amaris staging's AWS account.")
    try:
        nginx = image_ref(args.nginx, {"nginx", "library/nginx", "docker.io/library/nginx"})
        redis = image_ref(args.redis, {"valkey/valkey", "docker.io/valkey/valkey"})
    except ValueError as error:
        parser.error(str(error))
    json.dump(task(args.address, args.role, nginx, redis), sys.stdout, indent=2)
    print()


if __name__ == "__main__":
    main()
