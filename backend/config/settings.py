"""全局配置（从环境变量读取）"""
from pathlib import Path

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_BACKEND_DIR = Path(__file__).resolve().parents[1]
_DEFAULT_DATABASE_PATH = _BACKEND_DIR / "running_data" / "liuyao.db"
_DEFAULT_ENCRYPTION_KEY_PATH = (
    _BACKEND_DIR / "running_data" / ".user_llm_encryption_key"
)


class Settings(BaseSettings):
    """项目配置"""

    app_name: str = "liuyao-agent"
    app_version: str = "0.1.0"
    debug: bool = False
    root_path: str = ""

    # LLM 配置。Pydantic Settings 会自动读取同名环境变量。
    llm_api_key: str = ""
    llm_base_url: str = "https://api.openai.com/v1"
    llm_model: str = "gpt-4o"
    llm_timeout_seconds: float = 120.0

    # 追问建议可以使用独立的低成本 OpenAI-compatible 模型。
    # 留空时逐项回退到上面的主 LLM 配置。
    suggestion_llm_api_key: str | None = None
    suggestion_llm_base_url: str | None = None
    suggestion_llm_model: str | None = None
    suggestion_llm_timeout_seconds: float | None = None
    suggestion_context_max_chars: int = 1400
    suggestion_user_message_max_chars: int = 300

    # 长期记忆摘要模型；留空时逐项回退到主 LLM 配置。
    memory_llm_api_key: str | None = None
    memory_llm_base_url: str | None = None
    memory_llm_model: str | None = None
    memory_llm_timeout_seconds: float | None = None
    memory_summary_trigger_items: int = 10
    memory_summary_keep_recent_items: int = 5
    memory_summary_input_max_chars: int = 16000

    # OpenAI Agents SDK：限制一次运行的 turn 数和读取的最近 Session Item 数。
    chat_max_steps: int = 6
    chat_context_recent_limit: int = 50

    # 登录 Session 与用户自带 LLM 密钥。
    auth_cookie_name: str = "liuyao_session"
    auth_session_days: int = 30
    auth_cookie_secure: bool = False
    auth_cookie_samesite: str = "lax"
    user_llm_encryption_key: str = ""
    user_llm_encryption_key_file: Path = _DEFAULT_ENCRYPTION_KEY_PATH
    allow_private_llm_base_urls: bool = False

    # 数据库配置。默认使用 backend/running_data/liuyao.db。
    database_url: str = f"sqlite+aiosqlite:///{_DEFAULT_DATABASE_PATH.as_posix()}"

    # 日志
    log_level: str = "INFO"

    # CORS
    cors_origins: list[str] = [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ]

    @property
    def effective_memory_llm_api_key(self) -> str:
        return self.memory_llm_api_key or self.llm_api_key

    @property
    def effective_memory_llm_base_url(self) -> str:
        return self.memory_llm_base_url or self.llm_base_url

    @property
    def effective_memory_llm_model(self) -> str:
        return self.memory_llm_model or self.llm_model

    @property
    def effective_memory_llm_timeout_seconds(self) -> float:
        return (
            self.memory_llm_timeout_seconds
            if self.memory_llm_timeout_seconds is not None
            else self.llm_timeout_seconds
        )

    @model_validator(mode="after")
    def validate_memory_limits(self) -> "Settings":
        """确保摘要阈值不会在最近上下文窗口之外留下记忆缺口。"""
        if self.memory_summary_keep_recent_items < 1:
            raise ValueError(
                "MEMORY_SUMMARY_KEEP_RECENT_ITEMS 必须大于等于 1"
            )
        if (
            self.memory_summary_keep_recent_items
            >= self.memory_summary_trigger_items
        ):
            raise ValueError(
                "MEMORY_SUMMARY_KEEP_RECENT_ITEMS 必须小于 "
                "MEMORY_SUMMARY_TRIGGER_ITEMS"
            )
        if (
            self.memory_summary_trigger_items
            > self.chat_context_recent_limit
        ):
            raise ValueError(
                "MEMORY_SUMMARY_TRIGGER_ITEMS 不能大于 "
                "CHAT_CONTEXT_RECENT_LIMIT"
            )
        if self.auth_session_days < 1:
            raise ValueError("AUTH_SESSION_DAYS 必须大于等于 1")
        if self.auth_cookie_samesite not in {"lax", "strict", "none"}:
            raise ValueError(
                "AUTH_COOKIE_SAMESITE 必须是 lax、strict 或 none"
            )
        if self.auth_cookie_samesite == "none" and not self.auth_cookie_secure:
            raise ValueError(
                "AUTH_COOKIE_SAMESITE=none 时必须启用 AUTH_COOKIE_SECURE"
            )
        return self

    model_config = SettingsConfigDict(
        env_file=_BACKEND_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
