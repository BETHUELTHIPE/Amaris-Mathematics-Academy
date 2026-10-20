import copy
import io
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

import provision_approved as provision

MANIFEST = Path(__file__).with_name("pending-services.yaml")


class FakeRender:
    def __init__(self):
        self.services = {}
        self.created = []
        self.validated = 0
        self.missing_secret = False
        for name, (identifier, kind) in provision.SOURCES.items():
            self.services[identifier] = {
                "id": identifier,
                "name": name,
                "ownerId": provision.WORKSPACE,
                "type": kind,
                "suspended": "not_suspended",
                "slug": name,
                "serviceDetails": {"region": "frankfurt", "url": name + ":10000"},
            }

    def validate_blueprint(self, path):
        self.validated += 1

    def request(self, method, path, payload=None):
        if method == "GET":
            if path.startswith("/services?"):
                return [{"service": s} for s in self.services.values()]
            if "/env-vars/" in path:
                return {"value": "" if self.missing_secret else "private-test-secret"}
            if path == f"/key-value/{provision.BROKER_ID}":
                return {
                    "name": "amaris-production-broker",
                    "owner": {"id": provision.WORKSPACE},
                    "region": "frankfurt",
                }
            if path.endswith("/connection-info"):
                return {"internalConnectionString": "redis://private-test-broker:6379"}
            return self.services[path.split("/")[-1]]
        if method != "POST" or path != "/services":
            raise AssertionError("Unexpected mutation")
        self.created.append(copy.deepcopy(payload))
        service = copy.deepcopy(payload)
        service.update(
            {
                "id": f"srv-new-{len(self.created)}",
                "suspended": "not_suspended",
                "slug": service["name"] + "-actual",
            }
        )
        service["serviceDetails"]["url"] = service["slug"] + ":10000"
        self.services[service["id"]] = service
        return {"service": service, "deployId": f"dep-new-{len(self.created)}"}


class ProvisionApprovedTests(unittest.TestCase):
    def run_provision(self, api):
        with redirect_stdout(io.StringIO()) as output:
            report = provision.provision(api, MANIFEST)
        return report, output.getvalue()

    def test_exact_scope_disks_actual_address_and_no_secret_logging(self):
        api = FakeRender()
        report, logs = self.run_provision(api)
        self.assertEqual(api.validated, 1)
        self.assertEqual(len(report), 3)
        self.assertEqual(
            [x["type"] for x in api.created],
            ["private_service", "private_service", "background_worker"],
        )
        self.assertEqual(
            sum(
                x["serviceDetails"].get("disk", {}).get("sizeGB", 0)
                for x in api.created
            ),
            2,
        )
        grafana_env = {v["key"]: v["value"] for v in api.created[1]["envVars"]}
        self.assertEqual(
            grafana_env["PROMETHEUS_HOSTPORT"],
            "amaris-monitoring-prometheus-actual:10000",
        )
        for payload in api.created:
            self.assertEqual(payload["autoDeployTrigger"], "off")
            self.assertEqual(payload["serviceDetails"]["plan"], "0.5c-512mb")
            for item in payload["envVars"]:
                if item["key"] in {
                    "DJANGO_SECRET_KEY",
                    "DATABASE_URL",
                    "CELERY_BROKER_URL",
                    "GF_SECURITY_ADMIN_PASSWORD",
                }:
                    self.assertNotIn(item["value"], logs)
        self.assertIn(
            "--queues=monitoring-verification",
            api.created[2]["serviceDetails"]["envSpecificDetails"]["dockerCommand"],
        )

    def test_retry_retains_existing_services_and_does_not_rotate_password(self):
        api = FakeRender()
        self.run_provision(api)
        report, _ = self.run_provision(api)
        self.assertEqual(len(api.created), 3)
        self.assertTrue(all(row["action"] == "retained" for row in report))

    def test_public_name_collision_blocks_every_create(self):
        api = FakeRender()
        api.services["srv-collision"] = {
            **next(iter(api.services.values())),
            "name": "amaris-monitoring-grafana",
            "type": "web_service",
        }
        with self.assertRaises(ValueError):
            self.run_provision(api)
        self.assertEqual(api.created, [])

    def test_wrong_workspace_dependency_blocks_every_create(self):
        api = FakeRender()
        next(iter(api.services.values()))["ownerId"] = "tea-wrong"
        with self.assertRaises(ValueError):
            self.run_provision(api)
        self.assertEqual(api.created, [])

    def test_missing_secret_blocks_every_create(self):
        api = FakeRender()
        api.missing_secret = True
        with self.assertRaises(ValueError):
            self.run_provision(api)
        self.assertEqual(api.created, [])

    def test_changed_budget_or_queue_requires_review(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "render.yaml"
            path.write_bytes(
                MANIFEST.read_bytes().replace(
                    b"monitoring-verification", b"critical,default"
                )
            )
            with self.assertRaisesRegex(ValueError, "Blueprint changed"):
                provision.approved_manifest(path)

    def test_api_refuses_unrelated_mutations(self):
        client = provision.RenderAPI("synthetic-test-token")
        for method, path in [
            ("PATCH", "/services/existing"),
            ("POST", "/redis"),
            ("DELETE", "/services/existing"),
        ]:
            with self.assertRaisesRegex(ValueError, "Mutation outside"):
                client.request(method, path)

    def test_existing_service_upgrade_is_rejected_without_more_creation(self):
        api = FakeRender()
        self.run_provision(api)
        api.services["srv-new-1"]["serviceDetails"]["plan"] = "standard"
        with self.assertRaisesRegex(ValueError, "refusing replacement"):
            self.run_provision(api)
        self.assertEqual(len(api.created), 3)


if __name__ == "__main__":
    unittest.main()
