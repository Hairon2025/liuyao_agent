"""全局配置（从环境变量读取）"""
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

_BACKEND_DIR = Path(__file__).resolve().parents[1]
_DEFAULT_DATABASE_PATH = _BACKEND_DIR / "running_data" / "liuyao.db"


class Settings(BaseSettings):
    """项目配置"""

    app_name: str = "liuyao-agent"
    app_version: str = "0.1.0"
    debug: bool = False

    # LLM 配置。Pydantic Settings 会自动读取同名环境变量。
    llm_api_key: str = ""
    llm_base_url: str = "https://api.openai.com/v1"
    llm_model: str = "gpt-4o"

    # 数据库配置。默认使用 backend/running_data/liuyao.db。
    database_url: str = f"sqlite+aiosqlite:///{_DEFAULT_DATABASE_PATH.as_posix()}"

    # 日志
    log_level: str = "INFO"

    # CORS
    cors_origins: list[str] = ["*"]

    model_config = SettingsConfigDict(
        env_file=_BACKEND_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
