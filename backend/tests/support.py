"""Shared test helpers: an in-memory S3 double and module loaders."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]

DYNAMODB_TABLE = "get1agent-test"


class FakeStorage:
    """Minimal in-memory stand-in for ``shared.storage.Storage``.

    Implements just the surface the search/index/user-api code uses, including
    the conditional ``If-Match`` semantics the term index relies on.
    """

    def __init__(self) -> None:
        self.data: dict[str, bytes] = {}
        self.etags: dict[str, str] = {}
        self._seq = 0

    # --- bytes ---------------------------------------------------------------
    def put_bytes(self, key: str, data: bytes, content_type: str = "x") -> None:
        self.data[key] = data

    def get_bytes(self, key: str) -> bytes:
        return self.data[key]

    def delete(self, key: str) -> None:
        self.data.pop(key, None)
        self.etags.pop(key, None)

    def delete_prefix(self, prefix: str) -> None:
        for key in [k for k in self.data if k.startswith(prefix)]:
            self.data.pop(key, None)
            self.etags.pop(key, None)

    # --- presign / head ------------------------------------------------------
    def presign_put(self, key: str, content_type: str, expires_in: int = 3600) -> str:
        return f"https://s3.test/{key}"

    def presign_get(self, key: str, expires_in: int = 3600) -> str:
        return f"https://s3.test/{key}"

    def head_size(self, key: str) -> int:
        if key not in self.data:
            raise FileNotFoundError(key)
        return len(self.data[key])

    def head_etag(self, key: str) -> str:
        return "etag-" + key

    # --- json ----------------------------------------------------------------
    def get_json(self, key: str) -> Any | None:
        raw = self.data.get(key)
        if raw is None:
            return None
        return json.loads(raw.decode("utf-8"))

    def get_json_with_etag(self, key: str) -> tuple[Any | None, str | None]:
        return (self.get_json(key), self.etags.get(key))

    def put_json(self, key: str, value: Any) -> None:
        self.data[key] = json.dumps(value).encode("utf-8")
        self._seq += 1
        self.etags[key] = f"e{self._seq}"

    def put_json_conditional(self, key: str, value: Any, etag: str | None) -> str:
        if etag is not None and self.etags.get(key) != etag:
            from shared.storage import PreconditionFailed

            raise PreconditionFailed(key)
        self.data[key] = json.dumps(value).encode("utf-8")
        self._seq += 1
        self.etags[key] = f"e{self._seq}"
        return self.etags[key]


def load_module(relative_path: str, name: str) -> Any:
    """Load a Lambda handler by file path under a unique module name.

    Both ``user-api`` and ``knowledge-mcp`` ship a top-level ``handler`` module,
    so they cannot both be imported as ``handler`` in one process.
    """
    path = REPO_ROOT / relative_path
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _local_store(fake: FakeStorage):
    from shared.search.s3_vectors import LocalVectorStore

    return LocalVectorStore(fake)


def patch_search(monkeypatch, fake: FakeStorage) -> None:
    """Point the retrieval service at the in-memory S3 double."""
    from shared.search import service

    monkeypatch.setattr(service, "Storage", lambda: fake)
    monkeypatch.setattr(service, "vector_store", lambda storage: _local_store(fake))


def patch_pipeline(monkeypatch, fake: FakeStorage) -> None:
    """Point the ingestion pipeline's vector store at the in-memory double."""
    import shared.ingestion.pipeline as pipeline

    monkeypatch.setattr(pipeline, "vector_store", lambda storage: _local_store(fake))


def patch_actions(monkeypatch, fake: FakeStorage) -> None:
    import shared.ingestion.actions as actions

    monkeypatch.setattr(actions, "_storage", lambda: fake)


def patch_lambda_storage(monkeypatch, module: Any, fake: FakeStorage) -> None:
    """Point a handler module (user-api / knowledge-mcp) at the S3 double."""
    monkeypatch.setattr(module, "Storage", lambda: fake)
    if hasattr(module, "vector_store"):
        monkeypatch.setattr(module, "vector_store", lambda storage: _local_store(fake))
