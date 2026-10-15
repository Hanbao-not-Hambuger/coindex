"""Release check presentation. The service owns networking and URL validation."""
from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk


class UpdateController:
    def __init__(self, app):
        self.app = app
        self.started = False
        self.pending = None
        self.baseline = 0
        self.saw_checking = False
        self.shown_versions = set()
        self.dialog = None

    def check(self, automatic=False):
        if self.app.demo or self.pending:
            return
        state = self.app.snapshot.get("app_update", {})
        self.baseline = state.get("checked_at", 0)
        self.pending = "automatic" if automatic else "manual"
        self.saw_checking = False
        self.app.check_updates_button.configure(state="disabled", text="正在检查…")
        def accepted(response):
            if response.get("error"):
                self.pending = None
                self.app.check_updates_button.configure(state="normal", text="检查更新…")
                if not automatic:
                    messagebox.showerror("检查更新失败", str(response["error"]), parent=self.app.root)
        if self.app._rpc("check_updates", accepted, automatic=automatic) is None:
            self.pending = None
            self.app.check_updates_button.configure(state="normal", text="检查更新…")

    def observe(self):
        if self.app.demo or "app_update" not in self.app.snapshot:
            return
        state = self.app.snapshot["app_update"]
        if not self.started:
            self.started = True
            self.check(automatic=True)
            return
        checking = state.get("checking", False)
        self.app.check_updates_button.configure(text="正在检查…" if checking or self.pending else "检查更新…",
                                               state="disabled" if checking or self.pending else "normal")
        if self.pending and checking:
            self.saw_checking = True
        manual_finished = False
        if self.pending and not checking and (self.saw_checking or state.get("checked_at", 0) > self.baseline):
            manual_finished = self.pending == "manual"
            self.pending = None
            self.app.check_updates_button.configure(state="normal", text="检查更新…")
            if state.get("error"):
                if manual_finished:
                    messagebox.showerror("检查更新失败", state["error"], parent=self.app.root)
                return
            if manual_finished and not state.get("available"):
                messagebox.showinfo("检查更新", "当前已是最新版本 coindex %s。" % state.get("current_version", ""), parent=self.app.root)
                return
        if self.pending or checking:
            return
        version = state.get("version")
        if state.get("available") and state.get("should_prompt") and version and (manual_finished or version not in self.shown_versions):
            self.shown_versions.add(version)
            if self.dialog and self.dialog.win.winfo_exists():
                if self.dialog.version == version:
                    self.dialog.win.lift()
                    return
                self.dialog.win.destroy()
            self.dialog = UpdateDialog(self.app, state)


class UpdateDialog:
    def __init__(self, app, state):
        self.app = app
        self.version = state["version"]
        self.has_download = bool(state.get("download_url") and state.get("download_url") != state.get("url"))
        self.win = tk.Toplevel(app.root)
        self.win.title("coindex 有新版本")
        self.win.geometry("660x550")
        self.win.minsize(560, 420)
        self.win.transient(app.root)
        self.win.configure(bg=app.BG)
        footer = ttk.Frame(self.win, padding=(24, 0, 24, 20))
        footer.pack(side="bottom", fill="x")
        body = ttk.Frame(self.win, padding=24)
        body.pack(fill="both", expand=True)
        ttk.Label(body, text="coindex %s 已发布" % self.version, font=(app.font_family, 18, "bold")).pack(anchor="w")
        ttk.Label(body, text="当前版本 %s · GitHub Releases" % state.get("current_version", ""),
                  style="Muted.TLabel").pack(anchor="w", pady=(6, 16))
        ttk.Label(body, text="更新内容", font=(app.font_family, 11, "bold")).pack(anchor="w", pady=(0, 8))
        content = ttk.Frame(body)
        content.pack(fill="both", expand=True)
        self.notes = tk.Text(content, wrap="word", bg=app.SURFACE, fg=app.INK, relief="flat", borderwidth=0,
                             font=(app.font_family, 10), padx=16, pady=16, width=50, height=10)
        scroll = ttk.Scrollbar(content, orient="vertical", command=self.notes.yview)
        self.notes.configure(yscrollcommand=scroll.set)
        self.notes.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")
        # Release notes are untrusted plain text, never executable markup.
        self.notes.insert("1.0", state.get("notes") or "这个版本尚未提供更新说明。")
        self.notes.configure(state="disabled")
        ttk.Label(body, text="下载后解压，运行包内 scripts/install-linux.sh，再重启 coindex。\n现有待办和设置会保留。",
                  style="Muted.TLabel", wraplength=590).pack(anchor="w", pady=(14, 0))
        self.error = tk.StringVar()
        tk.Label(body, textvariable=self.error, bg=app.BG, fg="#A34444", justify="left", wraplength=590).pack(fill="x", pady=(6, 0))
        self.download_button = ttk.Button(footer, text="下载更新" if self.has_download else "查看发布页", style="Accent.TButton", command=self.download)
        self.download_button.pack(side="right")
        if not self.has_download:
            self.error.set("此版本尚未提供 Linux 安装包，可以查看发布页。")
        self.skip_button = ttk.Button(footer, text="跳过此版本", command=self.skip)
        self.skip_button.pack(side="right", padx=8)
        ttk.Button(footer, text="稍后", style="Quiet.TButton", command=self.win.destroy).pack(side="right")

    def download(self):
        self.download_button.configure(state="disabled")
        def opened(response):
            if not self.win.winfo_exists():
                return
            self.download_button.configure(state="normal")
            if response.get("error"):
                self.error.set(str(response["error"]))
            else:
                self.error.set("已在浏览器中打开下载，安装完成后重启 coindex。" if self.has_download else "已在浏览器中打开发布页。")
        if self.app._rpc("open_update", opened, version=self.version) is None:
            self.download_button.configure(state="normal")
            self.error.set("无法打开下载，请检查本地服务状态。")

    def skip(self):
        self.skip_button.configure(state="disabled")
        def skipped(response):
            if response.get("error"):
                if self.win.winfo_exists():
                    self.skip_button.configure(state="normal")
                    self.error.set(str(response["error"]))
                return
            self.app._mutation_result(response)
            if self.win.winfo_exists():
                self.win.destroy()
        if self.app._rpc("skip_update", skipped, version=self.version) is None:
            self.skip_button.configure(state="normal")
            self.error.set("未能保存跳过设置，请重试。")
