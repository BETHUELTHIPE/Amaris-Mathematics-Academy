"""Adapt the verified ECS staging task to use an ENI in a private subnet."""

import json
import sys

FAMILY = "amaris-ecs-staging-private-web"
ROOT = "/opt/amaris-staging/vpc"


def main():
    definition = json.load(sys.stdin)
    if definition.get("family") != "amaris-ecs-staging-web" or definition.get("networkMode") != "bridge":
        raise SystemExit("The verified ECS staging template is required.")
    definition.update(family=FAMILY, networkMode="awsvpc")
    volumes = {volume["name"]: volume for volume in definition["volumes"]}
    volumes["valkey-data"]["host"]["sourcePath"] = f"{ROOT}/valkey"
    volumes["cms-proxy"]["host"]["sourcePath"] = f"{ROOT}/cms.conf"
    containers = {container["name"]: container for container in definition["containerDefinitions"]}
    for container in containers.values():
        container.pop("links", None)
        for port in container.get("portMappings", []):
            port.pop("hostPort", None)
    redis = containers["valkey"]
    redis["command"].extend(["--bind", "127.0.0.1", "--protected-mode", "yes"])

    frontend = containers["frontend"]["entryPoint"]
    frontend[2] = frontend[2].replace('exec "$@"', 'export CMS_API_URL=http://127.0.0.1:8080/api/v1\nexec "$@"')

    backend = containers["backend"]["entryPoint"]
    backend[2] = backend[2].replace('exec "$@"', '''export DJANGO_CACHE_URL=redis://127.0.0.1:6379/0
export DJANGO_PUBLIC_CACHE_URL=redis://127.0.0.1:6379/1
export CELERY_BROKER_URL=redis://127.0.0.1:6379/2
export CELERY_RESULT_BACKEND=redis://127.0.0.1:6379/3
exec "$@"''')
    json.dump(definition, sys.stdout, indent=2)
    print()


if __name__ == "__main__":
    main()
