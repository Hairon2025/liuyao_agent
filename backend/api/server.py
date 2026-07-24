"""FastAPI 应用入口"""
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.api.routes import divination, health, user
from backend.config.settings import settings
from backend.utils.logger import logger


@asynccontextmanager
async def lifespan(_: FastAPI):
    """统一管理应用启动与关闭事件。"""
    logger.info(f"启动 {settings.app_name} v{settings.app_version}")
    yield
    logger.info(f"关闭 {settings.app_name}")


app = FastAPI(
    title="六爻解卦助手 API",
    description="基于多 Agent 协作的六爻解卦服务",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(divination.router)
app.include_router(user.router)
