import os
import signal
import tempfile
import threading
from pathlib import Path
from unittest import TestCase
from unittest.mock import Mock, patch

from amaris_cms.runtime_config import recommended_workers
from amaris_cms.web_runtime import port_number, render_config, serve, stop_process


class WebRuntimeTests(TestCase):
    def test_small_container_reserves_memory_for_notification_processes(self):
        with tempfile.TemporaryDirectory() as root, patch.dict(os.environ, {"AMARIS_COLOCATE_NOTIFICATIONS": "true"}):
            cgroup = Path(root)
            (cgroup / "cpu.max").write_text("50000 100000")
            (cgroup / "memory.max").write_text(str(1024 * 1024 * 1024))
            self.assertEqual(recommended_workers(cgroup), 1)

    def test_large_host_does_not_create_an_unbounded_number_of_workers(self):
        with tempfile.TemporaryDirectory() as root, patch("os.cpu_count", return_value=128):
            self.assertEqual(recommended_workers(Path(root)), 4)

    def test_proxy_keeps_private_paths_and_write_failures_out_of_cache(self):
        with tempfile.TemporaryDirectory() as root, patch.dict(os.environ, {"NGINX_TRUST_FORWARDED_PROTO": "false"}):
            config = render_config(Path(root), 10000, 8001).read_text()
        self.assertIn("listen 0.0.0.0:10000;", config)
        self.assertIn("server 127.0.0.1:8001;", config)
        self.assertIn("location ^~ /media/ { return 404; }", config)
        self.assertIn("proxy_next_upstream off;", config)
        self.assertIn("proxy_cache off;", config)
        self.assertNotIn('"https" https;', config)
        self.assertNotIn("@@", config)

    def test_forwarded_https_requires_explicit_trusted_edge(self):
        with tempfile.TemporaryDirectory() as root, patch.dict(os.environ, {"NGINX_TRUST_FORWARDED_PROTO": "true"}):
            self.assertIn('"https" https;', render_config(Path(root), 10000, 8001).read_text())

    def test_nginx_retires_idle_upstream_sockets_before_gunicorn(self):
        with tempfile.TemporaryDirectory() as root, patch.dict(os.environ, {"GUNICORN_KEEPALIVE": "2"}):
            self.assertIn("keepalive_timeout 1s;", render_config(Path(root), 10000, 8001).read_text())

    def test_invalid_or_colliding_ports_fail_before_startup(self):
        for value in ("80", "65536", "-1", "not-a-port"):
            with self.subTest(value=value), patch.dict(os.environ, {"PORT": value}), self.assertRaises(ValueError):
                port_number("PORT", 8000)
        with tempfile.TemporaryDirectory() as root, self.assertRaises(ValueError):
            render_config(Path(root), 8000, 8000)

    @patch("amaris_cms.web_runtime.subprocess.run")
    @patch("amaris_cms.web_runtime.subprocess.Popen")
    def test_proxy_death_stops_gunicorn_and_returns_failure(self, popen, run):
        gunicorn = Mock()
        gunicorn.poll.return_value = None
        proxy = Mock()
        proxy.poll.return_value = 1
        popen.side_effect = [gunicorn, proxy]
        with tempfile.TemporaryDirectory() as root:
            self.assertEqual(serve(Path(root), threading.Event()), 1)
        gunicorn.send_signal.assert_called_once_with(signal.SIGTERM)
        gunicorn.wait.assert_called_once_with(timeout=60)
        run.assert_called_once()
        self.assertEqual(popen.call_args_list[0].kwargs["env"]["GUNICORN_BIND"], "127.0.0.1:8001")

    def test_graceful_shutdown_signals_master_and_reaps_it(self):
        child = Mock()
        child.poll.return_value = None
        stop_process(child, signal.SIGQUIT, 30)
        child.send_signal.assert_called_once_with(signal.SIGQUIT)
        child.wait.assert_called_once_with(timeout=30)
