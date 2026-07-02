"""全局配置（从环境变量读取）"""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """项目配置"""

    app_name: str = "liuyao-agent"
    app_version: str = "0.1.0"
    debug: bool = False

    # LLM 配置
    llm_api_key: str = ""
    llm_base_url: str = ""
    llm_model: str = "gpt-4o"

    # 日志
    log_level: str = "INFO"

    # CORS
    cors_origins: list[str] = ["*"]

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


settings = Settings()
