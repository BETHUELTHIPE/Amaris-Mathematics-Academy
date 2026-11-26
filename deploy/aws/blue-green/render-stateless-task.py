"""Render a stateless ARM64 web task from the existing staging service definition.

Input is DescribeTaskDefinition.taskDefinition JSON, not environment secrets.
Application images must be immutable staging ECR digests. The proxy can reuse
the current pinned Nginx image with the configuration embedded in the task.
ECS reads Redis connection strings from dedicated SecureString SSM parameters.
This script never registers or deploys a task.
"""
import argparse
import json
import re
import sys
from pathlib import Path

REPO = "110156539003.dkr.ecr.eu-north-1.amazonaws.com/amaris-staging-frontend"
SSM = "arn:aws:ssm:eu-north-1:110156539003:parameter/amaris/aws-staging/shared-valkey/"
URLS = {
    "DJANGO_CACHE_URL": "cache",
    "DJANGO_PUBLIC_CACHE_URL": "public-cache",
    "CELERY_BROKER_URL": "broker",
    "CELERY_RESULT_BACKEND": "result",
}


def image(value):
    if not isinstance(value, str) or not re.fullmatch(re.escape(REPO) + r"@sha256:[0-9a-f]{64}", value):
        raise argparse.ArgumentTypeError("Use an immutable digest in the staging ECR repository")
    return value


def configure_proxy(container, proxy):
    if proxy is not None:
        container["image"] = image(proxy)
        return

    current = container.get("image", "")
    if not re.fullmatch(r"(?:(?:docker\.io/)?library/)?nginx@sha256:[0-9a-f]{64}", current):
        raise ValueError("Expected the current immutable official Nginx image")
    if container.get("entryPoint") or container.get("command") or container.get("readonlyRootFilesystem"):
        raise ValueError("Unexpected proxy start configuration")
    configs = Path(__file__).with_name("proxy")
    commands = []
    for source, destination in (("cms.conf", "default.conf"), ("backend.inc", "backend.inc")):
        body = (configs / source).read_text(encoding="utf-8").rstrip("\n")
        if "AMARIS_NGINX_CONFIG" in body.splitlines():
            raise ValueError("Proxy config contains the shell delimiter")
        commands.append(f"cat > /etc/nginx/conf.d/{destination} <<'AMARIS_NGINX_CONFIG'\n{body}\nAMARIS_NGINX_CONFIG")
    commands.append("exec /docker-entrypoint.sh nginx -g 'daemon off;'")
    container["entryPoint"] = ["/bin/sh", "-ec"]
    container["command"] = ["\n".join(commands)]


def render(task, backend, frontend, proxy):
    if task.get("family") != "amaris-ecs-staging-alb-web" or task.get("networkMode") != "awsvpc":
        raise ValueError("Expected existing staging ALB task family and awsvpc")
    if task.get("runtimePlatform", {}).get("cpuArchitecture") != "ARM64":
        raise ValueError("Expected ARM64")
    names = {c["name"]: c for c in task["containerDefinitions"]}
    if set(names) != {"backend", "frontend", "cms", "valkey"}:
        raise ValueError("Unexpected existing containers; manual review required")
    if {v["name"] for v in task["volumes"]} != {"valkey-data", "cms-proxy", "proxy-headers"}:
        raise ValueError("Unexpected existing volumes; manual review required")
    for name, digest in (("backend", backend), ("frontend", frontend)):
        names[name]["image"] = image(digest)
    configure_proxy(names["cms"], proxy)
    del names["valkey"]
    b = names["backend"]
    # The old wrapper explicitly overwrote SSM settings with localhost URLs.
    entry = b["entryPoint"][2]
    for i, (key, suffix) in enumerate(URLS.items()):
        old = f"export {key}=redis://127.0.0.1:6379/{i}"
        if entry.count(old) != 1:
            raise ValueError(f"Unexpected local Redis configuration for {key}")
        alias = f"AMARIS_SHARED_{key}"
        entry = entry.replace(old, f'export {key}="\x24{{{alias}:?Missing shared Valkey URL}}"')
        b.setdefault("secrets", []).append({"name": alias, "valueFrom": SSM + suffix})
    b["entryPoint"][2] = entry
    b["dependsOn"] = [d for d in b.get("dependsOn", []) if d["containerName"] != "valkey"]
    if not b["dependsOn"]:
        b.pop("dependsOn")
    names["cms"].pop("mountPoints", None)
    for c in names.values():
        if c.get("mountPoints") or c.get("volumesFrom") or c.get("links"):
            raise ValueError("Remaining local state or legacy links")
    allowed = {
        "family", "networkMode", "requiresCompatibilities", "runtimePlatform",
        "executionRoleArn", "taskRoleArn", "cpu", "memory", "ephemeralStorage",
        "pidMode", "ipcMode", "proxyConfiguration", "placementConstraints",
    }
    result = {k: v for k, v in task.items() if k in allowed and v is not None}
    result["containerDefinitions"] = list(names.values())
    result["volumes"] = []
    return result


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--backend", type=image)
    p.add_argument("--frontend", type=image)
    proxy_mode = p.add_mutually_exclusive_group(required=True)
    proxy_mode.add_argument("--proxy", type=image)
    proxy_mode.add_argument("--reuse-current-proxy", action="store_true")
    a = p.parse_args()
    if bool(a.backend) != bool(a.frontend) or (a.proxy and not a.backend):
        p.error("Supply the backend and frontend digests together, or reuse the running release")
    task = json.load(sys.stdin)
    current = {c["name"]: c.get("image") for c in task["containerDefinitions"]}
    try:
        result = render(task, a.backend or current.get("backend"), a.frontend or current.get("frontend"), a.proxy)
    except (ValueError, argparse.ArgumentTypeError) as error:
        p.error(str(error))
    json.dump(result, sys.stdout, indent=2)
    print()


if __name__ == "__main__":
    main()
