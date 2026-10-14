"""Focused checks for the Linux frontend and its real private stdio lifecycle."""
import pathlib
import subprocess
import sys
import tempfile
import time
import tkinter as tk
import unittest
import json

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from linux.app import CoindexApp, StdioClient, demo_snapshot


class DemoUITests(unittest.TestCase):
    def setUp(self):
        try:
            self.root = tk.Tk()
        except tk.TclError as error:
            self.skipTest("Tk display unavailable: %s" % error)
        self.root.withdraw()
        self.app = CoindexApp(self.root, demo=True, demo_data=demo_snapshot())

    def tearDown(self):
        if getattr(self, "root", None):
            try:
                self.app.close()
            except tk.TclError:
                pass

    def test_demo_is_read_only_and_filters_task_list(self):
        self.assertIsNone(self.app.client)
        self.assertEqual(len(self.app.visible_task_ids), 3)
        self.app.kind_var.set("目标")
        self.app._render_tasks()
        self.assertEqual(len(self.app.visible_task_ids), 1)
        self.app.kind_var.set("全部类型")
        self.app.search_var.set("基准测试")
        self.app._render_tasks()
        self.assertEqual(len(self.app.visible_task_ids), 1)
        self.assertTrue(self.app.primary_button.instate(["disabled"]))

    def test_demo_snapshot_contains_separate_progress_and_action(self):
        task = demo_snapshot()["tasks"][0]
        self.assertTrue(task["progress"])
        self.assertTrue(task["next_action"])
        self.assertIn("本机 / Linux", [h["name"] for h in demo_snapshot()["hosts"]])

    def test_task_action_uses_stdio_rpc_transport(self):
        calls = []

        class Process:
            @staticmethod
            def poll():
                return None

        class Client:
            process = Process()
            closed = False

            def request(self, method, callback=None, **values):
                calls.append((method, values))
                return "request-id"

            @staticmethod
            def drain():
                pass

            def close(self):
                self.closed = True

        app = CoindexApp(self.root, demo=False, client_factory=lambda *_args: Client(), demo_data=demo_snapshot())
        app._act("complete", app.snapshot["tasks"][0])
        self.assertEqual(calls[-1][0], "act")
        self.assertEqual(calls[-1][1]["action"], "complete")
        self.assertEqual(calls[-1][1]["entity_id"], "demo-task-0")
        app.client.close()


class StdioLifecycleTests(unittest.TestCase):
    def test_service_snapshot_manual_task_and_clean_eof_shutdown(self):
        with tempfile.TemporaryDirectory(prefix="coindex-ui-test-") as folder:
            proc = subprocess.Popen([sys.executable, str(ROOT / "backend/service.py"), "--data-dir", folder, "serve"],
                                    stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                    text=True, bufsize=1, start_new_session=True)
            try:
                proc.stdin.write('{"id":"s1","method":"snapshot"}\n')
                proc.stdin.flush()
                first = self._read_response(proc, "s1")
                self.assertIn("settings", first["result"])
                proc.stdin.write('{"id":"m1","method":"save_manual","title":"GUI lifecycle check","detail":"temporary data only","priority":2}\n')
                proc.stdin.flush()
                saved = self._read_response(proc, "m1")["result"]
                self.assertEqual(saved["snapshot"]["tasks"][-1]["title"], "GUI lifecycle check")
            finally:
                proc.stdin.close()
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    proc.terminate()
                    proc.wait(timeout=2)
                proc.stdout.close()
                proc.stderr.close()
            self.assertEqual(proc.returncode, 0)

    @staticmethod
    def _read_response(proc, request_id):
        deadline = time.monotonic() + 8
        while time.monotonic() < deadline:
            line = proc.stdout.readline()
            if not line:
                raise AssertionError("service closed its response stream")
            response = json.loads(line)
            if response.get("id") == request_id:
                if response.get("error"):
                    raise AssertionError(response["error"])
                return response
        raise AssertionError("timed out waiting for %s" % request_id)


if __name__ == "__main__":
    unittest.main()
