"""FastAPI 依赖注入"""
from backend.config.settings import settings


def get_settings():
    return settings
