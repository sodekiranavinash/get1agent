import asyncio
import os
import sys
from logging.config import fileConfig

from alembic import context

_HERE = os.path.dirname(os.path.abspath(__file__))
_BACKEND_ROOT = os.path.dirname(_HERE)
if os.path.isdir(os.path.join(_BACKEND_ROOT, "shared")):
    sys.path.insert(0, _BACKEND_ROOT)

from shared.db.engine import create_engine_from_env, create_engine_from_url  # noqa: E402
from shared.models import Base  # noqa: E402

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    url = os.environ.get("DATABASE_URL")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    database_url = os.environ.get("DATABASE_URL")
    engine = (
        create_engine_from_url(database_url)
        if database_url
        else create_engine_from_env()
    )
    async with engine.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await engine.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
