"""pytest 共享 fixtures

提供：
- client: FastAPI TestClient 实例（按 request 级别隔离）
- created_divination_ids: 自动收集本测试创建的 ID，teardown 时清理
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from api.server import app
from running_data import divination_store


@pytest.fixture
def client() -> TestClient:
    """FastAPI TestClient 实例。"""
    return TestClient(app)


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