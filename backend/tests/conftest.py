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
from backend.config.settings import settings
from backend.db.base import Base
from backend.db.session import enable_sqlite_foreign_keys, get_db_session
import backend.models  # noqa: F401  # 确保测试建表时已注册全部 Model


@pytest.fixture
def client(tmp_path) -> TestClient:
    """使用独立临时 SQLite 数据库的 FastAPI TestClient。"""
    database_path = tmp_path / "test.db"
    test_engine = create_async_engine(
        f"sqlite+aiosqlite:///{database_path.as_posix()}",
        poolclass=NullPool,
    )
    enable_sqlite_foreign_keys(test_engine)
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
    previous_encryption_key = settings.user_llm_encryption_key
    settings.user_llm_encryption_key = "test-encryption-key-with-at-least-32-bytes"

    try:
        with TestClient(app) as test_client:
            # 默认测试身份模拟“游客原地注册并配置自己的模型”。
            guest_response = test_client.post("/auth/guests", json={})
            assert guest_response.status_code == 201
            register = test_client.post(
                "/auth/register",
                json={"username": "test_user", "password": "password123"},
            )
            assert register.status_code == 201, register.text
            configured = test_client.put(
                "/users/me/llm-settings",
                json={
                    "base_url": "https://llm.example.com/v1",
                    "api_key": "test-api-key",
                    "model": "test-model",
                },
            )
            assert configured.status_code == 200, configured.text
            yield test_client
    finally:
        settings.user_llm_encryption_key = previous_encryption_key
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
