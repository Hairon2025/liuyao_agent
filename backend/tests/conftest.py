"""pytest 共享 fixtures

提供：
- client: 使用独立数据库和默认访客身份的 TestClient
- created_divination_ids: 兼容现有测试的 ID 收集列表
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
            # 模拟前端首次访问：创建访客，并把临时身份放入后续请求头。
            guest_response = test_client.post("/users/guests", json={})
            assert guest_response.status_code == 201
            test_client.headers["X-User-ID"] = guest_response.json()["id"]
            yield test_client
    finally:
        app.dependency_overrides.pop(get_db_session, None)
        asyncio.run(test_engine.dispose())


@pytest.fixture
def created_divination_ids():
    """收集本测试中创建的卦例 ID。

    每个测试已经使用独立临时数据库，无需额外清理；保留该 fixture 可以避免
    大量业务断言掺杂与本次存储迁移无关的改动。
    """
    ids: list[str] = []
    yield ids
