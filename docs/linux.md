# Linux desktop

coindex's Linux interface is a native Tkinter desktop application that reuses the Python backend. It targets mainstream Linux desktop sessions with Python 3.9 or later; no third-party Python packages are required.

## Dependencies

Install Python and Tkinter from the same distribution package set:

| Distribution | Packages |
| --- | --- |
| Debian / Ubuntu | `python3`, `python3-tk` |
| Fedora | `python3`, `python3-tkinter` |

The installer does not run a package manager or use sudo. Verify the desktop Python has Tkinter with `python3 -m tkinter` before starting the app. If the system's `python3` does not have Tkinter, install the distribution package or select a compatible interpreter with `CODEX_TODO_PYTHON=/path/to/python3`.

## Build and install

From a checkout:

```sh
bash scripts/build-linux.sh
bash scripts/install-linux.sh
```

The build creates `dist/coindex-linux`. A release archive can be installed by running its bundled `scripts/install-linux.sh`. The installer copies the bundle to `${XDG_DATA_HOME:-~/.local/share}/coindex-app`, writes the command launcher to `~/.local/bin/coindex` by default, and registers a desktop menu entry and icon under the XDG data home. Use `--prefix /custom/path` to choose another launcher prefix. Add `~/.local/bin` to `PATH` if needed.

No administrator access is required. The installer never starts the app or installs dependencies. Re-running it upgrades the program files while retaining `${XDG_DATA_HOME:-~/.local/share}/coindex`, which stores the SQLite database and settings. Do not place personal database files inside `coindex-app`; upgrades replace that program directory.

## Run and test

```sh
coindex
coindex --demo
python3 linux/app.py --demo --data-dir /tmp/coindex-demo-data
```

`--demo` uses fictional tasks and disables real analysis and nudges. Use a separate data directory when developing or testing. The normal default data directory is `${XDG_DATA_HOME:-~/.local/share}/coindex`.

To select a non-default Codex CLI or Python executable for subprocesses, set `CODEX_TODO_CODEX` or `CODEX_TODO_PYTHON` in the desktop session. The app reads the local Codex session directory and existing Codex login; it does not copy credentials into the application bundle.

## Desktop integration limits

Linux provides the main application window and desktop menu launcher. It does not provide the macOS menu-bar pet, system tray, or login-at-startup features. Opening a Codex conversation and sending a nudge require the existing desktop `codex://` handler and Codex desktop IPC to be available in the current session. These integrations can vary by Codex and desktop version. Reading sessions can work even when opening or nudging is unavailable.

For troubleshooting, check that Tkinter imports in the same Python interpreter selected by the launcher, verify `XDG_DATA_HOME` and `~/.local/bin` in the graphical login session, and start `coindex` from a terminal to inspect a startup error.
