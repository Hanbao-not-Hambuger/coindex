#!/usr/bin/env python3
"""Install the Linux bundle for the current user without elevated privileges."""
import argparse
import os
from pathlib import Path
import shutil
import sys
import tempfile

MARKER = "# Managed by coindex install-linux.sh"
DESKTOP_MARKER = "# Managed by coindex install-linux.sh"


def default_data_home():
    value = os.environ.get("XDG_DATA_HOME")
    return Path(value).expanduser() if value else Path.home() / ".local/share"


def desktop_quote(value):
    """Quote one .desktop Exec argument according to the Desktop Entry spec."""
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    escaped = escaped.replace("`", "\\`").replace("$", "\\$").replace("%", "%%")
    return '"' + escaped + '"'


def managed_launcher(path, app_launcher):
    if path.is_symlink():
        return path.resolve(strict=False) == app_launcher.resolve(strict=False)
    try:
        return path.is_file() and MARKER in path.read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        return False


def write_atomic(path, contents, mode=0o644):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix="." + path.name + ".", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            stream.write(contents)
        os.chmod(temp_name, mode)
        os.replace(temp_name, path)
    finally:
        try:
            os.unlink(temp_name)
        except FileNotFoundError:
            pass


def replace_bundle(source, destination):
    destination.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=".coindex-stage-", dir=str(destination.parent)))
    backup = destination.with_name(destination.name + ".previous")
    try:
        shutil.rmtree(stage)
        shutil.copytree(source, stage)
        if destination.is_symlink():
            raise RuntimeError("Refusing to replace a symbolic-link app directory: " + str(destination))
        if backup.exists():
            raise RuntimeError("Refusing to replace an existing upgrade backup: " + str(backup))
        if destination.exists():
            destination.rename(backup)
        try:
            stage.rename(destination)
        except BaseException:
            if backup.exists() and not destination.exists():
                backup.rename(destination)
            raise
        if backup.exists():
            shutil.rmtree(backup)
    finally:
        if stage.exists():
            shutil.rmtree(stage)


def install(source, prefix, data_home):
    source = source.expanduser().resolve()
    prefix = prefix.expanduser().absolute()
    data_home = data_home.expanduser().absolute()
    if not (source / "coindex").is_file() or not (source / "linux/app.py").is_file():
        raise RuntimeError("Linux bundle is missing coindex or linux/app.py: " + str(source))
    if not (source / "Resources/Brand/AppIcon.png").is_file():
        raise RuntimeError("Linux bundle is missing its application icon: " + str(source))
    if not os.access(source / "coindex", os.X_OK):
        raise RuntimeError("Linux bundle launcher is not executable: " + str(source / "coindex"))

    app_dir = data_home / "coindex-app"
    installed_launcher = app_dir / "coindex"
    launcher = prefix / "bin/coindex"
    applications = data_home / "applications"
    desktop = applications / "org.coindex.desktop.desktop"
    icon = data_home / "icons/hicolor/512x512/apps/org.coindex.desktop.png"

    # Check every fixed integration point before changing any of them.
    if launcher.exists() or launcher.is_symlink():
        if not managed_launcher(launcher, installed_launcher / "coindex"):
            raise RuntimeError("Refusing to overwrite an existing launcher: " + str(launcher))
    if desktop.exists() or desktop.is_symlink():
        try:
            own_desktop = desktop.is_file() and DESKTOP_MARKER in desktop.read_text(encoding="utf-8")
        except (OSError, UnicodeError):
            own_desktop = False
        if not own_desktop:
            raise RuntimeError("Refusing to overwrite an existing desktop entry: " + str(desktop))
    if (icon.exists() or icon.is_symlink()) and not desktop.exists():
        raise RuntimeError("Refusing to overwrite an existing icon without a managed desktop entry: " + str(icon))

    replace_bundle(source, app_dir)
    launcher.parent.mkdir(parents=True, exist_ok=True)
    launcher_text = "#!/bin/sh\n" + MARKER + "\nexec " + shell_quote(str(installed_launcher)) + ' "$@"\n'
    if launcher.is_symlink():
        launcher.unlink()
    write_atomic(launcher, launcher_text, 0o755)

    desktop_text = "\n".join((
        "[Desktop Entry]", DESKTOP_MARKER, "Version=1.0", "Type=Application", "Name=coindex",
        "Comment=Follow up on work delegated to Codex", "Exec=" + desktop_quote(str(launcher)),
        "Icon=org.coindex.desktop", "Terminal=false", "Categories=Development;Utility;",
        "StartupNotify=true", "", "",
    ))
    write_atomic(desktop, desktop_text)
    icon.parent.mkdir(parents=True, exist_ok=True)
    icon_tmp = icon.with_name("." + icon.name + ".tmp")
    try:
        shutil.copyfile(app_dir / "Resources/Brand/AppIcon.png", icon_tmp)
        os.replace(icon_tmp, icon)
    finally:
        try:
            icon_tmp.unlink()
        except FileNotFoundError:
            pass
    print("Installed coindex for this user.")
    print("Launcher: " + str(launcher))
    print("Application data: " + str(data_home / "coindex"))


def shell_quote(value):
    return "'" + value.replace("'", "'\\''") + "'"


def main(argv=None):
    here = Path(__file__).resolve().parents[1]
    default_source = here if (here / "coindex").is_file() else here / "dist/coindex-linux"
    parser = argparse.ArgumentParser(description="Install the coindex Linux bundle for the current user.")
    parser.add_argument("--prefix", type=Path, default=Path(os.environ.get("COINDEX_PREFIX", "~/.local")),
                        help="installation prefix for the coindex launcher (default: ~/.local)")
    parser.add_argument("--source", type=Path,
                        default=Path(os.environ.get("COINDEX_BUNDLE_DIR", str(default_source))),
                        help="built Linux bundle directory")
    args = parser.parse_args(argv)
    try:
        install(args.source, args.prefix, default_data_home())
    except (OSError, RuntimeError) as error:
        print("coindex installer: " + str(error), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
