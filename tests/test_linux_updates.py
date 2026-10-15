"""Version prompt tests use only a fake transport and never access GitHub."""
import copy
import unittest
from unittest.mock import patch

try:
    import tkinter as tk
except ImportError:
    tk = None

from linux.app import CoindexApp, demo_snapshot
from linux.updates import UpdateDialog


def state(**values):
    result = {"current_version": "1.9.0", "checking": False, "available": False, "version": "", "title": "",
              "notes": "", "url": "", "download_url": "", "published_at": "", "error": "",
              "checked_at": 0, "skipped_version": "", "should_prompt": False}
    result.update(values)
    return result


def available(**values):
    return state(available=True, version="1.10.0", title="Summary", notes="# Changelog\n" + "Fictional update.\n" * 60,
                 url="https://github.com/Junming-Liang/coindex/releases/tag/v1.10.0",
                 download_url="https://github.com/Junming-Liang/coindex/releases/download/v1.10.0/coindex-1.10.0-linux.tar.gz",
                 checked_at=1, should_prompt=True, **values)


class UpdateUITests(unittest.TestCase):
    def setUp(self):
        if tk is None:
            self.skipTest("Tkinter is unavailable")
        try:
            self.root = tk.Tk()
        except tk.TclError as error:
            self.skipTest("Tk display unavailable: %s" % error)
        self.app = CoindexApp(self.root, demo=True, demo_data=demo_snapshot())
        self.app.demo = False
        self.calls = []
        def request(method, callback=None, **values):
            self.calls.append((method, values, callback))
            return "fake-request"
        self.app._rpc = request

    def tearDown(self):
        if getattr(self, "root", None):
            self.app.close()

    def refresh(self, value):
        self.app.snapshot["app_update"] = copy.deepcopy(value)
        self.app._render()
        self.root.update()

    def test_startup_checks_once_and_demo_never_checks(self):
        self.app.demo = True
        self.refresh(state())
        self.assertFalse(self.calls)
        self.app.demo = False
        self.refresh(state())
        self.assertEqual([(call[0], call[1]) for call in self.calls], [("check_updates", {"automatic": True})])
        self.refresh(state(checking=True))
        self.refresh(state(checked_at=1))
        self.refresh(state(checked_at=1))
        self.assertEqual(len(self.calls), 1)
        self.assertFalse(self.app.updates.pending)

    def test_changelog_prompt_preserves_scroll_and_later_does_not_persist_skip(self):
        self.refresh(state())
        self.refresh(available())
        dialog = self.app.updates.dialog
        self.assertEqual(dialog.notes.get("1.0", "end-1c"), available()["notes"])
        dialog.notes.yview_moveto(.5)
        self.root.update()
        top = dialog.notes.yview()
        self.refresh(available())
        self.assertIs(self.app.updates.dialog, dialog)
        self.assertEqual(dialog.notes.yview(), top)
        dialog.win.destroy()
        self.refresh(available())
        self.assertFalse(dialog.win.winfo_exists())
        self.assertFalse(any(call[0] == "skip_update" for call in self.calls))

    def test_skip_and_download_use_displayed_release_and_manual_can_reopen_it(self):
        self.refresh(state())
        self.refresh(available())
        dialog = self.app.updates.dialog
        dialog.download()
        self.assertEqual(self.calls[-1][:2], ("open_update", {"version": "1.10.0"}))
        self.calls[-1][2]({"result": {"opened": True}})
        dialog.skip()
        self.assertEqual(self.calls[-1][:2], ("skip_update", {"version": "1.10.0"}))
        snapshot = copy.deepcopy(self.app.snapshot)
        snapshot["app_update"].update(skipped_version="1.10.0", should_prompt=False)
        self.calls[-1][2]({"result": snapshot})
        self.assertFalse(dialog.win.winfo_exists())
        self.app.updates.check()
        self.assertEqual(self.calls[-1][:2], ("check_updates", {"automatic": False}))
        next_state = available()
        next_state.update(checked_at=2, skipped_version="1.10.0")
        self.refresh(next_state)
        self.assertTrue(self.app.updates.dialog.win.winfo_exists())
        self.assertIsNot(self.app.updates.dialog, dialog)

    def test_manual_no_update_and_error_are_reported_once(self):
        self.refresh(state())
        self.refresh(state(checked_at=1))
        with patch("linux.updates.messagebox.showinfo") as info:
            self.app.updates.check()
            self.refresh(state(checked_at=2))
            self.refresh(state(checked_at=2))
        info.assert_called_once()
        with patch("linux.updates.messagebox.showerror") as error:
            self.app.updates.check()
            self.refresh(state(checked_at=3, error="Fictional connection failure"))
            self.refresh(state(checked_at=3, error="Fictional connection failure"))
        error.assert_called_once()

    def test_release_without_asset_offers_page_and_minimum_dialog_keeps_actions(self):
        current = available()
        current["download_url"] = current["url"]
        dialog = UpdateDialog(self.app, current)
        dialog.win.geometry("560x420")
        self.root.update()
        self.assertEqual(dialog.download_button.cget("text"), "查看发布页")
        self.assertLessEqual(dialog.download_button.winfo_rooty() + dialog.download_button.winfo_height(),
                             dialog.win.winfo_rooty() + dialog.win.winfo_height())
        self.assertGreater(dialog.download_button.winfo_width(), 50)
        dialog.download()
        self.assertEqual(self.calls[-1][:2], ("open_update", {"version": "1.10.0"}))


if __name__ == "__main__":
    unittest.main()
