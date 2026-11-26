import copy
import importlib.util
import unittest
from pathlib import Path
from test_render_stateless_task import TaskTests, renderer

spec = importlib.util.spec_from_file_location("split", Path(__file__).with_name("render-multitask.py"))
split = importlib.util.module_from_spec(spec)
spec.loader.exec_module(split)

class SplitTests(unittest.TestCase):
    def fixture(self):
        old = TaskTests()
        old.setUp()
        task = old.task
        for c in task["containerDefinitions"]:
            if c["name"] == "backend":
                c["image"] = old.images[0]
            elif c["name"] == "frontend":
                c["image"] = old.images[1]
            elif c["name"] == "cms":
                c["image"] = "nginx@sha256:" + "a" * 64
        task["volumes"].append({"name": "staging-celery-config"})
        for name in ("celery-worker", "celery-beat"):
            task["containerDefinitions"].append({
                "name": name, "image": old.images[0], "mountPoints": [{"sourceVolume": "staging-celery-config"}],
                "dependsOn": [{"containerName": "valkey", "condition": "HEALTHY"}],
                "command": ["python", "-m", "celery", "-A", "staging_celery:app", name.removeprefix("celery-")]
            })
        return task

    def test_split(self):
        original = self.fixture()
        snapshot = copy.deepcopy(original)
        result = split.render(original)
        self.assertEqual(original, snapshot)
        self.assertEqual({c["name"] for c in result["web"]["containerDefinitions"]}, {"backend", "frontend", "cms"})
        self.assertEqual({c["name"] for c in result["jobs"]["containerDefinitions"]}, {"celery-worker", "celery-beat"})
        for task in result.values():
            self.assertEqual(task["volumes"], [])
            for c in task["containerDefinitions"]:
                self.assertFalse(c.get("mountPoints"))
                self.assertNotIn("redis://127.0.0.1", str(c))
        for c in result["jobs"]["containerDefinitions"]:
            self.assertTrue(c["essential"])
            self.assertEqual(len(c["secrets"]), 5)
            self.assertIn("AMARIS_CELERY_CONFIG", c["entryPoint"][2])
            self.assertIn("deliver-video-request-notifications", c["entryPoint"][2])

    def test_private_host_ca_injected_for_web_and_jobs(self):
        result = split.render(self.fixture(), host_valkey=True)
        for task in result.values():
            for c in task["containerDefinitions"]:
                if c["name"] in {"backend", "celery-worker", "celery-beat"}:
                    self.assertIn({"name": "AMARIS_SHARED_VALKEY_CA", "valueFrom": renderer.SSM + "ca"}, c["secrets"])
                    self.assertIn("test -s /tmp/amaris-shared-valkey-ca.pem", c["entryPoint"][2])
                    self.assertIn("unset AMARIS_SHARED_VALKEY_CA", c["entryPoint"][2])

    def test_reject_unknown_volume(self):
        original = self.fixture()
        original["volumes"].append({"name": "unknown"})
        with self.assertRaises(ValueError):
            split.render(original)

if __name__ == "__main__":
    unittest.main()
