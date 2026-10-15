"""Check public coindex releases; no downloads or installation are performed here."""
import datetime as dt
import json
from pathlib import Path
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid

REPOSITORY = "Junming-Liang/coindex"
API_URL = "https://api.github.com/repos/" + REPOSITORY + "/releases/latest"
RELEASE_ROOT = "https://github.com/" + REPOSITORY + "/releases/"
MAX_RESPONSE_BYTES = 1024 * 1024
TIMEOUT_SECONDS = 10
SEMVER = re.compile(r"(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\Z")
PUBLIC_KEYS = ("version", "title", "notes", "url", "download_url", "published_at")


def version_tuple(value):
    if not isinstance(value, str) or len(value) > 40 or not SEMVER.fullmatch(value):
        raise ValueError("\u53d1\u5e03\u7248\u672c\u683c\u5f0f\u65e0\u6548")
    return tuple(int(part) for part in value.split("."))


def current_version(root=None):
    root = Path(root) if root is not None else Path(__file__).resolve().parents[1]
    if (root / "VERSION").is_file():
        value = (root / "VERSION").read_text().strip()
    else:
        try:
            value = json.loads((root / "release.json").read_text())["version"]
        except (OSError, ValueError, KeyError, TypeError):
            raise ValueError("\u65e0\u6cd5\u8bfb\u53d6\u5f53\u524d\u5e94\u7528\u7248\u672c")
    version_tuple(value)
    return value


def _trusted_url(value, expected_path):
    if not isinstance(value, str) or len(value) > 600 or any(ord(char) <= 32 or ord(char) == 127 for char in value):
        return False
    try:
        url = urllib.parse.urlsplit(value)
        return (url.scheme == "https" and url.netloc == "github.com"
                and url.path == expected_path and not url.query and not url.fragment)
    except ValueError:
        return False


def _asset_name(version, platform=None):
    platform = platform or sys.platform
    suffix = "-macos-universal.zip" if platform == "darwin" else "-linux.tar.gz" if platform.startswith("linux") else None
    if suffix is None:
        raise ValueError("\u5f53\u524d\u5e73\u53f0\u6682\u4e0d\u652f\u6301\u66f4\u65b0\u68c0\u67e5")
    return "coindex-" + version + suffix


def parse_release(payload, platform=None):
    if not isinstance(payload, dict) or payload.get("draft") is not False or payload.get("prerelease") is not False:
        raise ValueError("\u53ea\u652f\u6301\u5df2\u516c\u5f00\u7684\u7a33\u5b9a\u7248\u672c")
    tag = payload.get("tag_name")
    if not isinstance(tag, str):
        raise ValueError("\u53d1\u5e03\u7248\u672c\u683c\u5f0f\u65e0\u6548")
    version = tag[1:] if tag.startswith("v") else tag
    version_tuple(version)
    url = payload.get("html_url")
    if not _trusted_url(url, "/" + REPOSITORY + "/releases/tag/" + tag):
        raise ValueError("\u53d1\u5e03\u9875\u9762\u4e0d\u5c5e\u4e8e coindex \u5b98\u65b9\u4ed3\u5e93")
    published = payload.get("published_at")
    try:
        if not isinstance(published, str) or len(published) > 40:
            raise ValueError()
        date = dt.datetime.fromisoformat(published.replace("Z", "+00:00"))
        if date.tzinfo is None:
            raise ValueError()
    except ValueError:
        raise ValueError("\u53d1\u5e03\u65f6\u95f4\u65e0\u6548")
    expected = _asset_name(version, platform)
    assets = payload.get("assets")
    if not isinstance(assets, list):
        raise ValueError("\u53d1\u5e03\u6587\u4ef6\u6e05\u5355\u65e0\u6548")
    matches = [asset for asset in assets if isinstance(asset, dict) and asset.get("name") == expected]
    if len(matches) > 1:
        raise ValueError("\u53d1\u5e03\u6587\u4ef6\u6e05\u5355\u5305\u542b\u91cd\u590d\u7248\u672c")
    target = url
    if matches:
        asset = matches[0]
        target = asset.get("browser_download_url")
        path = "/" + REPOSITORY + "/releases/download/" + tag + "/" + expected
        if asset.get("state") != "uploaded" or not _trusted_url(target, path):
            raise ValueError("\u66f4\u65b0\u4e0b\u8f7d\u5730\u5740\u65e0\u6548")
    title = payload.get("name") or ("coindex " + version)
    notes = payload.get("body") or "\u6b64\u7248\u672c\u672a\u63d0\u4f9b\u66f4\u65b0\u8bf4\u660e\u3002"
    if not isinstance(title, str) or not isinstance(notes, str):
        raise ValueError("\u66f4\u65b0\u8bf4\u660e\u683c\u5f0f\u65e0\u6548")
    return {"version": version, "tag": tag, "title": title[:160], "notes": notes[:20000],
            "url": url, "download_url": target, "published_at": published}


