"""http-fetch: fetch → save to storage → list → read (moto-backed DynamoDB).

The outbound HTTP call is stubbed (no network); the storage double is the
in-memory S3 fixture. Identity scoping is exercised by reading as another user.
"""

from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
APP = REPO / "backend" / "services" / "mcp" / "http-fetch"

USER = "u_7k3f9qz2mpx8n4rq"
OTHER = "u_zzzzzzzzzzzzzzzz"

SAMPLE = b'{"hello": "world"}'


def _load_service():
    """Load ``src/service.py`` as ``http_fetch_app.service`` (relative imports)."""
    pkg_name = "http_fetch_app"
    if pkg_name not in sys.modules:
        pkg = types.ModuleType(pkg_name)
        pkg.__path__ = [str(APP / "src")]
        sys.modules[pkg_name] = pkg
        spec = importlib.util.spec_from_file_location(
            f"{pkg_name}.service", APP / "src" / "service.py"
        )
        assert spec and spec.loader
        module = importlib.util.module_from_spec(spec)
        sys.modules[f"{pkg_name}.service"] = module
        spec.loader.exec_module(module)
    return sys.modules[f"{pkg_name}.service"]


service = _load_service()


def _stub_fetch(monkeypatch, *, body: bytes = SAMPLE, content_type: str = "application/json"):
    def fake(url, **kwargs):
        return service.fetcher.FetchResult(
            status=200,
            headers={"content-type": content_type},
            content_type=content_type,
            body=body,
            final_url=url,
            truncated=False,
            redirects=[],
        )

    monkeypatch.setattr(service.fetcher, "fetch", fake)


def test_fetch_save_list_read(fake_storage, monkeypatch):
    monkeypatch.setattr(service, "_storage", lambda: fake_storage)
    _stub_fetch(monkeypatch)

    saved = service.fetch_and_save(
        USER, {"url": "https://api.example.com/data", "fileName": "data.json"}
    )
    assert saved["error"] is None
    file_id = saved["file"]["id"]
    assert saved["file"]["fileName"] == "data.json"
    assert saved["file"]["contentType"] == "application/json"
    assert saved["file"]["sizeBytes"] == len(SAMPLE)
    assert saved["usage"]["fileCount"] == 1
    assert any(key.startswith(f"storage/{USER}/") for key in fake_storage.data)

    listed = service.list_files(USER)
    assert [item["id"] for item in listed["files"]] == [file_id]

    read = service.read_file(USER, {"fileId": file_id})
    assert read["error"] is None
    assert read["format"] == "json"
    assert '"hello": "world"' in read["content"]

    # Files are scoped by userId: another user cannot read them.
    assert service.read_file(OTHER, {"fileId": file_id})["error"]["code"] == "not_found"


def test_blocked_target_returns_error(fake_storage, monkeypatch):
    monkeypatch.setattr(service, "_storage", lambda: fake_storage)

    def boom(url, **kwargs):
        raise service.fetcher.FetchError("blocked_target", "nope")

    monkeypatch.setattr(service.fetcher, "fetch", boom)
    out = service.fetch_and_save(USER, {"url": "http://169.254.169.254/"})
    assert out["error"]["code"] == "blocked_target"
    assert fake_storage.data == {}


def test_empty_body_is_not_saved(fake_storage, monkeypatch):
    monkeypatch.setattr(service, "_storage", lambda: fake_storage)
    _stub_fetch(monkeypatch, body=b"", content_type="text/plain")
    out = service.fetch_and_save(USER, {"url": "https://api.example.com/empty"})
    assert out["error"]["code"] == "empty_response"


def test_read_missing_file(fake_storage, monkeypatch):
    monkeypatch.setattr(service, "_storage", lambda: fake_storage)
    assert service.read_file(USER, {"fileId": "nope"})["error"]["code"] == "not_found"
    assert service.read_file(USER, {})["error"]["code"] == "invalid_request"
