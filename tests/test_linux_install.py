import os
from pathlib import Path
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
INSTALLER = ROOT / "scripts/install-linux.sh"


class LinuxInstallerTests(unittest.TestCase):
    def bundle(self, folder):
        bundle = folder / "source bundle with spaces $ and 'quote'"
        (bundle / "linux").mkdir(parents=True)
        (bundle / "Resources/Brand").mkdir(parents=True)
        (bundle / "backend").mkdir()
        app = bundle / "linux/app.py"
        app.write_text(
            "import sys\n"
            "if '--help' in sys.argv: print('coindex test app help')\n"
            "else: raise SystemExit('unexpected GUI launch')\n",
            encoding="utf-8",
        )
        launcher = bundle / "coindex"
        launcher.write_text(
            "#!/bin/sh\n# Managed by coindex build-linux.sh\n"
            "APP_DIR=\"$(CDPATH= cd -- \"$(dirname -- \"$0\")\" && pwd)\"\n"
            "exec python3 \"$APP_DIR/linux/app.py\" \"$@\"\n",
            encoding="utf-8",
        )
        launcher.chmod(0o755)
        (bundle / "Resources/Brand/AppIcon.png").write_bytes(b"fake icon payload")
        return bundle

    def invoke(self, env, *args, cwd=None):
        return subprocess.run([str(INSTALLER), *map(str, args)], env=env, text=True,
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE, cwd=cwd)

    def test_help_does_not_need_a_bundle(self):
        result = self.invoke(dict(os.environ), "--help")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("--prefix", result.stdout)

    def test_install_rerun_and_run_help_preserve_user_data(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = self.bundle(root)
            prefix = root / 'prefix with spaces $ and \'quote\' "double" \\backtick` percent%'
            data_home = root / "data home with spaces $ and 'quote'"
            env = dict(os.environ, XDG_DATA_HOME=str(data_home), COINDEX_BUNDLE_DIR=str(source),
                       COINDEX_PREFIX=str(prefix))
            result = self.invoke(env)
            self.assertEqual(result.returncode, 0, result.stderr)
            installed_app = data_home / "coindex-app"
            self.assertTrue((installed_app / "linux/app.py").is_file())
            self.assertFalse((data_home / "coindex").exists())
            (data_home / "coindex").mkdir()
            db = data_home / "coindex/todos.sqlite"
            db.write_bytes(b"preserve me")
            (source / "linux/app.py").write_text(
                "import sys\n"
                "if '--help' in sys.argv: print('upgraded app help')\n"
                "else: raise SystemExit('unexpected GUI launch')\n",
                encoding="utf-8",
            )
            managed_launcher = prefix / "bin/coindex"
            managed_launcher.unlink()
            managed_launcher.symlink_to(installed_app / "coindex")
            unrelated_temp = data_home / "icons/hicolor/512x512/apps/.org.coindex.desktop.png.tmp"
            unrelated_temp.parent.mkdir(parents=True, exist_ok=True)
            unrelated_temp.write_bytes(b"unrelated temporary file")

            result = self.invoke(env)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(db.read_bytes(), b"preserve me")
            self.assertEqual(unrelated_temp.read_bytes(), b"unrelated temporary file")
            help_result = subprocess.run([str(prefix / "bin/coindex"), "--help"], env=env, text=True,
                                         stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            self.assertEqual(help_result.returncode, 0, help_result.stderr)
            self.assertIn("upgraded app help", help_result.stdout)
            desktop = data_home / "applications/org.coindex.desktop.desktop"
            desktop_text = desktop.read_text(encoding="utf-8")
            self.assertIn('# Managed by coindex install-linux.sh', desktop_text)
            exec_line = next(line for line in desktop_text.splitlines() if line.startswith("Exec="))
            self.assertIn("%%", exec_line)
            self.assertEqual(len(exec_line.split("$", 1)[0]) - len(exec_line.split("$", 1)[0].rstrip("\\")), 2)
            before_double = exec_line.split("double", 1)[0]
            quote = before_double.rfind('"')
            self.assertEqual(len(before_double[:quote]) - len(before_double[:quote].rstrip("\\")), 2)
            before_backtick = exec_line.split("backtick", 1)[0]
            self.assertEqual(len(before_backtick) - len(before_backtick.rstrip("\\")), 4)
            tick = exec_line.index("`")
            self.assertEqual(len(exec_line[:tick]) - len(exec_line[:tick].rstrip("\\")), 2)

    def test_refuses_to_overwrite_unrelated_launcher(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = self.bundle(root)
            prefix = root / "prefix"
            launcher = prefix / "bin/coindex"
            launcher.parent.mkdir(parents=True)
            launcher.write_text("user-owned launcher\n", encoding="utf-8")
            env = dict(os.environ, XDG_DATA_HOME=str(root / "data"), COINDEX_BUNDLE_DIR=str(source))
            result = self.invoke(env, "--prefix", prefix)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("Refusing to overwrite", result.stderr)
            self.assertEqual(launcher.read_text(encoding="utf-8"), "user-owned launcher\n")
            self.assertFalse((root / "data/coindex-app").exists())

    def test_refuses_to_overwrite_unrelated_application_payload(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = self.bundle(root)
            data_home = root / "data"
            app_dir = data_home / "coindex-app"
            app_dir.mkdir(parents=True)
            marker = app_dir / "keep.txt"
            marker.write_text("user-owned payload", encoding="utf-8")
            env = dict(os.environ, XDG_DATA_HOME=str(data_home), COINDEX_BUNDLE_DIR=str(source))
            result = self.invoke(env, "--prefix", root / "prefix")
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("unrecognized app directory", result.stderr)
            self.assertEqual(marker.read_text(encoding="utf-8"), "user-owned payload")

    def test_relative_xdg_data_home_falls_back_to_default(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = self.bundle(root)
            home = root / "home"
            working = root / "working"
            home.mkdir()
            working.mkdir()
            env = dict(os.environ, HOME=str(home), XDG_DATA_HOME="relative-data",
                       COINDEX_BUNDLE_DIR=str(source))
            result = self.invoke(env, "--prefix", root / "prefix", cwd=working)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue((home / ".local/share/coindex-app/coindex").is_file())
            self.assertFalse((working / "relative-data").exists())

    def test_refuses_source_nested_in_install_destination(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            data_home = root / "data"
            source = self.bundle(data_home / "coindex-app")
            env = dict(os.environ, XDG_DATA_HOME=str(data_home), COINDEX_BUNDLE_DIR=str(source))
            result = self.invoke(env, "--prefix", root / "prefix")
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("into or around its source", result.stderr)
            self.assertTrue((source / "coindex").is_file())

    def test_upgrade_failure_keeps_installed_app_and_user_data(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = self.bundle(root)
            data_home = root / "data"
            prefix = root / "prefix"
            env = dict(os.environ, XDG_DATA_HOME=str(data_home), COINDEX_BUNDLE_DIR=str(source))
            first = self.invoke(env, "--prefix", prefix)
            self.assertEqual(first.returncode, 0, first.stderr)
            app_dir = data_home / "coindex-app"
            (data_home / "coindex").mkdir()
            db = data_home / "coindex/todos.sqlite"
            db.write_bytes(b"keep database")
            backup = app_dir.with_name("coindex-app.previous")
            backup.mkdir()
            (backup / "keep.txt").write_text("stale backup", encoding="utf-8")
            (source / "linux/app.py").write_text("print('new version')\n", encoding="utf-8")

            failed = self.invoke(env, "--prefix", prefix)
            self.assertNotEqual(failed.returncode, 0)
            self.assertIn("existing upgrade backup", failed.stderr)
            self.assertIn("coindex test app help", (app_dir / "linux/app.py").read_text(encoding="utf-8"))
            self.assertEqual(db.read_bytes(), b"keep database")
            self.assertEqual((backup / "keep.txt").read_text(encoding="utf-8"), "stale backup")

    def test_rejects_newline_launcher_path_before_install_mutations(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = self.bundle(root)
            data_home = root / "data"
            env = dict(os.environ, XDG_DATA_HOME=str(data_home), COINDEX_BUNDLE_DIR=str(source))
            result = self.invoke(env, "--prefix", root / "prefix\nExec=malicious")
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("newline", result.stderr)
            self.assertFalse((data_home / "coindex-app").exists())


if __name__ == "__main__":
    unittest.main()
