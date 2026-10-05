"""storage MCP server tools: write -> list -> read -> delete (moto DynamoDB).

The repository itself is covered by ``test_storage.py``; this file exercises the
server's service layer, with bytes in the in-memory S3 double.
"""

from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
APP = REPO / "backend" / "services" / "mcp" / "storage"

USER = "u_7k3f9qz2mpx8n4rq"
OTHER = "u_zzzzzzzzzzzzzzzz"


def _load_service():
    pkg_name = "storage_app"
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


def test_write_list_read_delete(fake_storage, monkeypatch):
    monkeypatch.setattr(service, "_storage", lambda: fake_storage)

    written = service.write_file(USER, {"fileName": "rates.json", "content": '{"usd": 1}'})
    assert written["error"] is None
    file_id = written["file"]["id"]
    assert written["file"]["fileName"] == "rates.json"
    assert written["file"]["contentType"] == "application/json"
    assert any(key.startswith(f"storage/{USER}/") for key in fake_storage.data)

    listed = service.list_files(USER)
    assert [item["id"] for item in listed["files"]] == [file_id]

    read = service.read_file(USER, {"fileId": file_id})
    assert read["error"] is None
    assert read["format"] == "json"
    assert '"usd": 1' in read["content"]

    deleted = service.delete_file(USER, {"fileId": file_id})
    assert deleted["error"] is None and deleted["deleted"] is True
    assert service.list_files(USER)["files"] == []
    assert fake_storage.data == {}


def test_writes_are_scoped_by_user(fake_storage, monkeypatch):
    monkeypatch.setattr(service, "_storage", lambda: fake_storage)
    written = service.write_file(USER, {"fileName": "a.txt", "content": "hi"})
    file_id = written["file"]["id"]
    assert service.read_file(USER, {"fileId": file_id})["error"] is None
    assert service.read_file(OTHER, {"fileId": file_id})["error"]["code"] == "not_found"


def test_binary_base64_round_trip(fake_storage, monkeypatch):
    monkeypatch.setattr(service, "_storage", lambda: fake_storage)
    written = service.write_file(
        USER,
        {"fileName": "blob.bin", "content": "AAEC", "encoding": "base64"},
    )
    assert written["error"] is None
    read = service.read_file(
        USER, {"fileId": written["file"]["id"], "format": "base64"}
    )
    assert read["content"] == "AAEC"


def test_write_requires_inputs(fake_storage, monkeypatch):
    monkeypatch.setattr(service, "_storage", lambda: fake_storage)
    assert service.write_file(USER, {})["error"]["code"] == "invalid_request"
    assert (
        service.write_file(USER, {"fileName": "x.txt"})["error"]["code"]
        == "invalid_request"
    )


def test_delete_missing_file(fake_storage, monkeypatch):
    monkeypatch.setattr(service, "_storage", lambda: fake_storage)
    assert service.delete_file(USER, {"fileId": "nope"})["error"]["code"] == "not_found"
