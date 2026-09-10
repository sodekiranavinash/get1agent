import asyncio
import os
from collections.abc import Coroutine
from typing import Any, TypeVar

import boto3
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None
_loop: asyncio.AbstractEventLoop | None = None

T = TypeVar("T")

# Lambda handles one request at a time per execution environment, so a single
# pooled connection is enough. Reusing it avoids a TCP + TLS + IAM handshake on
# every warm invocation.
_POOL_OPTIONS: dict[str, Any] = {
    "pool_size": 1,
    "max_overflow": 0,
    "pool_timeout": 5,
    "pool_recycle": 300,
    "pool_pre_ping": True,
    "pool_use_lifo": True,
}


def _required(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f"Missing required env var: {name}")
    return value


def _iam_token() -> str:
    host = _required("DB_HOST")
    port = int(os.environ.get("DB_PORT", "5432"))
    user = _required("DB_IAM_USER")
    region = _required("AWS_REGION")
    client = boto3.client("rds", region_name=region)
    return client.generate_db_auth_token(
        DBHostname=host,
        Port=port,
        DBUsername=user,
        Region=region,
    )


def get_event_loop() -> asyncio.AbstractEventLoop:
    """Return a long-lived event loop so pooled asyncpg connections stay usable.

    ``asyncio.run`` creates and closes a loop per call; asyncpg connections are
    bound to the loop that created them, so a persistent loop is required for
    connection reuse across invocations.
    """
    global _loop
    if _loop is None or _loop.is_closed():
        _loop = asyncio.new_event_loop()
        asyncio.set_event_loop(_loop)
    return _loop


def run_async(coro: Coroutine[Any, Any, T]) -> T:
    return get_event_loop().run_until_complete(coro)


def create_engine_from_url(database_url: str) -> AsyncEngine:
    return create_async_engine(
        database_url,
        connect_args={"statement_cache_size": 0},
        **_POOL_OPTIONS,
    )


def create_engine_from_env() -> AsyncEngine:
    host = _required("DB_HOST")
    port = os.environ.get("DB_PORT", "5432")
    database = _required("DB_NAME")
    user = _required("DB_IAM_USER")

    engine = create_async_engine(
        f"postgresql+asyncpg://{user}@{host}:{port}/{database}",
        connect_args={"ssl": "require", "statement_cache_size": 0},
        **_POOL_OPTIONS,
    )

    @event.listens_for(engine.sync_engine, "do_connect")
    def provide_token(dialect, conn_rec, cargs, cparams) -> None:
        cparams["password"] = _iam_token()
        cparams.setdefault("ssl", "require")

    return engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    global _engine, _session_factory
    if _session_factory is None:
        database_url = os.environ.get("DATABASE_URL")
        _engine = (
            create_engine_from_url(database_url)
            if database_url
            else create_engine_from_env()
        )
        _session_factory = async_sessionmaker(_engine, expire_on_commit=False)
    return _session_factory