class _NoRedirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ValueError("\u66f4\u65b0\u63a5\u53e3\u53d1\u751f\u4e86\u672a\u5141\u8bb8\u7684\u8df3\u8f6c")


def _open_release(request, timeout):
    return urllib.request.build_opener(_NoRedirects()).open(request, timeout=timeout)


def fetch_latest():
    request = urllib.request.Request(API_URL, headers={
        "Accept": "application/vnd.github+json", "Accept-Encoding": "identity",
        "User-Agent": "coindex-update-check", "X-GitHub-Api-Version": "2026-03-10"})
    with _open_release(request, timeout=TIMEOUT_SECONDS) as response:
        if response.geturl() != API_URL:
            raise ValueError("\u66f4\u65b0\u63a5\u53e3\u5730\u5740\u65e0\u6548")
        data = response.read(MAX_RESPONSE_BYTES + 1)
    if len(data) > MAX_RESPONSE_BYTES:
        raise ValueError("\u66f4\u65b0\u4fe1\u606f\u8d85\u8fc7\u5141\u8bb8\u5927\u5c0f")
    try:
        return json.loads(data)
    except (ValueError, UnicodeError):
        raise ValueError("\u66f4\u65b0\u4fe1\u606f\u4e0d\u662f\u6709\u6548 JSON")


def _saved(store):
    value = store.meta("update_state", {})
    return value if isinstance(value, dict) else {}


