from __future__ import annotations

from typing import Any

from sqlalchemy.types import UserDefinedType


class Vector(UserDefinedType):
    """pgvector column type with no Python-side dependency.

    Embeddings are sent as the pgvector text form (``[0.1,0.2,...]``) and read
    back as text, because asyncpg has no codec registered for the vector OID.
    This keeps the shared layer free of the ``pgvector`` package while still
    producing real ``vector(n)`` columns and HNSW indexes in Postgres.
    """

    cache_ok = True

    def __init__(self, dimensions: int) -> None:
        self.dimensions = dimensions

    def get_col_spec(self, **kw: Any) -> str:
        return f"vector({self.dimensions})"

    def bind_processor(self, dialect: Any):
        def process(value: Any) -> str | None:
            if value is None:
                return None
            return "[" + ",".join(repr(float(item)) for item in value) + "]"

        return process

    def result_processor(self, dialect: Any, coltype: Any):
        def process(value: Any) -> list[float] | None:
            if value is None:
                return None
            if isinstance(value, str):
                inner = value.strip().strip("[]")
                return [float(item) for item in inner.split(",")] if inner else []
            return [float(item) for item in value]

        return process
