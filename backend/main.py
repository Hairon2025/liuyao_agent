"""项目启动入口：python main.py"""
import uvicorn

from backend.config.settings import settings


def main():
    uvicorn.run(
        "backend.api.server:app",
        host="127.0.0.1",
        port=8022,
        reload=settings.debug,
    )


if __name__ == "__main__":
    main()
