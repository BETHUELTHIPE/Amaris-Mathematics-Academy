import copy
import io
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

import provision as p


def configuration(environment):
    spec = p.ENVIRONMENTS[environment]
    project = spec["project"]
    return {
        "DJANGO_SECRET_KEY": "private-django-test-value",
        "DATABASE_URL": f"postgresql://postgres.{project}:private-db-test-value@aws-0-eu-west-1.pooler.supabase.com:5432/postgres",
        "DATABASE_SSL_REQUIRED": "true", "SUPABASE_PROJECT_REF": project,
        "SUPABASE_URL": f"https://{project}.supabase.co",
        "CELERY_BROKER_URL": f'redis://{spec["broker"]}:6379/0',
        "CELERY_RESULT_BACKEND": f'redis://{spec["broker"]}:6379/1',
        "SUPABASE_S3_ENDPOINT_URL": f"https://{project}.storage.supabase.co/storage/v1/s3",
        "SUPABASE_S3_ACCESS_KEY_ID": "private-storage-test-key",
        "SUPABASE_S3_SECRET_ACCESS_KEY": "private-storage-test-value",
        "SUPABASE_S3_ADMIN_BUCKET": "admin-private", "SUPABASE_S3_STUDENT_BUCKET": "student-private",
        "PAYFAST_MODE": "sandbox" if environment == "staging" else "live",
        "PAYFAST_MERCHANT_KEY": "must-never-copy-payment-key",
        "EMAIL_HOST": "smtp.example.test", "EMAIL_HOST_USER": "mail@example.test",
        "EMAIL_HOST_PASSWORD": "private-smtp-test-value", "DEFAULT_FROM_EMAIL": "mail@example.test",
        "RENDER_API_KEY": "must-never-copy-render-token", "OPENAI_API_KEY": "must-never-copy-openai-key",
    }


class FakeRender:
    def __init__(self, environment):
        self.environment = environment
        self.spec = p.ENVIRONMENTS[environment]
        self.values = configuration(environment)
        self.created = []
        self.services = {}
        self.vars = {}
        self.web = {
            "id": self.spec["web"], "name": self.spec["web_name"], "ownerId": p.WORKSPACE,
            "type": "web_service", "repo": p.REPO, "branch": self.spec["branch"],
            "suspended": "not_suspended", "serviceDetails": {"region": "frankfurt"},
        }
        self.services[self.web["id"]] = self.web
        self.vars[self.web["id"]] = self.values
        self.deploys = [{"deploy": {"status": "live", "commit": {"id": self.spec["sha"]}}}]
        self.broker = {
            "owner": {"id": p.WORKSPACE}, "name": f"amaris-{environment}-broker",
            "region": "frankfurt", "options": {"maxmemoryPolicy": "noeviction"},
        }

    def request(self, method, path, payload=None):
        if method == "POST":
            assert path == "/services"
            self.created.append(copy.deepcopy(payload))
            service = copy.deepcopy(payload)
            service.pop("envVars")
            service.update(id=f"srv-test-{len(self.created)}", suspended="not_suspended")
            self.services[service["id"]] = service
            self.vars[service["id"]] = {v["key"]: v["value"] for v in payload["envVars"]}
            return {"service": service, "deployId": "dep-test"}
        if path.startswith("/key-value/"):
            return self.broker
        if "/env-vars?" in path:
            return [{"envVar": {"key": k, "value": v}} for k, v in self.vars[path.split("/")[2]].items()]
        if "/deploys?" in path:
            return self.deploys
        if path.startswith("/services?"):
            return [{"service": s} for s in self.services.values()]
        return self.services[path.split("/")[-1]]


