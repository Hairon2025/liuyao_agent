"""pytest 共享 fixtures

提供：
- client: FastAPI TestClient 实例（按 request 级别隔离）
- created_divination_ids: 自动收集本测试创建的 ID，teardown 时清理
"""
from __future__ import annotations

import asyncio

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from backend.api.server import app
from backend.db.base import Base
from backend.db.session import get_db_session
import backend.models  # noqa: F401  # 确保测试建表时已注册全部 Model
from backend.running_data import divination_store


@pytest.fixture
def client(tmp_path) -> TestClient:
    """使用独立临时 SQLite 数据库的 FastAPI TestClient。"""
    database_path = tmp_path / "test.db"
    test_engine = create_async_engine(
        f"sqlite+aiosqlite:///{database_path.as_posix()}",
        poolclass=NullPool,
    )
    session_factory = async_sessionmaker(
        bind=test_engine,
        expire_on_commit=False,
        autoflush=False,
    )

    async def prepare_database() -> None:
        async with test_engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)

    async def override_db_session():
        async with session_factory() as session:
            try:
                yield session
            except Exception:
                await session.rollback()
                raise

    asyncio.run(prepare_database())
    app.dependency_overrides[get_db_session] = override_db_session

    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.pop(get_db_session, None)
        asyncio.run(test_engine.dispose())


@pytest.fixture
def created_divination_ids():
    """收集本测试中创建的解卦 ID，teardown 时统一删除。

    使用方式：测试中拿到响应后 append 进去即可。
        def test_x(client, created_divination_ids):
            r = client.post("/divinations", json={...})
            created_divination_ids.append(r.json()["divination_id"])
    """
    ids: list[str] = []
    yield ids
    # teardown：清理 JSON + MD 文件
    for div_id in ids:
        try:
            divination_store.delete(div_id)
        except Exception:
            pass
