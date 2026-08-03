"""密码凭证和用户 LLM 密钥相关安全工具测试。"""
from __future__ import annotations

import stat

import pytest

from backend.utils.security import (
    CredentialCipher,
    load_or_create_encryption_secret,
)


def test_local_encryption_secret_is_persistent_and_private(tmp_path):
    key_path = tmp_path / ".user_llm_encryption_key"

    first = load_or_create_encryption_secret(key_path)
    second = load_or_create_encryption_secret(key_path)

    assert first == second
    assert len(first.encode("utf-8")) >= 32
    assert stat.S_IMODE(key_path.stat().st_mode) == 0o600


def test_local_encryption_secret_rejects_invalid_existing_file(tmp_path):
    key_path = tmp_path / ".user_llm_encryption_key"
    key_path.write_text("too-short", encoding="utf-8")

    with pytest.raises(ValueError, match="本地主密钥文件内容无效"):
        load_or_create_encryption_secret(key_path)


def test_credential_cipher_round_trip():
    cipher = CredentialCipher("a-stable-secret-that-is-longer-than-32-bytes")

    encrypted = cipher.encrypt("sk-private-value")

    assert "sk-private-value" not in encrypted
    assert cipher.decrypt(encrypted) == "sk-private-value"