class ProvisionTests(unittest.TestCase):
    def run_apply(self, api):
        with redirect_stdout(io.StringIO()) as output:
            result = p.provision(api, api.environment, apply=True, approved_monthly_usd=21)
        return result, output.getvalue()

    def test_preflight_is_read_only_for_both_environments(self):
        for environment in p.ENVIRONMENTS:
            with self.subTest(environment=environment):
                api = FakeRender(environment)
                report = p.provision(api, environment)
                self.assertEqual(api.created, [])
                self.assertEqual(len(report), 3)
                self.assertTrue(all(r["action"] == "would-create" for r in report))

    def test_apply_uses_exact_sources_and_separate_queues_without_secret_logs(self):
        for environment in p.ENVIRONMENTS:
            with self.subTest(environment=environment):
                api = FakeRender(environment)
                result, logs = self.run_apply(api)
                self.assertEqual(len(result), 3)
                commands = [s["serviceDetails"]["envSpecificDetails"]["startCommand"] for s in api.created]
                self.assertIn("--queues=critical,default", commands[0])
                self.assertIn("--queues=notifications", commands[1])
                self.assertIn(" beat ", commands[2])
                self.assertEqual(sum(" beat " in c for c in commands), 1)
                for body in api.created:
                    env = {v["key"]: v["value"] for v in body["envVars"]}
                    self.assertEqual(env["CELERY_BROKER_URL"], api.values["CELERY_BROKER_URL"])
                    self.assertNotIn("PAYFAST_MERCHANT_KEY", env)
                    self.assertNotIn("RENDER_API_KEY", env)
                    self.assertNotIn("OPENAI_API_KEY", env)
                    for value in env.values():
                        if "private-" in value:
                            self.assertNotIn(value, logs)
                    details = body["serviceDetails"]
                    self.assertEqual(details["numInstances"], 1)
                    self.assertEqual(details["runtime"], "python")
                    self.assertEqual(details["plan"], p.PLAN)
                    self.assertIn(api.spec["sha"], details["envSpecificDetails"]["buildCommand"])
                    self.assertNotIn("migrate", details["envSpecificDetails"]["buildCommand"])
                notification_env = {v["key"]: v["value"] for v in api.created[1]["envVars"]}
                self.assertEqual(notification_env["EMAIL_BACKEND"], "django.core.mail.backends.smtp.EmailBackend")
                for index in (0, 2):
                    self.assertNotIn("EMAIL_HOST_PASSWORD", {v["key"] for v in api.created[index]["envVars"]})

    def test_retries_adopt_existing_without_extra_services(self):
        api = FakeRender("staging")
        self.run_apply(api)
        report, _ = self.run_apply(api)
        self.assertEqual(len(api.created), 3)
        self.assertTrue(all(r["action"] == "retained" for r in report))

    def test_partial_creation_retry_adopts_created_workers(self):
        api = FakeRender("staging")
        original = api.request

        def fail_second(method, path, payload=None):
            if method == "POST" and len(api.created) == 1:
                raise RuntimeError("simulated provider failure")
            return original(method, path, payload)

        with patch.object(api, "request", side_effect=fail_second):
            with self.assertRaises(RuntimeError), redirect_stdout(io.StringIO()):
                p.provision(api, "staging", True, 21)
        self.run_apply(api)
        self.assertEqual(len(api.created), 3)

    def test_approval_is_required_before_api_reads_or_creates(self):
        for amount in (None, 0, 7, 20, 42):
            with self.subTest(amount=amount):
                api = FakeRender("staging")
                with patch.object(api, "request") as request:
                    with self.assertRaises(ValueError):
                        p.provision(api, "staging", True, amount)
                    request.assert_not_called()

    def test_fail_closed_before_any_create(self):
        changes = {
            "wrong-workspace": lambda a: a.web.update(ownerId="other"),
            "wrong-branch": lambda a: a.web.update(branch="main"),
            "wrong-source": lambda a: a.deploys[0]["deploy"]["commit"].update(id="0" * 40),
            "deploy-in-progress": lambda a: a.deploys.append({"deploy": {"status": "build_in_progress"}}),
            "missing-smtp": lambda a: a.values.pop("EMAIL_HOST_PASSWORD"),
            "plain-smtp": lambda a: a.values.update(EMAIL_USE_TLS="false"),
            "tls-and-ssl": lambda a: a.values.update(EMAIL_USE_SSL="true"),
            "wrong-database": lambda a: a.values.update(DATABASE_URL=configuration("production")["DATABASE_URL"]),
            "wrong-storage": lambda a: a.values.update(SUPABASE_S3_ENDPOINT_URL=configuration("production")["SUPABASE_S3_ENDPOINT_URL"]),
            "production-queue": lambda a: a.values.update(CELERY_BROKER_URL=configuration("production")["CELERY_BROKER_URL"]),
            "production-results": lambda a: a.values.update(CELERY_RESULT_BACKEND=configuration("production")["CELERY_RESULT_BACKEND"]),
            "live-staging-payment": lambda a: a.values.update(PAYFAST_MODE="live"),
            "evicting-broker": lambda a: a.broker["options"].update(maxmemoryPolicy="allkeys-lru"),
            "database-no-ssl": lambda a: a.values.update(DATABASE_SSL_REQUIRED="false"),
        }
        for name, change in changes.items():
            with self.subTest(name=name):
                api = FakeRender("staging")
                change(api)
                with self.assertRaises(ValueError):
                    self.run_apply(api)
                self.assertEqual(api.created, [])

    def test_name_collision_and_changed_existing_secrets_are_not_overwritten(self):
        api = FakeRender("production")
        self.run_apply(api)
        api.vars["srv-test-3"]["CELERY_BROKER_URL"] = "redis://wrong:6379"
        with self.assertRaises(ValueError):
            self.run_apply(api)
        self.assertEqual(len(api.created), 3)
        api = FakeRender("production")
        api.services["collision"] = {**api.web, "name": "amaris-production-beat"}
        with self.assertRaises(ValueError):
            self.run_apply(api)
        self.assertEqual(api.created, [])

    def test_unmanaged_beat_on_same_broker_blocks_duplicate_scheduler(self):
        api = FakeRender("staging")
        api.services["unknown"] = {
            **api.web, "id": "unknown", "name": "legacy-scheduler", "type": "background_worker",
            "serviceDetails": {"envSpecificDetails": {"startCommand": "celery -A amaris_cms beat"}},
        }
        api.vars["unknown"] = api.values
        with self.assertRaisesRegex(ValueError, "Unmanaged"):
            self.run_apply(api)
        self.assertEqual(api.created, [])

    def test_api_cannot_mutate_web_database_or_existing_workers(self):
        api = p.RenderAPI("private-token", allow_create=True)
        for method, path in (("PATCH", "/services/web"), ("DELETE", "/services/worker"), ("POST", "/key-value"), ("POST", "/services/web/deploys")):
            with self.subTest(method=method, path=path):
                with self.assertRaises(ValueError):
                    api.request(method, path, {})
        api = p.RenderAPI("private-token")
        with self.assertRaises(ValueError):
            api.request("POST", "/services", {})

    def test_pagination_rejects_repeated_cursor_instead_of_missing_collisions(self):
        api = FakeRender("staging")
        with patch.object(api, "request", return_value=[{"cursor": "same"}] * 100):
            with self.assertRaisesRegex(ValueError, "pagination"):
                p.rows(api, "/services")


if __name__ == "__main__":
    unittest.main()
