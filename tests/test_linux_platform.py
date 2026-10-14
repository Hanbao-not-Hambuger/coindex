"""Portable defaults and Linux integration, with fictional data only."""
import json
import os
import pathlib
import select
import subprocess
import sys
import tempfile
import unittest
import uuid
from unittest.mock import patch

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "backend"))
from connections import codex_path
from nudge import open_desktop_thread
from platform_paths import default_data_dir
from store import Store
from test_backend import conversation, entry


class PlatformTests(unittest.TestCase):
    def test_data_defaults_use_xdg_and_ignore_relative_xdg_paths(self):
        with patch("platform_paths.sys.platform", "linux"), patch.dict(os.environ, {}, clear=True), patch("pathlib.Path.home", return_value=pathlib.Path("/example-home")):
            self.assertEqual(default_data_dir(), pathlib.Path("/example-home/.local/share/coindex"))
            with patch.dict(os.environ, {"XDG_DATA_HOME": "/data with spaces"}):
                self.assertEqual(default_data_dir(), pathlib.Path("/data with spaces/coindex"))
            with patch.dict(os.environ, {"XDG_DATA_HOME": "relative"}):
                self.assertEqual(default_data_dir(), pathlib.Path("/example-home/.local/share/coindex"))

    def test_macos_default_and_explicit_data_override_are_preserved(self):
        with patch("platform_paths.sys.platform", "darwin"), patch.dict(os.environ, {}, clear=True):
            self.assertEqual(default_data_dir(), pathlib.Path.home() / "Library/Application Support/CodexTodo")
            with patch.dict(os.environ, {"CODEX_TODO_DATA_DIR": "~/private-coindex"}):
                self.assertEqual(default_data_dir(), pathlib.Path.home() / "private-coindex")

    def test_linux_opener_has_one_encoded_url_argument(self):
        thread = str(uuid.uuid4())
        with patch("nudge.sys.platform", "linux"), patch("nudge.shutil.which", return_value="/usr/bin/xdg-open"), patch("nudge.subprocess.run") as run:
            open_desktop_thread(thread, "remote-ssh-discovered:example lab")
        self.assertEqual(run.call_args.args[0], ["/usr/bin/xdg-open", "codex://threads/" + thread + "?hostId=remote-ssh-discovered%3Aexample+lab"])
        self.assertNotIn("shell", run.call_args.kwargs)

    def test_invalid_thread_and_missing_opener_fail_before_launch(self):
        with patch("nudge.subprocess.run") as run:
            with self.assertRaises(ValueError):
                open_desktop_thread("../../example", "local")
            run.assert_not_called()
        with patch("nudge.sys.platform", "linux"), patch("nudge.shutil.which", return_value=None):
            with self.assertRaisesRegex(RuntimeError, "xdg-open"):
                open_desktop_thread(str(uuid.uuid4()), "local")

    def test_linux_app_discovers_adjacent_cli_before_path(self):
        with tempfile.TemporaryDirectory() as folder, patch("connections.sys.platform", "linux"), patch.dict(os.environ, {"CODEX_TODO_CODEX": ""}):
            root = pathlib.Path(folder)
            app = root / "Codex Desktop"
            cli = root / "resources/codex"
            cli.parent.mkdir()
            for executable in (app, cli):
                executable.write_text("#!/bin/sh\nexit 0\n")
                executable.chmod(0o700)
            self.assertEqual(codex_path({"codex_app": str(app)}), str(cli.resolve()))
            with self.assertRaisesRegex(RuntimeError, "无法执行"):
                codex_path({"codex_app": str(root / "missing")})

    @unittest.skipUnless(sys.platform.startswith("linux"), "Linux desktop executable integration")
    def test_service_opens_only_stored_conversations_and_preserves_source_identity(self):
        with tempfile.TemporaryDirectory() as folder:
            root = pathlib.Path(folder)
            thread = str(uuid.uuid4())
            conv = conversation("mac:" + thread)
            store = Store(root / "data")
            store.ingest(dict(host="mac", files={}, conversations=[conv], total_files=1, remaining_files=0, root="/example"))
            store.reconcile([entry(conv["id"])], [conv])
            manual = store.save_manual("Example manual task")
            app = root / "desktop with spaces"
            output = root / "opened-url"
            app.write_text("#!" + sys.executable + "\nimport pathlib,sys\npathlib.Path(" + repr(str(output)) + ").write_text(sys.argv[1])\n")
            app.chmod(0o700)
            store.save_settings({"codex_app": str(app), "workdays_only": False, "automatic": False})
            self.assertEqual(store.snapshot()["hosts"][0]["id"], "mac")
            self.assertEqual(store.snapshot()["hosts"][0]["name"], "本机 Linux")
            store.db.close()
            service = pathlib.Path(__file__).resolve().parents[1] / "backend/service.py"
            child = subprocess.Popen([sys.executable, str(service), "--data-dir", str(root / "data"), "serve"], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            try:
                def request(ident, entity):
                    child.stdin.write(json.dumps({"id": ident, "method": "open_thread", "entity_id": entity}) + "\n")
                    child.stdin.flush()
                    self.assertTrue(select.select([child.stdout], [], [], 8)[0], "service response timed out")
                    response = json.loads(child.stdout.readline())
                    self.assertEqual(response["id"], ident)
                    return response
                self.assertIn("error", request(1, manual))
                self.assertIn("error", request(2, "not-a-stored-thread"))
                self.assertEqual(request(3, conv["id"])["result"], {"opened": True})
                self.assertEqual(output.read_text(), "codex://threads/" + thread + "?hostId=local")
                child.stdin.close()
                child.wait(timeout=5)
                self.assertEqual(child.returncode, 0)
            finally:
                if child.poll() is None:
                    child.terminate()
                    child.wait(timeout=5)
                child.stdout.close()
                child.stderr.close()


if __name__ == "__main__":
    unittest.main()
