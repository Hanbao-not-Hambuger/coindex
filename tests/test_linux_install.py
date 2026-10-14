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
            "#!/bin/sh\nAPP_DIR=\"$(CDPATH= cd -- \"$(dirname -- \"$0\")\" && pwd)\"\n"
            "exec python3 \"$APP_DIR/linux/app.py\" \"$@\"\n",
            encoding="utf-8",
        )
        launcher.chmod(0o755)
        (bundle / "Resources/Brand/AppIcon.png").write_bytes(b"fake icon payload")
        return bundle

    def invoke(self, env, *args):
        return subprocess.run([str(INSTALLER), *map(str, args)], env=env, text=True,
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    def test_help_does_not_need_a_bundle(self):
        result = self.invoke(dict(os.environ), "--help")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("--prefix", result.stdout)

    def test_install_rerun_and_run_help_preserve_user_data(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = self.bundle(root)
            prefix = root / "prefix with spaces $ and 'quote'"
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

            result = self.invoke(env)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(db.read_bytes(), b"preserve me")
            help_result = subprocess.run([str(prefix / "bin/coindex"), "--help"], env=env, text=True,
                                         stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            self.assertEqual(help_result.returncode, 0, help_result.stderr)
            self.assertIn("upgraded app help", help_result.stdout)
            desktop = data_home / "applications/org.coindex.desktop.desktop"
            self.assertIn('# Managed by coindex install-linux.sh', desktop.read_text(encoding="utf-8"))
            self.assertIn('"' + str(prefix / "bin/coindex").replace("$", "\\$").replace("%", "%%") + '"',
                          desktop.read_text(encoding="utf-8"))

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


if __name__ == "__main__":
    unittest.main()
