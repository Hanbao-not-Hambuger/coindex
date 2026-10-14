"""GUI regressions for snapshot refreshes, using fictional in-memory data only."""
import copy
import pathlib
import sys
import time
import unittest

try:
    import tkinter as tk
except ImportError:
    tk = None

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from linux.app import CoindexApp, demo_snapshot


def expanded_demo_snapshot(task_count=42, conversation_count=42):
    """Build a large synthetic snapshot without touching a user's sessions."""
    source = demo_snapshot()
    task_template = source["tasks"][0]
    conv_template = source["conversations"][0]
    tasks, conversations = [], []
    now = time.time()
    for index in range(max(task_count, conversation_count)):
        conv_id = "fictional:refresh-%03d" % index
        title = "虚构待办 %03d" % index
        if index < task_count:
            task = copy.deepcopy(task_template)
            task.update(id="fictional-task-%03d" % index, conversation_id=conv_id,
                        title=title, conversation_title="虚构对话 %03d" % index,
                        detail="纯虚构的详情。", progress="虚构进度 %03d" % index,
                        next_action="检查虚构事项 %03d" % index,
                        evidence=("虚构证据 %03d。 " % index) * 180,
                        updated_at=now - index * 10, status="open", snoozed_until=0,
                        kind="review")
            tasks.append(task)
        if index < conversation_count:
            conv = copy.deepcopy(conv_template)
            conv.update(id=conv_id, thread_id="fictional-thread-%03d" % index,
                        title="虚构对话 %03d" % index,
                        summary="只用于界面回归测试。", path="/fictional/session-%03d.jsonl" % index,
                        updated_at=now - index * 10, closed=0, archived=0, active=False,
                        execution_state="idle")
            conversations.append(conv)
    result = copy.deepcopy(source)
    result.update(tasks=tasks, conversations=conversations, nudges=[])
    return result


