from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def text(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


class ProductionArchitectureContractTests(unittest.TestCase):
    def test_autoscaling_pooling_and_queue_isolation_are_declared(self) -> None:
        manifest = text("deploy/kubernetes/production.yaml")
        for required in (
            "replicas: 3",
            "minReplicas: 3",
            "maxReplicas: 24",
            "averageUtilization: 70",
            "name: pgbouncer",
            "value: transaction",
            "DATABASE_URL_POOLED",
            "--queues=critical,default",
            "--queues=notifications",
            "amaris-cache-warm",
        ):
            self.assertIn(required, manifest)

    def test_edge_security_and_homepage_preload_are_enforced(self) -> None:
        worker = text("frontend/worker/index.ts")
        for required in (
            "AUTH_RATE_LIMITER",
            "REGISTER_RATE_LIMITER",
            "PASSWORD_RESET_RATE_LIMITER",
            "CHECKOUT_RATE_LIMITER",
            '"Content-Security-Policy"',
            '"Content-Security-Policy-Report-Only"',
            '"Referrer-Policy"',
            'pathname === "/"',
            "amaris-math-hero.webp",
            "rel=preload",
        ):
            self.assertIn(required, worker)

    def test_monitoring_is_private_and_alert_routing_exists(self) -> None:
        nginx = text("backend/nginx/default.conf")
        self.assertIn("location ^~ /monitoring/flower/ { return 404; }", nginx)
        self.assertIn("location ^~ /monitoring/grafana/ { return 404; }", nginx)
        self.assertIn("location ^~ /monitoring/pgadmin/ { return 404; }", nginx)
        self.assertIn("limit_req_zone", nginx)

        prometheus = text("backend/monitoring/prometheus/prometheus.yml")
        self.assertIn("alertmanagers:", prometheus)
        self.assertIn('targets: ["alertmanager:9093"]', prometheus)

        alertmanager = text("backend/monitoring/alertmanager/alertmanager.yml")
        self.assertIn("url_file: /run/secrets/alertmanager_webhook_url", alertmanager)

    def test_required_slo_alerts_exist(self) -> None:
        rules = text("backend/monitoring/prometheus/rules/performance.yml")
        for alert in (
            "AmarisPublicApiP99LatencyHigh",
            "AmarisHttp5xxRateHigh",
            "AmarisPostgresConnectionsHigh",
            "AmarisCacheHitRatioDropped",
            "AmarisCeleryQueueAgeHigh",
            "AmarisCacheRedisMemoryHigh",
            "AmarisTLSCertificateExpiring",
            "AmarisPaymentWebhookFailureRateHigh",
            "AmarisPaymentWebhookP95LatencyHigh",
        ):
            self.assertIn(alert, rules)

    def test_performance_profiles_match_capacity_architecture(self) -> None:
        config = text("backend/load_tests/config.py")
        for concurrency in ("2500", "5000", "7500", "10000", "15000", "25000"):
            self.assertIn(concurrency, config.replace("_", ""))
        self.assertIn("500, 1000, 750, 1000", config)
        self.assertIn('"normal": Thresholds(0.009', config)
        self.assertIn('"peak": Thresholds(0.019', config)

    def test_image_build_and_release_gate_fixable_high_critical_findings(self) -> None:
        dockerfile = text("backend/Dockerfile")
        self.assertIn("RESTIC_VERSION=0.19.1", dockerfile)
        self.assertIn('"setuptools>=78.1.1"', dockerfile)
        self.assertIn('"msgpack>=1.2.1,<2.0"', dockerfile)

        workflow = text(".github/workflows/quality-release.yml")
        self.assertIn("severity: HIGH,CRITICAL", workflow)
        self.assertIn("ignore-unfixed: true", workflow)
        self.assertIn("frontend-sbom.cdx.json", workflow)
        self.assertIn("npm audit --audit-level=high", workflow)

    def test_operational_governance_is_explicit(self) -> None:
        operations = text("docs/OPERATIONS_READINESS.md")
        for required in (
            "Primary On-Call Engineer",
            "Sev1",
            "PostgreSQL connection exhaustion",
            "Celery queue backlog",
            "PayFast timeout or webhook failure spike",
            "TLS/certificate expiry",
            "within **10 minutes**",
            "AMARIS_FEATURE_FLAGS",
            "change freeze",
            "Data retention and deletion policy",
            "Post-incident review template",
        ):
            self.assertIn(required, operations)

        migration_register = text("backend/docs/MIGRATION_REGISTER.md")
        for migration in ("0001_initial", "0002_payment_reliability", "0003_", "0004_payment_authority", "0005_payment_status_cancelled"):
            self.assertIn(migration, migration_register)


if __name__ == "__main__":
    unittest.main()
