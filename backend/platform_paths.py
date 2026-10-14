"""Platform defaults shared by the service and desktop frontends."""
import os
import pathlib
import sys


def default_data_dir():
    override = os.environ.get("CODEX_TODO_DATA_DIR")
    if override:
        return pathlib.Path(override).expanduser()
    if sys.platform == "darwin":
        return pathlib.Path.home() / "Library/Application Support/CodexTodo"
    base = os.environ.get("XDG_DATA_HOME", "")
    # XDG paths must be absolute; relative values are ignored per the spec.
    root = pathlib.Path(base) if base and pathlib.Path(base).is_absolute() else pathlib.Path.home() / ".local/share"
    return root / "coindex"


def local_host_name():
    return "这台 Mac" if sys.platform == "darwin" else "本机 Linux"
