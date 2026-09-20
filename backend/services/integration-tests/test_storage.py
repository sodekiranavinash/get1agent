"""Standalone file storage repository (moto-backed DynamoDB)."""

from __future__ import annotations

from data.repositories import storage as repo

USER = "u_7k3f9qz2mpx8n4rq"


def _make(file_id: str, name: str = "report.pdf", size: int = 1234) -> dict:
    item = repo.storage_item(
        file_id=file_id,
        user_id=USER,
        file_name=name,
        s3_key=f"storage/{USER}/{file_id}/{name}",
        content_type="application/pdf",
        size_bytes=size,
    )
    return repo.put_file(item)


def test_create_get_list_delete() -> None:
    _make("f1")
    assert repo.get_file(USER, "f1")["fileName"] == "report.pdf"
    assert [item["fileId"] for item in repo.list_files(USER)] == ["f1"]

    removed = repo.delete_file(USER, "f1")
    assert removed is not None
    assert repo.get_file(USER, "f1") is None
    assert repo.list_files(USER) == []


def test_duplicate_file_id_fails() -> None:
    _make("f2")
    try:
        _make("f2")
    except Exception:  # noqa: BLE001 - conditional write failure
        pass
    else:  # pragma: no cover
        raise AssertionError("duplicate put should fail")


def test_list_is_newest_first() -> None:
    repo.put_file(
        repo.storage_item(
            file_id="old",
            user_id=USER,
            file_name="a.txt",
            s3_key=f"storage/{USER}/old/a.txt",
            content_type="text/plain",
            size_bytes=1,
            created_at="2026-01-01T00:00:00Z",
        )
    )
    repo.put_file(
        repo.storage_item(
            file_id="new",
            user_id=USER,
            file_name="b.txt",
            s3_key=f"storage/{USER}/new/b.txt",
            content_type="text/plain",
            size_bytes=1,
            created_at="2026-02-01T00:00:00Z",
        )
    )
    assert [item["fileId"] for item in repo.list_files(USER)] == ["new", "old"]
