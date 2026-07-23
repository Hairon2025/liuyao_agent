"""FastAPI 应用入口"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.routes import divination, health
from config.settings import settings
from utils.logger import logger


app = FastAPI(
    title="六爻解卦助手 API",
    description="基于多 Agent 协作的六爻解卦服务",
    version="0.1.0",
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


@app.on_event("startup")
async def startup():
    logger.info(f"启动 {settings.app_name} v{settings.app_version}")


@app.on_event("shutdown")
async def shutdown():
    logger.info(f"关闭 {settings.app_name}")
