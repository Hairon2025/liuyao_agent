"""认证、当前用户资料和用户 LLM 设置路由测试。"""
from __future__ import annotations


def test_current_registered_user_and_profile_update(client):
    current = client.get("/auth/me")
    assert current.status_code == 200
    assert current.json()["user"]["username"] == "test_user"
    assert current.json()["user"]["user_type"] == "registered"

    updated = client.patch("/users/me", json={"display_name": "  问卦者  "})
    assert updated.status_code == 200
    assert updated.json()["display_name"] == "问卦者"


def test_guest_registration_upgrades_same_user_and_preserves_data(client):
    assert client.post("/auth/logout").status_code == 204
    guest = client.post("/auth/guests", json={"display_name": "游客"})
    guest_id = guest.json()["user"]["id"]
    created = client.post(
        "/divinations",
        json={
            "method": "manual",
            "question": "注册前的卦",
            "numbers": [2, 1, 2, 2, 1, 2],
        },
    )
    assert created.status_code == 200

    registered = client.post(
        "/auth/register",
        json={
            "username": "upgraded_user",
            "password": "password123",
        },
    )
    assert registered.status_code == 201
    assert registered.json()["user"]["id"] == guest_id
    assert registered.json()["user"]["user_type"] == "registered"
    assert created.json()["divination_id"] in client.get("/divinations").json()


def test_login_logout_and_invalid_password(client):
    assert client.post("/auth/logout").status_code == 204
    assert client.get("/auth/me").status_code == 401
    invalid = client.post(
        "/auth/login",
        json={"username": "test_user", "password": "wrong-password"},
    )
    assert invalid.status_code == 401

    logged_in = client.post(
        "/auth/login",
        json={"username": "TEST_USER", "password": "password123"},
    )
    assert logged_in.status_code == 200
    assert logged_in.json()["user"]["username"] == "test_user"


def test_guest_login_existing_account_preserves_guest_divination(client):
    """游客排盘后登录已有账号，原卦例应直接归入该账号。"""
    registered_user_id = client.get("/auth/me").json()["user"]["id"]
    assert client.post("/auth/logout").status_code == 204

    guest = client.post("/auth/guests", json={})
    assert guest.status_code == 201
    guest_user_id = guest.json()["user"]["id"]
    assert guest_user_id != registered_user_id

    created = client.post(
        "/divinations",
        json={
            "method": "manual",
            "question": "游客登录前排好的卦",
            "numbers": [2, 1, 2, 2, 1, 2],
            "generate_markdown": True,
        },
    )
    assert created.status_code == 200
    divination_id = created.json()["divination_id"]

    logged_in = client.post(
        "/auth/login",
        json={"username": "test_user", "password": "password123"},
    )
    assert logged_in.status_code == 200
    assert logged_in.json()["user"]["id"] == registered_user_id

    loaded = client.get(f"/divinations/{divination_id}")
    assert loaded.status_code == 200
    assert loaded.json()["paipan"]["question"] == "游客登录前排好的卦"
    assert divination_id in client.get("/divinations").json()


def test_duplicate_username_is_rejected(client):
    client.post("/auth/logout")
    client.post("/auth/guests", json={})
    duplicate = client.post(
        "/auth/register",
        json={"username": "TEST_USER", "password": "password123"},
    )
    assert duplicate.status_code == 409


def test_registration_validates_username_and_password(client):
    client.post("/auth/logout")
    client.post("/auth/guests", json={})
    invalid_name = client.post(
        "/auth/register",
        json={"username": "中文用户名", "password": "password123"},
    )
    assert invalid_name.status_code == 422
    short_password = client.post(
        "/auth/register",
        json={"username": "valid_name", "password": "short"},
    )
    assert short_password.status_code == 422


def test_guest_cannot_use_ai_or_manage_llm_settings(client):
    client.post("/auth/logout")
    client.post("/auth/guests", json={})
    assert client.get("/users/me/llm-settings").status_code == 403
    assert client.post("/chat/sessions", json={}).status_code == 403

    divination = client.post(
        "/divinations",
        json={
            "method": "manual",
            "question": "游客排盘",
            "numbers": [2, 1, 2, 2, 1, 2],
            "generate_markdown": True,
        },
    )
    assert divination.status_code == 200
    divination_id = divination.json()["divination_id"]
    assert client.post(
        f"/divinations/{divination_id}/interpret"
    ).status_code == 403


def test_registered_user_without_llm_settings_is_prompted_to_configure(client):
    assert client.delete("/users/me/llm-settings").status_code == 204
    assert client.get("/users/me/llm-settings").json() is None
    response = client.post("/chat/sessions", json={})
    assert response.status_code == 428
    assert "配置 LLM" in response.json()["detail"]


def test_llm_settings_never_return_api_key_and_can_preserve_existing_key(client):
    current = client.get("/users/me/llm-settings")
    assert current.status_code == 200
    assert current.json()["api_key_last4"] == "-key"
    assert current.json()["suggestion_enabled"] is True
    assert "api_key" not in current.json()
    assert "ciphertext" not in current.text

    updated = client.put(
        "/users/me/llm-settings",
        json={
            "base_url": "https://another.example.com/v1",
            "model": "another-model",
            "memory_model": "cheap-memory",
            "suggestion_enabled": False,
        },
    )
    assert updated.status_code == 200
    assert updated.json()["api_key_last4"] == "-key"
    assert updated.json()["memory_model"] == "cheap-memory"
    assert updated.json()["suggestion_enabled"] is False


def test_llm_settings_reject_private_base_url(client):
    response = client.put(
        "/users/me/llm-settings",
        json={
            "base_url": "http://127.0.0.1:11434/v1",
            "api_key": "local-key",
            "model": "local-model",
        },
    )
    assert response.status_code == 400
    assert "Base URL" in response.json()["detail"]
