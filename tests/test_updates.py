import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import urllib.error

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from store import Store
import updates


def release_payload(version="1.11.0"):
    base = updates.RELEASE_ROOT
    tag = "v" + version
    return {"tag_name": tag, "draft": False, "prerelease": False, "name": "coindex " + version,
            "body": "New summaries and improvements.", "published_at": "2026-10-15T06:00:00Z",
            "html_url": base + "tag/" + tag,
            "assets": [{"name": "coindex-" + version + suffix, "state": "uploaded",
                        "browser_download_url": base + "download/" + tag + "/coindex-" + version + suffix}
                       for suffix in ("-macos-universal.zip", "-linux.tar.gz")]}


class UpdateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.temp.name) / "data")
        self.version_patch = patch("updates.current_version", return_value="1.10.0")
        self.version_patch.start()

    def tearDown(self):
        self.version_patch.stop()
        self.store.db.close()
        self.temp.cleanup()

    def run_check(self, payload=None, automatic=True):
        self.assertTrue(updates.begin(self.store, automatic=automatic))
        with patch("updates.fetch_latest", return_value=payload or release_payload()):
            return updates.perform(self.store, automatic=automatic)

    def test_semantic_versions_compare_numerically(self):
        self.assertGreater(updates.version_tuple("1.10.0"), updates.version_tuple("1.2.9"))
        self.assertGreater(updates.version_tuple("2.0.0"), updates.version_tuple("1.99.99"))
        for invalid in ("1.2", "v1.2.3", "01.2.3", "1.2.3-beta", "1.2.3+local", "1.2.3\n", 123):
            with self.assertRaises(ValueError):
                updates.version_tuple(invalid)
        result = self.run_check(release_payload("1.9.9"))
        self.assertFalse(result["available"])
        self.assertFalse(result["should_prompt"])

    def test_packaged_and_source_current_version(self):
        self.version_patch.stop()
        root = Path(self.temp.name) / "app"
        root.mkdir()
        (root / "release.json").write_text(json.dumps({"version": "1.10.0"}))
        self.assertEqual(updates.current_version(root), "1.10.0")
        (root / "VERSION").write_text("1.11.0\n")
        self.assertEqual(updates.current_version(root), "1.11.0")
        (root / "VERSION").write_text("1.11.bad")
        with self.assertRaises(ValueError):
            updates.current_version(root)
        self.version_patch.start()

    def test_success_exposes_release_notes_and_matching_platform_download(self):
        for platform, suffix in (("darwin", "macos-universal.zip"), ("linux", "linux.tar.gz")):
            with patch("updates.sys.platform", platform):
                result = self.run_check()
                self.assertTrue(result["available"])
                self.assertTrue(result["should_prompt"])
                self.assertFalse(result["checking"])
                self.assertEqual(result["notes"], "New summaries and improvements.")
                self.assertTrue(updates.download_url(self.store).endswith(suffix))

    def test_skip_survives_restart_suppresses_only_exact_automatic_release(self):
        self.run_check()
        updates.skip(self.store, "1.11.0")
        self.store.db.close()
        self.store = Store(Path(self.temp.name) / "data")
        skipped = self.run_check()
        self.assertTrue(skipped["available"])
        self.assertFalse(skipped["should_prompt"])
        next_release = self.run_check(release_payload("1.12.0"))
        self.assertTrue(next_release["should_prompt"])
        self.assertEqual(next_release["skipped_version"], "1.11.0")

    def test_manual_check_bypasses_skip_without_erasing_preference(self):
        self.run_check()
        updates.skip(self.store, "1.11.0")
        result = self.run_check(automatic=False)
        self.assertTrue(result["should_prompt"])
        self.assertEqual(result["skipped_version"], "1.11.0")
        with self.assertRaises(ValueError):
            updates.skip(self.store, "1.99.0")

    def test_network_failure_preserves_cached_notes_and_advances_completion_time(self):
        first = self.run_check()
        self.assertTrue(updates.begin(self.store))
        with patch("updates.fetch_latest", side_effect=urllib.error.URLError("offline")):
            result = updates.perform(self.store)
        self.assertEqual(result["version"], first["version"])
        self.assertEqual(result["notes"], first["notes"])
        self.assertGreater(result["checked_at"], first["checked_at"])
        self.assertFalse(result["checking"])
        self.assertFalse(result["should_prompt"])
        self.assertTrue(result["error"])

    def test_parallel_check_cancellation_and_stale_result_are_guarded(self):
        self.assertTrue(updates.begin(self.store))
        other = Store(Path(self.temp.name) / "data")
        try:
            self.assertFalse(updates.begin(other))
        finally:
            other.db.close()
        def cancel_during_fetch():
            updates.cancel(self.store)
            self.assertTrue(updates.begin(self.store))
            return release_payload()
        with patch("updates.fetch_latest", side_effect=cancel_during_fetch):
            updates.perform(self.store)
        self.assertTrue(updates.state(self.store)["checking"])
        self.assertFalse(updates.state(self.store)["available"])
        updates.cancel(self.store)
        with patch("updates.fetch_latest") as fetch:
            updates.perform(self.store)
            fetch.assert_not_called()

    def test_recover_clears_cached_prompt_until_fresh_request(self):
        self.assertTrue(self.run_check()["should_prompt"])
        updates.recover(self.store)
        result = updates.state(self.store)
        self.assertTrue(result["available"])
        self.assertFalse(result["should_prompt"])
        updates.begin(self.store)
        updates.recover(self.store)
        self.assertFalse(updates.state(self.store)["checking"])

    def test_rejects_unstable_or_unpublished_versions_and_invalid_tags(self):
        for key, value in (("draft", True), ("prerelease", True), ("tag_name", "v1.11.0-rc1"),
                           ("tag_name", "v01.11.0"), ("published_at", "")):
            payload = release_payload()
            payload[key] = value
            with self.assertRaises(ValueError):
                updates.parse_release(payload)

    def test_rejects_foreign_release_and_asset_urls(self):
        for unsafe in ("http://github.com/Junming-Liang/coindex/releases/tag/v1.11.0",
                       "https://github.com.evil.invalid/Junming-Liang/coindex/releases/tag/v1.11.0",
                       "https://github.com@evil.invalid/Junming-Liang/coindex/releases/tag/v1.11.0",
                       "https://github.com/other/coindex/releases/tag/v1.11.0",
                       updates.RELEASE_ROOT + "tag/v1.11.0?redirect=elsewhere",
                       "\n" + updates.RELEASE_ROOT + "tag/v1.11.0"):
            payload = release_payload()
            payload["html_url"] = unsafe
            with self.assertRaises(ValueError):
                updates.parse_release(payload, "darwin")
        payload = release_payload()
        payload["assets"][0]["browser_download_url"] = "https://evil.invalid/update.zip"
        with self.assertRaises(ValueError):
            updates.parse_release(payload, "darwin")
        payload = release_payload()
        payload["assets"].append(payload["assets"][0])
        with self.assertRaises(ValueError):
            updates.parse_release(payload, "darwin")

    def test_missing_platform_asset_falls_back_to_verified_release_page(self):
        payload = release_payload()
        payload["assets"] = []
        self.run_check(payload)
        self.assertEqual(updates.download_url(self.store), payload["html_url"])
        saved = self.store.meta("update_state")
        saved["download_url"] = "https://evil.invalid/download"
        self.store.put_meta("update_state", saved)
        with self.assertRaises(ValueError):
            updates.download_url(self.store)

    def test_release_body_is_bounded_plain_data(self):
        payload = release_payload()
        payload["body"] = "<b>Release notes</b> " + "x" * 30000
        result = updates.parse_release(payload)
        self.assertEqual(len(result["notes"]), 20000)
        self.assertTrue(result["notes"].startswith("<b>"))

    def test_fetch_size_timeout_and_no_redirects(self):
        class Response(io.BytesIO):
            def geturl(self):
                return updates.API_URL
        with patch("updates._open_release", return_value=Response(json.dumps(release_payload()).encode())) as opening:
            self.assertEqual(updates.fetch_latest()["tag_name"], "v1.11.0")
            self.assertEqual(opening.call_args.kwargs["timeout"], 10)
            self.assertEqual(opening.call_args.args[0].full_url, updates.API_URL)
        with patch("updates._open_release", return_value=Response(b"x" * (updates.MAX_RESPONSE_BYTES + 1))):
            with self.assertRaises(ValueError):
                updates.fetch_latest()
        with self.assertRaises(ValueError):
            updates._NoRedirects().redirect_request(None, None, 302, "", {}, "https://evil.invalid")


if __name__ == "__main__":
    unittest.main()
