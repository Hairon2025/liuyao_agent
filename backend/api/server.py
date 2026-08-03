"""FastAPI 应用入口"""
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.api.routes import auth, chat, divination, health, llm_settings, user
from backend.config.settings import settings
from backend.utils.logger import logger
from backend.utils.security import load_or_create_encryption_secret


@asynccontextmanager
async def lifespan(_: FastAPI):
    """统一管理应用启动与关闭事件。"""
    if not settings.user_llm_encryption_key:
        settings.user_llm_encryption_key = load_or_create_encryption_secret(
            settings.user_llm_encryption_key_file
        )
        logger.warning(
            "未配置 USER_LLM_ENCRYPTION_KEY，已使用本地持久化主密钥文件"
        )
    logger.info(f"启动 {settings.app_name} v{settings.app_version}")
    yield
    logger.info(f"关闭 {settings.app_name}")


app = FastAPI(
    title="六爻解卦助手 API",
    description="基于多 Agent 协作的六爻解卦服务",
    version="0.1.0",
    root_path=settings.root_path,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(auth.router)
app.include_router(divination.router)
app.include_router(user.router)
app.include_router(llm_settings.router)
app.include_router(chat.router)
