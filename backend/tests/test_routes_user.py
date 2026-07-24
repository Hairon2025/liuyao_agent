"""User 路由测试。"""
from __future__ import annotations

import uuid
from typing import Any


def _create_guest(client: Any, display_name: str | None = None) -> dict:
    payload = {} if display_name is None else {"display_name": display_name}
    response = client.post("/users/guests", json=payload)
    assert response.status_code == 201, response.text
    return response.json()


class TestCreateGuestUser:
    """POST /users/guests"""

    def test_create_guest_generates_server_side_id(self, client: Any):
        body = _create_guest(client, "  问卦者  ")

        assert uuid.UUID(body["id"])
        assert body["user_type"] == "guest"
        assert body["display_name"] == "问卦者"
        assert body["is_active"] is True
        assert body["created_at"]
        assert body["updated_at"]

    def test_create_guest_allows_missing_display_name(self, client: Any):
        body = _create_guest(client)
        assert body["display_name"] is None

    def test_create_guest_rejects_blank_display_name(self, client: Any):
        response = client.post(
            "/users/guests",
            json={"display_name": "   "},
        )
        assert response.status_code == 422
        assert "昵称不能只包含空白字符" in response.text

    def test_create_guest_rejects_client_supplied_identity(self, client: Any):
        response = client.post(
            "/users/guests",
            json={"id": str(uuid.uuid4()), "user_type": "registered"},
        )
        assert response.status_code == 422


class TestGetUser:
    """GET /users/{user_id}"""

    def test_get_existing_user(self, client: Any):
        created = _create_guest(client, "测试用户")

        response = client.get(f"/users/{created['id']}")

        assert response.status_code == 200
        assert response.json() == created

    def test_get_missing_user_returns_404(self, client: Any):
        missing_id = uuid.uuid4()
        response = client.get(f"/users/{missing_id}")

        assert response.status_code == 404
        assert str(missing_id) in response.json()["detail"]

    def test_get_invalid_uuid_returns_422(self, client: Any):
        response = client.get("/users/not-a-uuid")
        assert response.status_code == 422


class TestUpdateUser:
    """PATCH /users/{user_id}"""

    def test_update_display_name(self, client: Any):
        created = _create_guest(client)

        response = client.patch(
            f"/users/{created['id']}",
            json={"display_name": "  新昵称  "},
        )

        assert response.status_code == 200
        assert response.json()["display_name"] == "新昵称"

    def test_clear_display_name_with_null(self, client: Any):
        created = _create_guest(client, "原昵称")

        response = client.patch(
            f"/users/{created['id']}",
            json={"display_name": None},
        )

        assert response.status_code == 200
        assert response.json()["display_name"] is None

    def test_empty_update_returns_400(self, client: Any):
        created = _create_guest(client)
        response = client.patch(f"/users/{created['id']}", json={})

        assert response.status_code == 400
        assert "至少提供一个" in response.json()["detail"]

    def test_update_missing_user_returns_404(self, client: Any):
        missing_id = uuid.uuid4()
        response = client.patch(
            f"/users/{missing_id}",
            json={"display_name": "不存在"},
        )

        assert response.status_code == 404
