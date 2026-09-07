from collections.abc import AsyncGenerator
from functools import lru_cache

import asyncpg
import boto3
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from app.config import Settings, get_settings


class Base(DeclarativeBase):
    pass


def _generate_iam_token(settings: Settings) -> str:
    client = boto3.client("rds", region_name=settings.aws_region)
    return client.generate_db_auth_token(
        DBHostname=settings.database_host,
        Port=settings.database_port,
        DBUsername=settings.database_iam_user,
        Region=settings.aws_region,
    )


def _build_engine(settings: Settings) -> AsyncEngine:
    if settings.database_use_iam:

        async def connect() -> asyncpg.Connection:
            token = _generate_iam_token(settings)
            return await asyncpg.connect(
                host=settings.database_host,
                port=settings.database_port,
                user=settings.database_iam_user,
                password=token,
                database=settings.database_name,
                ssl="require",
            )

        return create_async_engine(
            "postgresql+asyncpg://",
            async_creator=connect,
            echo=settings.db_echo,
            pool_pre_ping=True,
            pool_recycle=600,
        )

    return create_async_engine(
        settings.database_url,
        echo=settings.db_echo,
        pool_pre_ping=True,
    )


@lru_cache
def get_engine() -> AsyncEngine:
    return _build_engine(get_settings())


engine = get_engine()
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        yield session


async def check_database_connection() -> None:
    async with engine.connect() as connection:
        await connection.execute(text("SELECT 1"))
