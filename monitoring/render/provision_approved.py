"""Provision only the three resources approved in PR #303, via Render's API."""

import argparse
import hashlib
import json
import os
import re
import secrets
import urllib.error
import urllib.parse
import urllib.request
from decimal import Decimal
from pathlib import Path

import yaml

WORKSPACE = "tea-csppi8l6l47c73dk9c90"
REPO = "https://github.com/BETHUELTHIPE/Amaris-Mathematics-Academy"
MANIFEST_HASH = "a4bf72cc14cae4cf2b88f1b29098cbe44a7e0e4615a9fe478203b2567a48b139"
NAMES = {
    "amaris-monitoring-prometheus": "pserv",
    "amaris-monitoring-grafana": "pserv",
    "amaris-production-monitor-worker": "worker",
}
TYPES = {
    "pserv": "private_service",
    "worker": "background_worker",
    "web": "web_service",
}
SOURCES = {
    "amaris-production-web": ("srv-dapn6b3tqb8s73d3r7n0", "web_service"),
    "amaris-monitoring-flower": ("srv-db7v5l8n74is73eag9ig", "private_service"),
    "amaris-monitoring-render-metrics": ("srv-db7v5l8n74is73eag9j0", "private_service"),
}
BROKER_ID = "red-dapaglkja7ms73ajrkq0"


def approved_manifest(path):
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != MANIFEST_HASH:
        raise ValueError("Blueprint changed from approved PR #303; review required")
    services = yaml.safe_load(raw)["services"]
    if {s["name"]: s["type"] for s in services} != NAMES or len(services) != 3:
        raise ValueError("Only the three approved services are allowed")
    disks = [s["disk"] for s in services if "disk" in s]
    for service in services:
        if any(
            service.get(key) != value
            for key, value in {
                "repo": REPO,
                "runtime": "docker",
                "region": "frankfurt",
                "plan": "0.5c-512mb",
                "autoDeployTrigger": "off",
            }.items()
        ):
            raise ValueError("Unapproved service configuration")
    if len(disks) != 2 or any(disk["sizeGB"] != 1 for disk in disks):
        raise ValueError("Only two one-GB disks are allowed")
    if Decimal(7) * len(services) + Decimal("0.25") * len(disks) != Decimal("21.50"):
        raise ValueError("Approved base-cost estimate exceeded")
    return services


