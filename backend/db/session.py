"""异步数据库连接与 FastAPI Session 依赖。"""
from __future__ import annotations

from collections.abc import AsyncIterator

from sqlalchemy import event
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from backend.config.settings import settings

def enable_sqlite_foreign_keys(async_engine: AsyncEngine) -> None:
    """为 SQLite 异步引擎的每条连接开启外键约束。"""

    @event.listens_for(async_engine.sync_engine, "connect")
    def _enable_sqlite_foreign_keys(dbapi_connection, _) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


engine = create_async_engine(
    settings.database_url,
    pool_pre_ping=True,
)

if settings.database_url.startswith("sqlite"):
    enable_sqlite_foreign_keys(engine)


AsyncSessionFactory = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    autoflush=False,
    expire_on_commit=False,
)


async def get_db_session() -> AsyncIterator[AsyncSession]:
    """为一次 HTTP 请求提供独立的数据库 Session。

    提交事务由 Service 层负责；发生异常时统一回滚，避免把半成品写入数据库。
    """
    async with AsyncSessionFactory() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
