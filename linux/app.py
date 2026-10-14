#!/usr/bin/env python3
"""Linux desktop interface for coindex's private stdio backend."""
from __future__ import annotations

import argparse
import copy
import json
import os
import pathlib
import queue
import subprocess
import sys
import tempfile
import threading
import time
import uuid
import tkinter as tk
from tkinter import messagebox, simpledialog, ttk

ROOT = pathlib.Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

try:
    from platform_paths import default_data_dir
except ImportError:  # Supports running this frontend from an older source checkout.
    def default_data_dir():
        return pathlib.Path.home() / ".local" / "share" / "coindex"


def demo_snapshot():
    now = time.time()
    rows = [
        ("review", "文档搜索功能验收", "搜索功能已提交；尚未做集成验证", "在测试环境验证完整搜索流程", "PR #123 已创建"),
        ("continue", "修复应用自动更新", "已定位版本比较错误；尚未改代码", "修改版本比较规则后验证升级流程", "复现步骤已记录"),
        ("wait", "降低图片上传等待时间", "两组基准测试已进入队列", "查询基准测试的运行状态", "任务已排队"),
    ]
    tasks, conversations = [], []
    for i, (kind, title, progress, action, evidence) in enumerate(rows):
        cid = "mac:demo-" + str(i)
        tasks.append({"id": "demo-task-" + str(i), "conversation_id": cid, "kind": kind, "title": title,
                      "detail": "演示数据仅用于浏览界面。", "progress": progress, "next_action": action,
                      "evidence": evidence, "artifact": "演示记录", "priority": i + 1, "status": "open",
                      "snoozed_until": 0, "host": "mac", "thread_id": "demo-" + str(i),
                      "conversation_title": ["文档检索功能", "自动更新排查", "上传性能测试"][i],
                      "cwd": "/workspace/example", "path": "/example/session.jsonl", "updated_at": now - i * 600})
        conversations.append({"id": cid, "host": "mac", "thread_id": "demo-" + str(i),
                              "title": tasks[-1]["conversation_title"], "cwd": "/workspace/example",
                              "path": "/example/session.jsonl", "updated_at": now - i * 600,
                              "summary": "演示对话", "closed": 0, "archived": 0, "active": False,
                              "execution_state": "idle"})
    return {"tasks": tasks, "conversations": conversations,
            "hosts": [{"id": "mac", "name": "本机 / Linux", "status": "online", "detail": "演示数据"}],
            "nudges": [], "settings": {"automatic": True, "interval_seconds": 1800, "idle_minutes": 10,
                "batch_size": 6, "history_days": 0, "enabled_hosts": ["mac"], "workdays_only": True,
                "work_hours_enabled": False, "work_start_minutes": 540, "work_end_minutes": 1080,
                "codex_home": "", "codex_cli": "", "codex_app": "", "remote_hosts": [],
                "analysis_model": "gpt-6-luna", "analysis_effort": "max", "connection_setup_complete": False},
            "schedule": {"due": False, "summary": "演示模式", "next_at": None},
            "sync": {"running": False, "phase": ""}, "model": "gpt-6-luna", "effort": "max",
            "pending_analysis": 0, "last_sync": now, "model_error": "", "now": now}


def load_demo_snapshot():
    """Load the packaged fixture, or generate an isolated source-tree fixture."""
    packaged = ROOT / "demo.json"
    if packaged.is_file():
        return json.loads(packaged.read_text(encoding="utf-8"))
    generator = ROOT / "scripts" / "create-demo.py"
    if generator.is_file():
        with tempfile.TemporaryDirectory(prefix="coindex-demo-") as temp:
            output = pathlib.Path(temp) / "demo.json"
            subprocess.run([sys.executable, str(generator), str(output)], check=True,
                           stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return json.loads(output.read_text(encoding="utf-8"))
    return demo_snapshot()


class StdioClient:
    """Line-oriented RPC client. All Tk calls stay on the main thread."""
    def __init__(self, command, on_message, on_exit=None, popen=subprocess.Popen):
        self.on_message = on_message
        self.on_exit = on_exit
        self.process = popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                             stderr=subprocess.DEVNULL, text=True, bufsize=1, start_new_session=True)
        self.lock = threading.Lock()
        self.messages = queue.Queue()
        self.pending = {}
        self.closed = False
        self.reader = threading.Thread(target=self._read, daemon=True)
        self.reader.start()

    def request(self, method, callback=None, **values):
        if self.closed or self.process.poll() is not None:
            raise RuntimeError("本地服务已关闭")
        request_id = str(uuid.uuid4())
        request = {"id": request_id, "method": method, **values}
        with self.lock:
            if callback:
                self.pending[request_id] = callback
            self.process.stdin.write(json.dumps(request, ensure_ascii=False) + "\n")
            self.process.stdin.flush()
        return request_id

    def _read(self):
        try:
            for line in self.process.stdout:
                try:
                    self.messages.put(json.loads(line))
                except (ValueError, TypeError):
                    self.messages.put({"error": "服务返回了无法识别的数据"})
        finally:
            self.messages.put({"_closed": True, "returncode": self.process.poll()})

    def drain(self):
        while True:
            try:
                msg = self.messages.get_nowait()
            except queue.Empty:
                break
            if msg.get("_closed"):
                if self.on_exit:
                    self.on_exit(msg.get("returncode"))
                continue
            callback = self.pending.pop(msg.get("id"), None)
            if callback:
                callback(msg)

    def close(self):
        if self.closed:
            return
        self.closed = True
        try:
            self.process.stdin.close()
        except (OSError, AttributeError):
            pass
        if self.process.poll() is None:
            self.process.terminate()