class SnapshotRefreshTests(unittest.TestCase):
    def setUp(self):
        if tk is None:
            self.skipTest("Tkinter is unavailable")
        try:
            self.root = tk.Tk()
        except tk.TclError as error:
            self.skipTest("Tk display unavailable: %s" % error)
        self.root.geometry("1240x820")
        self.root.deiconify()
        self.app = CoindexApp(self.root, demo=True, demo_data=expanded_demo_snapshot())
        self.root.update()

    def tearDown(self):
        if getattr(self, "root", None):
            try:
                self.app.close()
            except tk.TclError:
                pass

    def refresh(self, snapshot):
        self.app.snapshot = snapshot
        self.app._render()
        self.root.update()

    @staticmethod
    def descendants(widget):
        found = []
        for child in widget.winfo_children():
            found.append(child)
            found.extend(SnapshotRefreshTests.descendants(child))
        return found

    def card_for_title(self, title):
        for card in self.app.cards.winfo_children():
            if any(isinstance(widget, tk.Label) and widget.cget("text") == title
                   for widget in self.descendants(card)):
                return card
        self.fail("no task card rendered for %r" % title)

    def detail_label(self, text):
        return next((widget for widget in self.descendants(self.app.detail_content)
                     if isinstance(widget, tk.Label) and widget.cget("text") == text), None)

    def test_unchanged_content_refresh_preserves_widgets_selection_focus_and_scroll(self):
        self.app._select_task("fictional-task-008")
        self.root.update_idletasks()
        selected_card = self.card_for_title("虚构待办 008")
        detail_title = self.detail_label("虚构待办 008")
        self.assertIsNotNone(detail_title)
        self.app.canvas.yview_moveto(.32)
        self.app.detail_canvas.yview_moveto(.55)
        self.app.detail_canvas.focus_set()
        self.root.update()
        task_y = self.app.canvas.yview()
        detail_y = self.app.detail_canvas.yview()
        focused = self.root.focus_get()
        self.assertIs(focused, self.app.detail_canvas)

        updated = copy.deepcopy(self.app.snapshot)
        updated["now"] = updated["now"] + 90
        updated["last_sync"] = updated["last_sync"] + 90
        updated["schedule"].update(summary="虚构的新计划状态", next_at=time.time() + 90)
        updated["sync"].update(phase="虚构扫描进度 100%", running=False)
        self.refresh(updated)

        self.assertEqual(self.app.selected_task, "fictional-task-008")
        self.assertIs(self.card_for_title("虚构待办 008"), selected_card)
        self.assertIs(self.detail_label("虚构待办 008"), detail_title)
        self.assertIs(self.root.focus_get(), focused)
        self.assertEqual(self.app.canvas.yview(), task_y)
        self.assertEqual(self.app.detail_canvas.yview(), detail_y)
        self.assertEqual(self.app.visible_task_ids, [t["id"] for t in updated["tasks"]])

    def test_task_progress_and_receipt_update_render_and_other_task_keeps_detail(self):
        selected_id = "fictional-task-008"
        self.app._select_task(selected_id)
        self.root.update_idletasks()
        old_card = self.card_for_title("虚构待办 008")
        updated = copy.deepcopy(self.app.snapshot)
        updated["tasks"][8]["progress"] = "刚刚完成的虚构进度更新"
        updated["nudges"] = [{"action_id": "fictional-receipt", "conversation_id": updated["tasks"][8]["conversation_id"],
                               "status": "sent", "error": "", "attention": "虚构送达回执", "updated_at": time.time()}]
        self.refresh(updated)
        self.assertIsNotNone(self.detail_label("刚刚完成的虚构进度更新"))
        self.assertIsNotNone(self.detail_label("已送达\n虚构送达回执"))
        self.assertEqual(self.app.selected_task, selected_id)
        self.assertIs(self.card_for_title("虚构待办 008"), old_card)
        updated_detail = self.detail_label("虚构待办 008")
        self.assertIsNotNone(updated_detail)
        updated_other = copy.deepcopy(updated)
        updated_other["tasks"][9]["progress"] = "另一条虚构待办更新"
        self.refresh(updated_other)
        self.assertEqual(self.app.selected_task, selected_id)
        self.assertIs(self.detail_label("虚构待办 008"), updated_detail)

    def test_new_tasks_above_viewport_preserve_visible_task_and_pixel_offset(self):
        self.app.canvas.yview_moveto(.43)
        self.root.update_idletasks()
        anchor_title, anchor_offset = self.visible_task_anchor()
        updated = copy.deepcopy(self.app.snapshot)
        additions = []
        for index in range(3):
            task = copy.deepcopy(updated["tasks"][0])
            task.update(id="fictional-added-%d" % index,
                        conversation_id="fictional:added-%d" % index,
                        title="虚构新增任务 %d" % index,
                        updated_at=time.time() + 100 + index)
            additions.append(task)
        updated["tasks"] = additions + updated["tasks"]
        self.refresh(updated)
        next_title, next_offset = self.visible_task_anchor()
        self.assertEqual(next_title, anchor_title)
        self.assertAlmostEqual(next_offset, anchor_offset, delta=4)

    def visible_task_anchor(self):
        top = self.app.canvas.canvasy(0)
        for card in self.app.cards.winfo_children():
            if card.winfo_y() + card.winfo_height() > top:
                title = next(widget.cget("text") for widget in self.descendants(card)
                             if isinstance(widget, tk.Label) and widget.cget("text").startswith("虚构"))
                return title, top - card.winfo_y()
        self.fail("task viewport has no visible card")

    def test_explicit_filter_keeps_selection_inside_visible_rows(self):
        self.app._select_task("fictional-task-010")
        self.app.kind_var.set("结果校对")
        self.app.search_var.set("虚构待办 020")
        self.app._render_tasks()
        self.assertEqual(self.app.visible_task_ids, ["fictional-task-020"])
        self.assertEqual(self.app.selected_task, "fictional-task-020")
        self.assertIsNotNone(self.detail_label("虚构待办 020"))

        self.app.search_var.set("no matching fictional task")
        self.app._render_tasks()
        self.assertEqual(self.app.visible_task_ids, [])
        self.assertIsNone(self.app.selected_task)
        self.assertFalse(self.app.detail.winfo_manager())

    def test_conversation_refresh_preserves_selection_focus_and_scroll_anchor(self):
        self.app._switch("conversations")
        self.root.update()
        tree = self.app.conversations
        selected_id = "fictional:refresh-030"
        tree.selection_set(selected_id)
        tree.focus(selected_id)
        tree.see(selected_id)
        tree.yview_scroll(-7, "units")
        tree.focus_set()
        self.root.update()
        old_focus = self.root.focus_get()
        self.assertIs(old_focus, tree)
        old_anchor = self.visible_conversation_anchor()

        updated = copy.deepcopy(self.app.snapshot)
        for index in range(3):
            conv = copy.deepcopy(updated["conversations"][0])
            conv.update(id="fictional:inserted-%d" % index,
                        thread_id="fictional-inserted-%d" % index,
                        title="虚构插入对话 %d" % index, updated_at=time.time() + 100 + index)
            updated["conversations"].insert(index, conv)
        self.refresh(updated)

        self.assertEqual(tree.selection(), (selected_id,))
        self.assertEqual(tree.focus(), selected_id)
        self.assertIs(self.root.focus_get(), old_focus)
        self.assertEqual(self.visible_conversation_anchor(), old_anchor)

    def visible_conversation_anchor(self):
        tree = self.app.conversations
        visible = []
        for iid in tree.get_children(""):
            box = tree.bbox(iid, "#0")
            if box and box[1] >= 0:
                visible.append((box[1], iid))
        self.assertTrue(visible, "conversation tree has no visible rows")
        y, iid = min(visible)
        return iid, y

    def test_status_phase_length_does_not_change_task_viewport_height(self):
        self.app.status_var.set("虚构状态")
        self.root.update_idletasks()
        original_height = self.app.canvas.winfo_height()
        updated = copy.deepcopy(self.app.snapshot)
        updated["sync"]["phase"] = "非常长的虚构状态阶段 " * 80
        self.refresh(updated)
        self.assertEqual(self.app.canvas.winfo_height(), original_height)


if __name__ == "__main__":
    unittest.main()
