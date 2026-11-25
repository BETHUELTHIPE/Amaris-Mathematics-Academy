import copy
import importlib.util
import unittest
from pathlib import Path

spec = importlib.util.spec_from_file_location("renderer", Path(__file__).with_name("render-stateless-task.py"))
renderer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(renderer)


class TaskTests(unittest.TestCase):
    def setUp(self):
        self.images = [renderer.REPO + "@sha256:" + char * 64 for char in "abc"]
        self.task = {
            "family": "amaris-ecs-staging-alb-web",
            "networkMode": "awsvpc",
            "runtimePlatform": {"cpuArchitecture": "ARM64", "operatingSystemFamily": "LINUX"},
            "requiresCompatibilities": ["EC2"],
            "executionRoleArn": "test-role",
            "revision": 17,
            "volumes": [{"name": n} for n in ("valkey-data", "cms-proxy", "proxy-headers")],
            "containerDefinitions": [
                {"name": "valkey", "mountPoints": [{"sourceVolume": "valkey-data"}]},
                {
                    "name": "backend",
                    "entryPoint": ["/bin/sh", "-ec", "\n".join(
                        f"export {key}=redis://127.0.0.1:6379/{i}"
                        for i, key in enumerate(renderer.URLS)
                    ) + '\nexec "$@"'],
                    "secrets": [{"name": "AMARIS_RUNTIME_ENV", "valueFrom": "existing"}],
                    "dependsOn": [{"containerName": "valkey", "condition": "HEALTHY"}],
                },
                {"name": "frontend", "dependsOn": [{"containerName": "cms", "condition": "START"}]},
                {"name": "cms", "mountPoints": [{"sourceVolume": "cms-proxy"}, {"sourceVolume": "proxy-headers"}]},
            ],
        }

    def test_shared_state_and_immutable_images(self):
        task = renderer.render(copy.deepcopy(self.task), *self.images)
        containers = {c["name"]: c for c in task["containerDefinitions"]}
        self.assertEqual(set(containers), {"backend", "frontend", "cms"})
        self.assertEqual(task["volumes"], [])
        self.assertNotIn("revision", task)
        for name, image in zip(("backend", "frontend", "cms"), self.images):
            self.assertEqual(containers[name]["image"], image)
        backend = containers["backend"]
        self.assertNotIn("127.0.0.1:6379", backend["entryPoint"][2])
        self.assertNotIn("dependsOn", backend)
        self.assertEqual(len(backend["secrets"]), 5)
        for key, suffix in renderer.URLS.items():
            self.assertIn("AMARIS_SHARED_" + key, backend["entryPoint"][2])
            self.assertIn({"name": "AMARIS_SHARED_" + key, "valueFrom": renderer.SSM + suffix}, backend["secrets"])

    def test_reject_floating_image(self):
        with self.assertRaises(renderer.argparse.ArgumentTypeError):
            renderer.render(copy.deepcopy(self.task), renderer.REPO + ":latest", *self.images[1:])

    def test_reject_unreviewed_host_volume(self):
        self.task["volumes"].append({"name": "other"})
        with self.assertRaises(ValueError):
            renderer.render(self.task, *self.images)

    def test_reject_unreviewed_broker_configuration(self):
        self.task["containerDefinitions"][1]["entryPoint"][2] = "exec app"
        with self.assertRaises(ValueError):
            renderer.render(self.task, *self.images)


if __name__ == "__main__":
    unittest.main()