class CoindexApp:
    BG, SURFACE, SIDEBAR = "#F7F8FA", "#FFFFFF", "#EFF0F4"
    BORDER, INK, MUTED, ACCENT = "#E1E3EB", "#20212B", "#676A79", "#555FC9"

    def __init__(self, root, data_dir=None, demo=False, client_factory=StdioClient, demo_data=None, smoke_test=False):
        self.root, self.demo = root, demo
        self.snapshot = copy.deepcopy(demo_data) if demo_data is not None else (load_demo_snapshot() if demo else {})
        self.data_dir = pathlib.Path(data_dir or default_data_dir()).expanduser()
        self.client = None
        self.selected_task = None
        self.tab = "tasks"
        self.show_inactive = False
        self.request_inflight = False
        self.last_auto_sync = 0
        self.client_factory = client_factory
        self._build()
        if demo:
            self._render()
            self.status_var.set("演示模式 · 所有数据均为虚构，修改与连接操作已停用")
            if smoke_test:
                self.root.after(300, self._finish_smoke_test)
        else:
            self.client = self.client_factory([sys.executable, str(BACKEND / "service.py"), "--data-dir",
                                              str(self.data_dir), "serve"], self._incoming, self._service_exit)
            self.root.after(50, self._drain)
            self._rpc("snapshot", self._snapshot_result)

    @classmethod
    def from_args(cls, argv=None):
        parser = argparse.ArgumentParser(description="coindex Linux desktop task workspace")
        parser.add_argument("--data-dir", default=None, help="coindex data directory")
        parser.add_argument("--demo", action="store_true", help="show fictional sample data without starting the service")
        parser.add_argument("--smoke-test", action="store_true", help="render demo widgets and exit (requires --demo)")
        args = parser.parse_args(argv)
        if args.smoke_test and not args.demo:
            parser.error("--smoke-test requires --demo")
        root = tk.Tk()
        return cls(root, args.data_dir, args.demo, smoke_test=args.smoke_test)

    def _finish_smoke_test(self):
        try:
            if not self.snapshot.get("tasks") or not self.visible_task_ids:
                raise RuntimeError("demo task list did not render")
            self._select_task(self.visible_task_ids[0])
            if not self.detail.winfo_children():
                raise RuntimeError("task detail pane did not render")
            self.root.quit()
        except Exception as exc:
            self.smoke_error = str(exc)
            self.root.quit()

    def _build(self):
        self.root.title("coindex")
        self.root.geometry("1200x820")
        self.root.minsize(960, 660)
        self.root.configure(bg=self.BG)
        style = ttk.Style(self.root)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure("TFrame", background=self.BG)
        style.configure("Panel.TFrame", background=self.SURFACE)
        style.configure("TLabel", background=self.BG, foreground=self.INK, font=("Sans", 10))
        style.configure("Muted.TLabel", foreground=self.MUTED)
        style.configure("Title.TLabel", font=("Sans", 21, "bold"))
        style.configure("Task.TLabel", background=self.SURFACE, font=("Sans", 12, "bold"))
        style.configure("TButton", padding=(9, 5))
        style.configure("Accent.TButton", background=self.ACCENT, foreground="#FFFFFF")
        style.map("Accent.TButton", background=[("active", "#464FB5")])
        style.configure("TEntry", padding=6)
        self.root.protocol("WM_DELETE_WINDOW", self.close)

        shell = ttk.Frame(self.root)
        shell.pack(fill="both", expand=True)
        sidebar = tk.Frame(shell, bg=self.SIDEBAR, width=220, highlightthickness=1, highlightbackground=self.BORDER)
        sidebar.pack(side="left", fill="y")
        sidebar.pack_propagate(False)
        tk.Label(sidebar, text="coindex", bg=self.SIDEBAR, fg=self.INK, font=("Sans", 19, "bold")).pack(anchor="w", padx=20, pady=(22, 26))
        self.nav_tasks = ttk.Button(sidebar, text="▣  待办", command=lambda: self._switch("tasks"))
        self.nav_tasks.pack(fill="x", padx=12, pady=3)
        self.nav_convs = ttk.Button(sidebar, text="◷  对话", command=lambda: self._switch("conversations"))
        self.nav_convs.pack(fill="x", padx=12, pady=3)
        ttk.Button(sidebar, text="⚙  设置", command=self.open_settings).pack(fill="x", padx=12, pady=(3, 3))
        self.sidebar_status = tk.Label(sidebar, text="服务连接中…", bg=self.SIDEBAR, fg=self.MUTED,
                                       justify="left", wraplength=185, font=("Sans", 9))
        self.sidebar_status.pack(side="bottom", anchor="w", padx=18, pady=18)

        content = ttk.Frame(shell, padding=(24, 20, 24, 18))
        content.pack(side="left", fill="both", expand=True)
        header = ttk.Frame(content)
        header.pack(fill="x", pady=(0, 16))
        self.heading_var = tk.StringVar(value="待办")
        ttk.Label(header, textvariable=self.heading_var, style="Title.TLabel").pack(side="left")
        self.status_var = tk.StringVar(value="")
        ttk.Label(header, textvariable=self.status_var, style="Muted.TLabel").pack(side="left", padx=16, pady=(7, 0))
        self.primary_button = ttk.Button(header, text="＋ 新建待办", style="Accent.TButton", command=self.new_task)
        self.primary_button.pack(side="right")
        self.update_button = ttk.Button(header, text="更新", command=self.manual_sync)
        self.update_button.pack(side="right", padx=(0, 8))

        self.task_filters = ttk.Frame(content)
        self.task_filters.pack(fill="x", pady=(0, 10))
        self.search_var = tk.StringVar()
        search = ttk.Entry(self.task_filters, textvariable=self.search_var, width=28)
        search.pack(side="left", fill="x", expand=True, padx=(0, 8))
        search.insert(0, "")
        self.search_var.trace_add("write", lambda *_: self._render_tasks())
        self.kind_var = tk.StringVar(value="全部类型")
        self.kind_box = ttk.Combobox(self.task_filters, textvariable=self.kind_var, values=("全部类型", "目标", "继续", "等待", "决策", "手动"), state="readonly", width=11)
        self.kind_box.pack(side="left", padx=4)
        self.kind_box.bind("<<ComboboxSelected>>", lambda _e: self._render_tasks())
        self.host_var = tk.StringVar(value="全部来源")
        self.host_box = ttk.Combobox(self.task_filters, textvariable=self.host_var, values=("全部来源",), state="readonly", width=14)
        self.host_box.pack(side="left", padx=4)
        self.host_box.bind("<<ComboboxSelected>>", lambda _e: self._render_tasks())
        self.inactive_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(self.task_filters, text="已完成 / 稍后", variable=self.inactive_var, command=self._toggle_inactive).pack(side="left", padx=(8, 0))

        self.task_page = ttk.Frame(content)
        self.conversation_page = ttk.Frame(content)
        self.task_page.pack(fill="both", expand=True)
        task_split = ttk.Frame(self.task_page)
        task_split.pack(fill="both", expand=True)
        list_frame = tk.Frame(task_split, bg=self.BG)
        list_frame.pack(side="left", fill="both", expand=True)
        self.canvas = tk.Canvas(list_frame, bg=self.BG, highlightthickness=0)
        self.task_scroll = ttk.Scrollbar(list_frame, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=self.task_scroll.set)
        self.task_scroll.pack(side="right", fill="y")
        self.canvas.pack(side="left", fill="both", expand=True)
        self.cards = tk.Frame(self.canvas, bg=self.BG)
        self.cards_window = self.canvas.create_window((0, 0), window=self.cards, anchor="nw")
        self.cards.bind("<Configure>", lambda _e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.canvas.bind("<Configure>", lambda e: self.canvas.itemconfigure(self.cards_window, width=e.width))
        self.canvas.bind_all("<MouseWheel>", self._wheel)
        self.detail = tk.Frame(task_split, bg=self.SURFACE, width=360, highlightthickness=1, highlightbackground=self.BORDER)
        self.detail.pack(side="right", fill="y", padx=(14, 0))
        self.detail.pack_propagate(False)
        self._clear_detail()

        self.conversation_page.pack_forget()
        self.conversations = ttk.Treeview(self.conversation_page, columns=("host", "state", "updated"), show="tree headings", selectmode="browse")
        self.conversations.heading("#0", text="对话")
        self.conversations.heading("host", text="来源")
        self.conversations.heading("state", text="状态")
        self.conversations.heading("updated", text="最近更新")
        self.conversations.column("#0", width=500)
        self.conversations.column("host", width=140)
        self.conversations.column("state", width=120)
        self.conversations.column("updated", width=160)
        conv_list = ttk.Frame(self.conversation_page)
        conv_list.pack(fill="both", expand=True, pady=(0, 10))
        self.conversations.pack(in_=conv_list, side="left", fill="both", expand=True)
        conv_scroll = ttk.Scrollbar(conv_list, orient="vertical", command=self.conversations.yview)
        conv_scroll.pack(side="right", fill="y")
        self.conversations.configure(yscrollcommand=conv_scroll.set)
        self.conv_inactive_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(self.conversation_page, text="显示已结束对话", variable=self.conv_inactive_var,
                        command=self._toggle_conversations).pack(anchor="w", pady=(0, 8))
        actions = ttk.Frame(self.conversation_page)
        actions.pack(fill="x")
        self.open_conv_button = ttk.Button(actions, text="打开对话", command=self.open_conversation)
        self.open_conv_button.pack(side="left")
        self.close_conv_button = ttk.Button(actions, text="结束对话", command=self.toggle_conversation)
        self.close_conv_button.pack(side="left", padx=8)
        self._disable_mutations()

    def _disable_mutations(self):
        if self.demo:
            for widget in (self.primary_button, self.update_button, self.open_conv_button, self.close_conv_button):
                widget.configure(state="disabled")

    def _rpc(self, method, callback=None, **kwargs):
        if not self.client:
            return None
        try:
            return self.client.request(method, callback, **kwargs)
        except Exception as exc:
            self._error(str(exc))
            return None

    def _incoming(self, _message):
        # Compatibility hook for injected clients; StdioClient queues messages itself.
        pass

    def _drain(self):
        if self.client:
            self.client.drain()
            if self.client.process.poll() is None:
                self.root.after(50, self._drain)

    def _service_exit(self, code):
        if not self.client or self.client.closed:
            return
        self.sidebar_status.configure(text="本地服务已退出" + ("" if code in (None, 0) else "（错误 %s）" % code), fg="#A34444")

    def _snapshot_result(self, response):
        if response.get("error"):
            self._error(response["error"])
            return
        self.snapshot = response.get("result", {})
        self._render()
        self._maybe_auto_sync()
        if self.client and not self.client.closed:
            self.root.after(2500, lambda: self._rpc("snapshot", self._snapshot_result))

    def _maybe_auto_sync(self):
        settings = self.snapshot.get("settings", {})
        schedule = self.snapshot.get("schedule", {})
        if (settings.get("automatic") and settings.get("connection_setup_complete") and schedule.get("due")
                and not self.snapshot.get("sync", {}).get("running") and not self.request_inflight
                and time.monotonic() - self.last_auto_sync > 30):
            self.last_auto_sync = time.monotonic()
            self._rpc("sync", lambda _r: None, automatic=True)

    def _render(self):
        settings = self.snapshot.get("settings", {})
        schedule = self.snapshot.get("schedule", {})
        sync = self.snapshot.get("sync", {})
        self.status_var.set(sync.get("phase") or schedule.get("summary", ""))
        self.sidebar_status.configure(text="演示模式" if self.demo else "自动更新已开启" if settings.get("automatic") else "自动更新已暂停")
        names = {h["id"]: ("本机 / Linux" if h["id"] == "mac" else h.get("name") or h["id"])
                 for h in self.snapshot.get("hosts", [])}
        names["manual"] = "手动"
        hosts = ["全部来源"] + list(dict.fromkeys(names.get(t.get("host"), t.get("host", "")) for t in self.snapshot.get("tasks", [])))
        self.host_values = {label: key for key, label in names.items()}
        current = self.host_var.get()
        self.host_box.configure(values=hosts)
        if current not in hosts:
            self.host_var.set("全部来源")
        self._render_tasks()
        self._render_conversations()

    def _kind_label(self, kind):
        return {"review": "目标", "continue": "继续", "wait": "等待", "decision": "决策", "manual": "手动", "running": "进行中"}.get(kind, kind or "任务")

    def _render_tasks(self):
        if not hasattr(self, "cards"):
            return
        for child in self.cards.winfo_children():
            child.destroy()
        tasks = self.snapshot.get("tasks", [])
        search = self.search_var.get().strip().lower()
        chosen_kind = self.kind_var.get()
        chosen_host = self.host_var.get()
        by_id = {t["id"]: t for t in tasks}
        rows = []
        now = time.time()
        for task in tasks:
            status = task.get("status", "open")
            inactive = status in ("done", "dismissed") or task.get("snoozed_until", 0) > now
            if inactive != self.show_inactive:
                continue
            if search and search not in " ".join(str(task.get(k, "")) for k in ("title", "detail", "progress", "evidence", "next_action", "conversation_title")).lower():
                continue
            if chosen_kind != "全部类型" and self._kind_label(task.get("kind")) != chosen_kind:
                continue
            if chosen_host != "全部来源" and self.host_values.get(chosen_host, chosen_host) != task.get("host"):
                continue
            rows.append(task)
        self.visible_task_ids = [t["id"] for t in rows]
        self.selected_task = self.selected_task if self.selected_task in by_id else None
        self.result_count = len(rows)
        for task in rows:
            self._task_card(task, selected=task["id"] == self.selected_task)
        if not rows:
            tk.Label(self.cards, text="没有匹配的待办", bg=self.BG, fg=self.MUTED, font=("Sans", 13)).pack(anchor="w", padx=18, pady=28)
        if self.selected_task:
            self._show_detail(by_id[self.selected_task])
        else:
            self._clear_detail()

    def _task_card(self, task, selected=False):
        frame = tk.Frame(self.cards, bg=self.SURFACE, highlightthickness=2 if selected else 1,
                         highlightbackground=self.ACCENT if selected else self.BORDER, padx=14, pady=12)
        frame.pack(fill="x", pady=(0, 10), padx=(1, 7))
        title = tk.Label(frame, text=task.get("title", "未命名待办"), bg=self.SURFACE, fg=self.INK,
                         font=("Sans", 12, "bold"), anchor="w", justify="left", wraplength=430)
        title.pack(fill="x")
        meta = "%s · %s" % (self._kind_label(task.get("kind")), "本机 / Linux" if task.get("host") == "mac" else task.get("host", ""))
        tk.Label(frame, text=meta, bg=self.SURFACE, fg=self.MUTED, font=("Sans", 9), anchor="w").pack(fill="x", pady=(3, 7))
        tk.Label(frame, text=task.get("progress") or task.get("detail") or "暂无进展记录", bg="#F2F3F7", fg=self.INK,
                 font=("Sans", 10), anchor="w", justify="left", wraplength=430, padx=9, pady=7).pack(fill="x")
        tk.Label(frame, text="下一步  " + (task.get("next_action") or "尚未记录"), bg=self.SURFACE, fg=self.MUTED,
                 font=("Sans", 9), anchor="w", justify="left", wraplength=430).pack(fill="x", pady=(7, 0))
        for widget in (frame, title):
            widget.bind("<Button-1>", lambda _e, tid=task["id"]: self._select_task(tid))
            widget.bind("<Enter>", lambda _e, f=frame: f.configure(highlightbackground=self.ACCENT))
            widget.bind("<Leave>", lambda _e, f=frame, sel=selected: f.configure(highlightbackground=self.ACCENT if sel else self.BORDER))
        for child in frame.winfo_children():
            if isinstance(child, tk.Label):
                child.bind("<Button-1>", lambda _e, tid=task["id"]: self._select_task(tid))

    def _select_task(self, task_id):
        self.selected_task = task_id
        self._render_tasks()

    def _clear_detail(self):
        if not hasattr(self, "detail"):
            return
        for child in self.detail.winfo_children():
            child.destroy()
        tk.Label(self.detail, text="选择一条待办查看详情", bg=self.SURFACE, fg=self.MUTED,
                 font=("Sans", 11)).pack(padx=20, pady=30)

    def _show_detail(self, task):
        for child in self.detail.winfo_children():
            child.destroy()
        pane = tk.Frame(self.detail, bg=self.SURFACE)
        pane.pack(fill="both", expand=True, padx=18, pady=18)
        title = tk.Label(pane, text=task.get("title", ""), bg=self.SURFACE, fg=self.INK, font=("Sans", 15, "bold"),
                         anchor="w", justify="left", wraplength=300)
        title.pack(fill="x")
        self._section(pane, "进展 / 停止点", task.get("progress") or task.get("detail") or "暂无记录")
        self._section(pane, "下一步", task.get("next_action") or "尚未记录")
        self._section(pane, "依据", task.get("evidence") or "暂无依据")
        self._section(pane, "产物", task.get("artifact") or "暂无产物")
        meta = "%s\n%s" % ("本机 / Linux" if task.get("host") == "mac" else task.get("host", ""), task.get("conversation_title") or "手动待办")
        self._section(pane, "来源", meta)
        detail_buttons = []
        for label, fn in (("打开对话", self.open_conversation), ("改标题", lambda: self.rename_task(task)),
                          ("编辑", lambda: self.edit_task(task))):
            if label == "打开对话" and task.get("kind") == "manual":
                continue
            button = ttk.Button(pane, text=label, command=fn)
            button.pack(fill="x", pady=(7, 0))
            detail_buttons.append(button)
        status = task.get("status")
        if not self.demo:
            status_buttons = []
            if status in ("done", "dismissed") or task.get("snoozed_until", 0) > time.time():
                status_buttons.append(ttk.Button(pane, text="重新打开", command=lambda: self._act("reopen", task)))
            else:
                status_buttons.append(ttk.Button(pane, text="完成", style="Accent.TButton", command=lambda: self._act("complete", task)))
                status_buttons.append(ttk.Button(pane, text="稍后提醒…", command=lambda: self._snooze(task)))
                status_buttons.append(ttk.Button(pane, text="忽略", command=lambda: self._act("dismiss", task)))
                if task.get("kind") != "manual":
                    status_buttons.append(ttk.Button(pane, text="轻推原对话…", command=lambda: self._nudge(task)))
            detail_buttons.extend(status_buttons)
            for button in status_buttons:
                button.pack(fill="x", pady=(7, 0))
        if self.demo:
            for button in detail_buttons:
                button.configure(state="disabled")

    def _section(self, parent, heading, text):
        tk.Label(parent, text=heading, bg=self.SURFACE, fg=self.MUTED, font=("Sans", 9, "bold"), anchor="w").pack(fill="x", pady=(13, 3))
        tk.Label(parent, text=text, bg=self.SURFACE, fg=self.INK, font=("Sans", 10), anchor="w", justify="left", wraplength=305).pack(fill="x")

    def _act(self, action, task):
        self._rpc("act", self._mutation_result, action=action, entity_id=task["id"])

    def _mutation_result(self, response):
        self.request_inflight = False
        if response.get("error"):
            self._error(response["error"])
        elif "snapshot" in response.get("result", {}):
            self.snapshot = response["result"]["snapshot"]
            self._render()
        elif isinstance(response.get("result"), dict):
            self.snapshot = response["result"]
            self._render()

    def _snooze(self, task):
        minutes = simpledialog.askinteger("稍后提醒", "多少分钟后重新显示？（1–10080）", parent=self.root, initialvalue=60, minvalue=1, maxvalue=10080)
        if minutes is not None:
            self._rpc("act", self._mutation_result, action="snooze", entity_id=task["id"], value=minutes)

    def _nudge(self, task, retry_unknown=False):
        existing = [n for n in self.snapshot.get("nudges", [])
                    if n.get("conversation_id") == task.get("conversation_id") and n.get("status") == "unknown"]
        if (existing or retry_unknown) and not messagebox.askyesno(
                "确认送达情况", "请先检查原 Codex 对话，确认上次没有收到催办。现在继续重试吗？", parent=self.root):
            return
        if existing:
            retry_unknown = True
        action_id = str(uuid.uuid4())
        self._rpc("nudge", self._mutation_result, entity_id=task["id"], action_id=action_id, retry_unknown=retry_unknown)

    def new_task(self):
        if self.demo:
            return
        self._task_dialog()

    def edit_task(self, task):
        if task.get("kind") == "manual" and not self.demo:
            self._task_dialog(task)

    def rename_task(self, task):
        title = simpledialog.askstring("改标题", "待办标题", initialvalue=task.get("title", ""), parent=self.root)
        if title and title.strip():
            self._rpc("rename_task", self._mutation_result, entity_id=task["id"], title=title.strip())

    def _task_dialog(self, task=None):
        win = tk.Toplevel(self.root)
        win.title("编辑待办" if task else "新建待办")
        win.transient(self.root)
        win.grab_set()
        win.configure(bg=self.BG)
        box = ttk.Frame(win, padding=18)
        box.pack(fill="both", expand=True)
        ttk.Label(box, text="标题").pack(anchor="w")
        title = ttk.Entry(box, width=54)
        title.pack(fill="x", pady=(4, 12))
        title.insert(0, task.get("title", "") if task else "")
        ttk.Label(box, text="备注").pack(anchor="w")
        detail = tk.Text(box, width=54, height=7, wrap="word", relief="solid", bd=1)
        detail.pack(fill="both", expand=True, pady=(4, 12))
        if task:
            detail.insert("1.0", task.get("detail", ""))
        ttk.Label(box, text="优先级").pack(anchor="w")
        priority = tk.IntVar(value=task.get("priority", 2) if task else 2)
        row = ttk.Frame(box)
        row.pack(anchor="w", pady=4)
        for value, label in ((1, "高"), (2, "普通"), (3, "低")):
            ttk.Radiobutton(row, text=label, value=value, variable=priority).pack(side="left", padx=(0, 8))
        def save():
            values = {"title": title.get().strip(), "detail": detail.get("1.0", "end-1c"), "priority": priority.get()}
            if not values["title"]:
                messagebox.showerror("需要标题", "请填写待办标题。", parent=win)
                return
            if task:
                values["entity_id"] = task["id"]
            self._rpc("save_manual", lambda response: (win.destroy(), self._mutation_result(response)), **values)
        ttk.Button(box, text="保存", style="Accent.TButton", command=save).pack(anchor="e")
        title.focus_set()

    def _switch(self, name):
        self.tab = name
        self.heading_var.set("待办" if name == "tasks" else "对话")
        if name == "tasks":
            self.conversation_page.pack_forget()
            self.task_filters.pack(fill="x", pady=(0, 10))
            self.task_page.pack(fill="both", expand=True)
            self.primary_button.configure(text="＋ 新建待办", command=self.new_task)
            self._render_tasks()
        else:
            self.task_page.pack_forget()
            self.task_filters.pack_forget()
            self.conversation_page.pack(fill="both", expand=True)
            self.primary_button.configure(text="", command=lambda: None)
            self._render_conversations()

    def _render_conversations(self):
        if not hasattr(self, "conversations"):
            return
        self.conversations.delete(*self.conversations.get_children())
        self.conv_map = {}
        for conv in self.snapshot.get("conversations", []):
            if bool(conv.get("closed")) != self.conv_inactive_var.get():
                continue
            title = conv.get("title") or "未命名对话"
            host = "本机 / Linux" if conv.get("host") == "mac" else conv.get("host", "")
            state = "已结束" if conv.get("closed") else conv.get("execution_state", "")
            item = self.conversations.insert("", "end", text=title, values=(host, state, self._age(conv.get("updated_at", 0))), iid=conv["id"])
            self.conv_map[item] = conv
        self.close_conv_button.configure(text="恢复对话" if self.conv_inactive_var.get() else "结束对话")

    def _toggle_conversations(self):
        self._render_conversations()

    def _age(self, timestamp):
        if not timestamp:
            return ""
        return time.strftime("%m-%d %H:%M", time.localtime(timestamp))

    def _selected_conversation(self):
        selection = self.conversations.selection()
        return self.conv_map.get(selection[0]) if selection else None

    def toggle_conversation(self):
        conv = self._selected_conversation()
        if conv and not self.demo:
            action = "reopen_conversation" if conv.get("closed") else "close_conversation"
            self._rpc("act", self._mutation_result, action=action, entity_id=conv["id"])

    def open_conversation(self):
        if self.tab == "conversations":
            conv = self._selected_conversation()
            if not conv:
                return
            entity = conv["id"]
        else:
            task = next((x for x in self.snapshot.get("tasks", []) if x["id"] == self.selected_task), None)
            if not task or task.get("kind") == "manual":
                return
            entity = task["id"]
        if not self.demo:
            self._rpc("open_thread", self._action_result, entity_id=entity)

    def _action_result(self, response):
        if response.get("error"):
            self._error(response["error"])
        else:
            result = response.get("result", {})
            self.status_var.set(result.get("detail", "已打开对话"))

    def _toggle_inactive(self):
        self.show_inactive = self.inactive_var.get()
        self._render_tasks()
        self._render_conversations()

    def _wheel(self, event):
        if self.tab == "tasks":
            self.canvas.yview_scroll(int(-event.delta / 120), "units")

    def manual_sync(self):
        if self.demo:
            return
        self.request_inflight = True
        self._rpc("sync", lambda r: (setattr(self, "request_inflight", False), self._action_result(r)), automatic=False)

    def open_settings(self):
        if self.demo:
            return
        SettingsDialog(self)

    def _settings_saved(self, values):
        self._rpc("settings", self._mutation_result, values=values)

    def _error(self, text):
        self.status_var.set(str(text)[:160])

    def close(self):
        if self.client:
            self.client.close()
        self.root.destroy()


class SettingsDialog:
    def __init__(self, app):
        self.app = app
        self.saved = copy.deepcopy(app.snapshot.get("settings", {}))
        self.win = tk.Toplevel(app.root)
        self.win.title("设置")
        self.win.geometry("690x690")
        self.win.transient(app.root)
        body = ttk.Frame(self.win, padding=18)
        body.pack(fill="both", expand=True)
        self.canvas = tk.Canvas(body, highlightthickness=0, bg=app.BG)
        scroll = ttk.Scrollbar(body, orient="vertical", command=self.canvas.yview)
        self.form = ttk.Frame(self.canvas)
        self.canvas.create_window((0, 0), window=self.form, anchor="nw", tags="form")
        self.form.bind("<Configure>", lambda _e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.canvas.bind("<Configure>", lambda e: self.canvas.itemconfigure("form", width=e.width))
        self.canvas.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")
        self.vars = {}
        self._header("本机 Codex")
        self._entry("codex_home", "Codex 数据目录", self.saved.get("codex_home", ""))
        self._entry("codex_cli", "Codex CLI 路径（留空自动查找）", self.saved.get("codex_cli", ""))
        self._entry("codex_app", "Codex 应用路径（可选）", self.saved.get("codex_app", ""))
        ttk.Button(self.form, text="测试本机连接", command=self._test_local).pack(anchor="w", pady=(5, 10))
        self._header("分析模型")
        self._entry("analysis_model", "模型名称", self.saved.get("analysis_model", "gpt-6-luna"))
        effort = tk.StringVar(value=self.saved.get("analysis_effort", "max"))
        self.vars["analysis_effort"] = effort
        self._choice("推理强度", effort, ("minimal", "low", "medium", "high", "xhigh", "max", "ultra"))
        self._header("自动检测")
        self._check("automatic", "启用自动更新", self.saved.get("automatic", True))
        self._check("workdays_only", "仅工作日运行", self.saved.get("workdays_only", True))
        self._check("work_hours_enabled", "限定工作时段", self.saved.get("work_hours_enabled", False))
        self._entry("interval_seconds", "检测间隔（秒，30–3600）", self.saved.get("interval_seconds", 1800))
        self._entry("work_start_minutes", "开始时间（当天分钟数，例如 540 = 09:00）", self.saved.get("work_start_minutes", 540))
        self._entry("work_end_minutes", "结束时间（当天分钟数，例如 1080 = 18:00）", self.saved.get("work_end_minutes", 1080))
        self._header("SSH 来源")
        self._check("local_enabled", "启用本机来源", "mac" in self.saved.get("enabled_hosts", ["mac"]))
        self.host_list = ttk.Frame(self.form)
        self.host_list.pack(fill="x")
        self._render_hosts()
        ttk.Button(self.form, text="＋ 添加 SSH 来源", command=lambda: RemoteDialog(self)).pack(anchor="w", pady=6)
        foot = ttk.Frame(self.win, padding=(18, 6, 18, 14))
        foot.pack(fill="x")
        ttk.Button(foot, text="保存设置", style="Accent.TButton", command=self._save).pack(side="right")
        self._connection_succeeded = False

    def _header(self, text):
        ttk.Label(self.form, text=text, font=("Sans", 12, "bold")).pack(anchor="w", pady=(14, 7))

    def _entry(self, key, label, value):
        ttk.Label(self.form, text=label).pack(anchor="w", pady=(5, 2))
        var = tk.StringVar(value=str(value))
        self.vars[key] = var
        ttk.Entry(self.form, textvariable=var).pack(fill="x")

    def _check(self, key, label, value):
        var = tk.BooleanVar(value=bool(value))
        self.vars[key] = var
        ttk.Checkbutton(self.form, text=label, variable=var).pack(anchor="w", pady=2)

    def _choice(self, label, var, values):
        ttk.Label(self.form, text=label).pack(anchor="w")
        ttk.Combobox(self.form, textvariable=var, values=values, state="readonly").pack(anchor="w", pady=3)

    def _render_hosts(self):
        for child in self.host_list.winfo_children():
            child.destroy()
        for profile in self.saved.get("remote_hosts", []):
            row = ttk.Frame(self.host_list)
            row.pack(fill="x", pady=2)
            enabled = self.vars.get("host:" + profile["id"])
            if enabled is None:
                enabled = tk.BooleanVar(value=profile["id"] in self.saved.get("enabled_hosts", []))
                self.vars["host:" + profile["id"]] = enabled
            ttk.Checkbutton(row, text="启用", variable=enabled).pack(side="left")
            ttk.Label(row, text="%s · %s" % (profile.get("name", profile["id"]), profile.get("hostname", profile["id"]))).pack(side="left", fill="x", expand=True)
            ttk.Button(row, text="测试", command=lambda p=profile: self._test_remote(p)).pack(side="right", padx=2)
            ttk.Button(row, text="编辑", command=lambda p=profile: RemoteDialog(self, p)).pack(side="right", padx=2)
            ttk.Button(row, text="移除", command=lambda p=profile: self._remove(p)).pack(side="right", padx=2)

    def _remove(self, profile):
        if messagebox.askyesno("移除 SSH 来源", "移除 %s？现有历史记录会保留。" % profile.get("name", profile["id"]), parent=self.win):
            self.saved["remote_hosts"] = [x for x in self.saved.get("remote_hosts", []) if x["id"] != profile["id"]]
            self.saved["enabled_hosts"] = [x for x in self.saved.get("enabled_hosts", []) if x != profile["id"]]
            self._render_hosts()

    def _test_local(self):
        try:
            values = self._values()
        except ValueError as exc:
            messagebox.showerror("设置无效", str(exc), parent=self.win)
            return
        # The service checks its persisted connection settings. Save the edited paths
        # first, while keeping setup incomplete until the check itself succeeds.
        values.pop("connection_setup_complete", None)
        self.app._rpc("settings", lambda r: self._after_local_settings(r), values=values)

    def _after_local_settings(self, response):
        if response.get("error"):
            messagebox.showerror("连接设置失败", response["error"], parent=self.win)
            return
        self.app.snapshot = response.get("result", self.app.snapshot)
        self.app._rpc("check_connection", lambda r: self._checked(r, local=True))

    def _test_remote(self, profile):
        self.app._rpc("check_connection", lambda r: self._checked(r, local=False), profile=profile)

    def _checked(self, response, local):
        if response.get("error"):
            messagebox.showerror("连接测试失败", response["error"], parent=self.win)
            return
        result = response.get("result", {})
        if result.get("ok"):
            self._connection_succeeded = True
            self.saved["connection_setup_complete"] = True
            messagebox.showinfo("连接可用", result.get("detail", "连接测试通过。"), parent=self.win)
        else:
            messagebox.showerror("连接测试失败", result.get("detail", "连接检查未通过。"), parent=self.win)

    def _values(self):
        values = {}
        for key, var in self.vars.items():
            if key.startswith("host:"):
                continue
            value = var.get()
            if key in ("interval_seconds", "work_start_minutes", "work_end_minutes"):
                try:
                    value = int(value)
                except (ValueError, TypeError):
                    raise ValueError("检测间隔和时间请填写整数")
            values[key] = value
        remotes = copy.deepcopy(self.saved.get("remote_hosts", []))
        enabled = ["mac"] if self.vars.get("local_enabled", tk.BooleanVar(value=True)).get() else []
        for item in remotes:
            var = self.vars.get("host:" + item["id"])
            if var and var.get():
                enabled.append(item["id"])
        values["remote_hosts"] = remotes
        values["enabled_hosts"] = enabled
        if self._connection_succeeded:
            values["connection_setup_complete"] = True
        return values

    def _save(self):
        try:
            values = self._values()
        except ValueError as exc:
            messagebox.showerror("设置无效", str(exc), parent=self.win)
            return
        self.app._settings_saved(values)
        self.win.destroy()


class RemoteDialog:
    FIELDS = (("id", "连接标识（如 build-server）"), ("name", "显示名称"), ("hostname", "主机名或 IP"),
              ("user", "SSH 用户"), ("port", "SSH 端口（可留空）"), ("identity_file", "私钥路径（可留空）"),
              ("codex_home", "远程 Codex 数据目录（可留空）"), ("python", "远程 Python（可留空）"),
              ("host_id", "Codex 主机 ID（可选）"))

    def __init__(self, settings_dialog, profile=None):
        self.settings = settings_dialog
        self.profile = profile
        self.win = tk.Toplevel(settings_dialog.win)
        self.win.title("编辑 SSH 来源" if profile else "添加 SSH 来源")
        box = ttk.Frame(self.win, padding=16)
        box.pack(fill="both", expand=True)
        self.vars = {}
        for key, label in self.FIELDS:
            ttk.Label(box, text=label).pack(anchor="w", pady=(5, 2))
            var = tk.StringVar(value=str((profile or {}).get(key, "")))
            self.vars[key] = var
            ttk.Entry(box, textvariable=var, width=54).pack(fill="x")
        ttk.Button(box, text="保存连接", command=self._save).pack(anchor="e", pady=(12, 0))

    def _save(self):
        profile = {key: var.get().strip() for key, var in self.vars.items()}
        try:
            import connections
            profile = connections.normalize_remote(profile)
            old_id = self.profile.get("id") if self.profile else None
            remotes = [x for x in self.settings.saved.get("remote_hosts", []) if x["id"] != old_id and x["id"] != profile["id"]]
            remotes.append(profile)
            self.settings.saved["remote_hosts"] = remotes
            self.settings.saved["enabled_hosts"] = list(dict.fromkeys(self.settings.saved.get("enabled_hosts", []) + [profile["id"]]))
            self.settings.vars["host:" + profile["id"]] = tk.BooleanVar(master=self.settings.win, value=True)
            self.settings._render_hosts()
            self.destroy()
        except Exception as exc:
            messagebox.showerror("连接设置无效", str(exc), parent=self.win)

    def destroy(self):
        self.win.destroy()


def main(argv=None):
    app = CoindexApp.from_args(argv)
    app.root.mainloop()
    if getattr(app, "smoke_error", ""):
        print(app.smoke_error, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    main()