class RenderAPI:
    def __init__(self, token):
        if not token:
            raise ValueError("Protected RENDER_API_KEY is unavailable")
        self.token = token

    def request(self, method, path, payload=None, content_type="application/json"):
        if method not in {"GET", "POST"} or (
            method == "POST" and path not in {"/services", "/blueprints/validate"}
        ):
            raise ValueError("Mutation outside approved provisioning scope")
        data = payload
        if payload is not None and not isinstance(payload, bytes):
            data = json.dumps(payload).encode()
        request = urllib.request.Request(
            "https://api.render.com/v1" + path,
            method=method,
            data=data,
            headers={
                "Authorization": "Bearer " + self.token,
                "Accept": "application/json",
                "Content-Type": content_type,
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=45) as response:
                return json.load(response)
        except urllib.error.HTTPError as exc:
            # Never log response bodies: provider errors can echo secret inputs.
            raise RuntimeError(f"Render {method} {path}: HTTP {exc.code}") from None
        except (OSError, ValueError):
            raise RuntimeError(f"Render {method} {path}: request failed") from None

    def validate_blueprint(self, path):
        boundary = "amaris-" + secrets.token_hex(12)
        body = (
            (
                f'--{boundary}\r\nContent-Disposition: form-data; name="ownerId"\r\n\r\n'
                f"{WORKSPACE}\r\n--{boundary}\r\n"
                'Content-Disposition: form-data; name="file"; filename="render.yaml"\r\n'
                "Content-Type: application/yaml\r\n\r\n"
            ).encode()
            + path.read_bytes()
            + f"\r\n--{boundary}--\r\n".encode()
        )
        result = self.request(
            "POST",
            "/blueprints/validate",
            body,
            f"multipart/form-data; boundary={boundary}",
        )
        if result.get("valid") is not True:
            paths = [str(e.get("path", "unknown")) for e in result.get("errors", [])]
            raise ValueError(
                "Render Blueprint validation failed at " + ", ".join(paths)
            )
        plan = result.get("plan", {})
        if set(plan.get("services", [])) != set(NAMES) or any(
            plan.get(key) for key in ("databases", "keyValue", "envGroups", "workflows")
        ):
            raise ValueError("Render plan differs from the three approved additions")


def check_source(service, name, kind):
    details = service.get("serviceDetails", {})
    if (
        service.get("ownerId") != WORKSPACE
        or service.get("name") != name
        or service.get("type") != kind
        or details.get("region") != "frankfurt"
        or service.get("suspended") != "not_suspended"
    ):
        raise ValueError(f"Unexpected workspace, type, region or state for {name}")


def check_existing(service, definition):
    check_source(service, definition["name"], TYPES[definition["type"]])
    details = service["serviceDetails"]
    docker = details.get("envSpecificDetails", {})
    disk = details.get("disk") or {}
    expected_disk = definition.get("disk", {})
    if (
        service.get("repo", "").removesuffix(".git") != REPO
        or service.get("branch") != definition["branch"]
        or service.get("autoDeployTrigger") != "off"
        or details.get("runtime") != "docker"
        or details.get("plan") not in {"starter", "0.5c-512mb"}
        or details.get("numInstances") != 1
        or any(
            docker.get(k, "") != definition.get(k, "")
            for k in ("dockerContext", "dockerfilePath", "dockerCommand")
        )
        or any(
            disk.get(k) != expected_disk.get(k) for k in ("name", "mountPath", "sizeGB")
        )
    ):
        raise ValueError(
            f"Existing {definition['name']} differs; refusing replacement or mutation"
        )


def hostport(service):
    if service["type"] == "private_service":
        address = service["serviceDetails"]["url"]
    else:
        address = service["slug"] + ":10000"
    if not re.fullmatch(r"[a-z0-9-]+:[0-9]+", address):
        raise ValueError("Unexpected private hostport")
    return address


def service_payload(definition, values):
    details = {
        "runtime": "docker",
        "plan": definition["plan"],
        "region": "frankfurt",
        "numInstances": 1,
        "envSpecificDetails": {
            k: definition[k]
            for k in ("dockerfilePath", "dockerContext", "dockerCommand")
            if k in definition
        },
    }
    for key in ("disk", "maxShutdownDelaySeconds"):
        if key in definition:
            details[key] = definition[key]
    return {
        "type": TYPES[definition["type"]],
        "name": definition["name"],
        "ownerId": WORKSPACE,
        "repo": REPO,
        "branch": definition["branch"],
        "autoDeployTrigger": "off",
        "serviceDetails": details,
        "envVars": [{"key": key, "value": value} for key, value in values.items()],
    }


def provision(api, path):
    definitions = approved_manifest(path)
    services = {}
    # Validate every dependency and every existing-name collision before creating anything.
    for name, (identifier, kind) in SOURCES.items():
        service = api.request("GET", f"/services/{identifier}")
        check_source(service, name, kind)
        services[name] = service
    existing = {}
    cursor = ""
    while True:
        query = urllib.parse.urlencode(
            {"ownerId": WORKSPACE, "limit": 100, "cursor": cursor}
        )
        rows = api.request("GET", "/services?" + query)
        for row in rows:
            service = row["service"]
            if service["name"] in NAMES:
                if service["name"] in existing:
                    raise ValueError("Duplicate service name")
                existing[service["name"]] = service
        if len(rows) < 100:
            break
        next_cursor = rows[-1].get("cursor")
        if not next_cursor or next_cursor == cursor:
            raise ValueError("Unable to enumerate all service-name collisions")
        cursor = next_cursor
    for definition in definitions:
        if definition["name"] in existing:
            check_existing(existing[definition["name"]], definition)
            services[definition["name"]] = existing[definition["name"]]

    # These credentials stay inside the protected runner and Render. Never print them.
    copied = {}
    for key in ("DJANGO_SECRET_KEY", "DATABASE_URL"):
        value = api.request(
            "GET", f"/services/{SOURCES['amaris-production-web'][0]}/env-vars/{key}"
        ).get("value")
        if not isinstance(value, str) or not value:
            raise ValueError(f"Required backend variable {key} is unavailable")
        copied[key] = value
    broker = api.request("GET", f"/key-value/{BROKER_ID}")
    if (
        broker.get("name") != "amaris-production-broker"
        or broker.get("owner", {}).get("id") != WORKSPACE
        or broker.get("region") != "frankfurt"
    ):
        raise ValueError("Unexpected production broker identity")
    broker_url = api.request("GET", f"/key-value/{BROKER_ID}/connection-info").get(
        "internalConnectionString"
    )
    if not isinstance(broker_url, str) or not broker_url.startswith(
        ("redis://", "rediss://")
    ):
        raise ValueError("Private broker connection unavailable")
    if not existing:
        api.validate_blueprint(path)
    report = []
    for definition in definitions:
        name = definition["name"]
        if name in existing:
            report.append(
                {"name": name, "serviceId": existing[name]["id"], "action": "retained"}
            )
            continue
        values = {}
        for var in definition["envVars"]:
            if "value" in var:
                value = var["value"]
            elif var.get("generateValue"):
                value = secrets.token_urlsafe(48)
            else:
                source = var["fromService"]
                if "envVarKey" in source:
                    value = copied[source["envVarKey"]]
                elif source["type"] == "keyvalue":
                    value = broker_url
                else:
                    value = hostport(services[source["name"]])
            values[var["key"]] = value
        created = api.request("POST", "/services", service_payload(definition, values))
        service = created["service"]
        check_existing(service, definition)
        services[name] = service
        entry = {
            "name": name,
            "serviceId": service["id"],
            "deployId": created.get("deployId"),
            "action": "created",
        }
        report.append(entry)
        print(json.dumps(entry), flush=True)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    path = Path(__file__).with_name("pending-services.yaml")
    definitions = approved_manifest(path)
    print(
        "Approved scope: three Docker services, two one-GB disks, USD 21.50/month base estimate"
    )
    if not args.apply:
        print(
            json.dumps(
                [
                    {"name": s["name"], "type": s["type"], "plan": s["plan"]}
                    for s in definitions
                ]
            )
        )
        return
    report = provision(RenderAPI(os.environ.get("RENDER_API_KEY", "")), path)
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as output:
            output.write("## Approved monitoring provisioning\n\n")
            output.writelines(
                f"- {item['name']}: {item['serviceId']} ({item['action']})\n"
                for item in report
            )
            output.write(
                "\nCreation is not proof of a live deploy, fresh metrics or worker heartbeats.\n"
            )


if __name__ == "__main__":
    try:
        main()
    except (ValueError, RuntimeError) as error:
        raise SystemExit(str(error)) from None