def _put(store, value):
    store.db.execute("INSERT INTO meta VALUES('update_state',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                     (json.dumps(value, ensure_ascii=False),))


def state(store):
    saved = _saved(store)
    result = {key: saved.get(key, "") for key in PUBLIC_KEYS}
    result.update({"current_version": "", "checking": bool(saved.get("checking")),
                   "available": False, "checked_at": saved.get("checked_at", 0),
                   "error": saved.get("error", ""), "skipped_version": store.meta("update_skipped_version", ""),
                   "should_prompt": False})
    try:
        result["current_version"] = current_version()
        result["available"] = bool(result["version"]) and version_tuple(result["version"]) > version_tuple(result["current_version"])
    except ValueError:
        if not result["current_version"]:
            result["error"] = "\u65e0\u6cd5\u8bfb\u53d6\u5f53\u524d\u5e94\u7528\u7248\u672c"
    result["should_prompt"] = bool(result["available"] and saved.get("prompt_pending")
        and not result["checking"] and not result["error"]
        and (not saved.get("automatic") or result["version"] != result["skipped_version"]))
    return result


def begin(store, automatic=False):
    with store.db:
        store.db.execute("BEGIN IMMEDIATE")
        saved = _saved(store)
        if saved.get("checking"):
            return False
        saved.update({"checking": True, "request_id": uuid.uuid4().hex, "automatic": bool(automatic),
                      "prompt_pending": False, "error": ""})
        _put(store, saved)
    return True


def _finish(store, request_id, fields):
    with store.db:
        store.db.execute("BEGIN IMMEDIATE")
        saved = _saved(store)
        if not saved.get("checking") or saved.get("request_id") != request_id:
            return
        saved.update(fields)
        saved.update({"checking": False, "request_id": "",
                      "checked_at": max(time.time(), float(saved.get("checked_at") or 0) + 0.000001)})
        _put(store, saved)


def perform(store, automatic=False):
    saved = _saved(store)
    if not saved.get("checking"):
        return state(store)
    request_id = saved.get("request_id")
    try:
        current_version()
        result = parse_release(fetch_latest())
        result.update({"error": "", "prompt_pending": True})
        _finish(store, request_id, result)
    except urllib.error.HTTPError as error:
        message = "\u68c0\u67e5\u66f4\u65b0\u53d7 GitHub \u9650\u6d41\u5f71\u54cd\uff0c\u8bf7\u7a0d\u540e\u91cd\u8bd5" if error.code in (403, 429) else "\u65e0\u6cd5\u8bfb\u53d6 GitHub \u6700\u65b0\u7248\u672c\uff0c\u8bf7\u7a0d\u540e\u91cd\u8bd5"
        _finish(store, request_id, {"error": message, "prompt_pending": False})
    except (urllib.error.URLError, TimeoutError, OSError):
        _finish(store, request_id, {"error": "\u65e0\u6cd5\u8fde\u63a5 GitHub\uff0c\u8bf7\u68c0\u67e5\u7f51\u7edc\u540e\u91cd\u8bd5", "prompt_pending": False})
    except ValueError as error:
        _finish(store, request_id, {"error": str(error)[:200], "prompt_pending": False})
    except Exception:
        _finish(store, request_id, {"error": "\u68c0\u67e5\u66f4\u65b0\u5931\u8d25\uff0c\u8bf7\u7a0d\u540e\u624b\u52a8\u91cd\u8bd5", "prompt_pending": False})
    return state(store)


def cancel(store, error=""):
    with store.db:
        store.db.execute("BEGIN IMMEDIATE")
        saved = _saved(store)
        if saved.get("checking"):
            saved["checked_at"] = max(time.time(), float(saved.get("checked_at") or 0) + 0.000001)
        saved.update({"checking": False, "request_id": "", "prompt_pending": False})
        if error:
            saved["error"] = str(error)[:200]
        _put(store, saved)


def recover(store):
    cancel(store)


def skip(store, version):
    version_tuple(version)
    with store.db:
        store.db.execute("BEGIN IMMEDIATE")
        saved = _saved(store)
        if saved.get("version") != version:
            raise ValueError("\u8be5\u66f4\u65b0\u5df2\u53d8\u5316\uff0c\u8bf7\u91cd\u65b0\u68c0\u67e5\u7248\u672c")
        store.db.execute("INSERT INTO meta VALUES('update_skipped_version',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                         (json.dumps(version),))
        saved["prompt_pending"] = False
        _put(store, saved)
    return state(store)


def download_url(store):
    saved = _saved(store)
    version = saved.get("version")
    version_tuple(version)
    if version_tuple(version) <= version_tuple(current_version()):
        raise ValueError("\u5f53\u524d\u6ca1\u6709\u66f4\u65b0\u7248\u672c\u53ef\u4e0b\u8f7d")
    tag = saved.get("tag")
    if tag not in (version, "v" + version):
        raise ValueError("\u66f4\u65b0\u7248\u672c\u4fe1\u606f\u65e0\u6548")
    page = "/" + REPOSITORY + "/releases/tag/" + tag
    asset = "/" + REPOSITORY + "/releases/download/" + tag + "/" + _asset_name(version)
    target = saved.get("download_url")
    if not _trusted_url(saved.get("url"), page) or not (_trusted_url(target, page) or _trusted_url(target, asset)):
        raise ValueError("\u66f4\u65b0\u4e0b\u8f7d\u5730\u5740\u65e0\u6548\uff0c\u8bf7\u91cd\u65b0\u68c0\u67e5\u7248\u672c")
    return target
