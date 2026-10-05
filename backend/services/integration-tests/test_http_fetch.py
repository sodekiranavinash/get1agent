"""http-fetch: the response is returned inline (no storage).

The outbound HTTP call is stubbed (no network). Storing/reading files is covered
by ``test_storage.py`` against the separate storage server.
"""

from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
APP = REPO / "backend" / "services" / "mcp" / "http-fetch"

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


def _stub_fetch(
    monkeypatch, *, body: bytes = SAMPLE, content_type: str = "application/json"
):
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


def test_fetch_returns_json_inline(monkeypatch):
    _stub_fetch(monkeypatch)
    out = service.fetch({"url": "https://api.example.com/data"})
    assert out["error"] is None
    assert out["status"] == 200
    assert out["format"] == "json"
    assert out["content"] == {"hello": "world"}
    assert out["bytes"] == len(SAMPLE)


def test_fetch_truncates_text(monkeypatch):
    _stub_fetch(monkeypatch, body=b"a" * 2500, content_type="text/plain")
    out = service.fetch({"url": "https://x/y", "format": "text", "maxChars": 1000})
    assert out["format"] == "text"
    assert out["content"] == "a" * 1000
    assert out["truncated"] is True


def test_blocked_target_returns_error(monkeypatch):
    def boom(url, **kwargs):
        raise service.fetcher.FetchError("blocked_target", "nope")

    monkeypatch.setattr(service.fetcher, "fetch", boom)
    out = service.fetch({"url": "http://169.254.169.254/"})
    assert out["error"]["code"] == "blocked_target"


def test_empty_body_is_an_error(monkeypatch):
    _stub_fetch(monkeypatch, body=b"", content_type="text/plain")
    out = service.fetch({"url": "https://api.example.com/empty"})
    assert out["error"]["code"] == "empty_response"


def test_missing_url_is_an_error():
    assert service.fetch({})["error"]["code"] == "invalid_request"
