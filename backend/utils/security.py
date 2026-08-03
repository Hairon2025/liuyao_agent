"""密码、登录 Token 与用户 LLM 密钥的安全工具。"""
from __future__ import annotations

import base64
import hashlib
import ipaddress
import os
import secrets
from pathlib import Path
from urllib.parse import urlparse

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHash, VerifyMismatchError
from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM


_PASSWORD_HASHER = PasswordHasher()
_CIPHER_PREFIX = "v1."
_CIPHER_AAD = b"liuyao:user-llm:v1"


def normalize_username(username: str) -> str:
    """登录名不区分大小写；展示时仍保留用户原始写法。"""
    return username.strip().casefold()


def hash_password(password: str) -> str:
    return _PASSWORD_HASHER.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    try:
        return _PASSWORD_HASHER.verify(password_hash, password)
    except (VerifyMismatchError, InvalidHash):
        return False


def generate_session_token() -> str:
    """生成高熵 Cookie Token；数据库只保存其 SHA-256。"""
    return secrets.token_urlsafe(48)


def hash_session_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def load_or_create_encryption_secret(path: Path) -> str:
    """读取本地主密钥；不存在时以 0600 权限原子创建。

    这是未显式配置环境变量时的本地开发兜底。生产环境仍应通过
    ``USER_LLM_ENCRYPTION_KEY`` 注入并妥善备份。
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    generated = secrets.token_urlsafe(48)
    try:
        file_descriptor = os.open(
            path,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL,
            0o600,
        )
    except FileExistsError:
        secret = path.read_text(encoding="utf-8").strip()
    else:
        try:
            os.write(file_descriptor, generated.encode("utf-8"))
            os.fsync(file_descriptor)
        finally:
            os.close(file_descriptor)
        secret = generated

    if len(secret.encode("utf-8")) < 32:
        raise ValueError(f"本地主密钥文件内容无效：{path}")
    return secret


class CredentialCipher:
    """使用服务端主密钥对用户 API Key 做 AES-GCM 可逆加密。"""

    def __init__(self, master_secret: str):
        if len(master_secret.encode("utf-8")) < 32:
            raise ValueError("USER_LLM_ENCRYPTION_KEY 至少需要 32 字节")
        self._key = hashlib.sha256(master_secret.encode("utf-8")).digest()

    def encrypt(self, plaintext: str) -> str:
        nonce = secrets.token_bytes(12)
        ciphertext = AESGCM(self._key).encrypt(
            nonce,
            plaintext.encode("utf-8"),
            _CIPHER_AAD,
        )
        encoded = base64.urlsafe_b64encode(nonce + ciphertext).decode("ascii")
        return f"{_CIPHER_PREFIX}{encoded}"

    def decrypt(self, encrypted: str) -> str:
        if not encrypted.startswith(_CIPHER_PREFIX):
            raise ValueError("不支持的密钥密文版本")
        try:
            payload = base64.urlsafe_b64decode(
                encrypted.removeprefix(_CIPHER_PREFIX).encode("ascii")
            )
            plaintext = AESGCM(self._key).decrypt(
                payload[:12],
                payload[12:],
                _CIPHER_AAD,
            )
        except (ValueError, InvalidTag) as exc:
            raise ValueError("用户 API Key 解密失败") from exc
        return plaintext.decode("utf-8")


def validate_llm_base_url(value: str, *, allow_private: bool) -> str:
    """校验 Base URL，并拦截显式本机、内网和保留 IP。"""
    normalized = value.strip().rstrip("/")
    parsed = urlparse(normalized)
    allowed_schemes = {"https"} | ({"http"} if allow_private else set())
    if parsed.scheme not in allowed_schemes or not parsed.hostname:
        raise ValueError("Base URL 必须是有效的 HTTPS 地址")
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError("Base URL 不能包含账号、查询参数或片段")

    hostname = parsed.hostname.casefold()
    if not allow_private and (
        hostname in {"localhost", "localhost.localdomain"}
        or hostname.endswith((".localhost", ".local", ".internal"))
    ):
        raise ValueError("Base URL 不能指向本机或内网地址")
    try:
        address = ipaddress.ip_address(hostname)
    except ValueError:
        address = None
    if address is not None and not allow_private and not address.is_global:
        raise ValueError("Base URL 不能指向本机、内网或保留 IP")
    return normalized
