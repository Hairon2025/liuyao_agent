ARG PYTHON_BASE_IMAGE=python:3.12-slim
FROM ${PYTHON_BASE_IMAGE} AS runtime

# 默认使用清华大学 PyPI 镜像；构建时可通过 PIP_INDEX_URL 覆盖。
ARG PIP_INDEX_URL=https://mirrors.tuna.tsinghua.edu.cn/pypi/web/simple

# 关闭 .pyc 文件并让日志立即输出到容器日志。
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_INDEX_URL=${PIP_INDEX_URL} \
    TZ=Asia/Shanghai

WORKDIR /app

# 安装东八区时区数据，使日志和 datetime.now() 使用北京时间。
RUN apt-get update \
    && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends tzdata \
    && ln -snf /usr/share/zoneinfo/Asia/Shanghai /etc/localtime \
    && echo "Asia/Shanghai" > /etc/timezone \
    && rm -rf /var/lib/apt/lists/*

# 使用固定 UID/GID 的非 root 用户运行后端，降低容器权限。
RUN groupadd --gid 10001 app \
    && useradd --uid 10001 --gid app --create-home --shell /usr/sbin/nologin app

# 先复制依赖清单，业务代码变化时可以复用依赖安装缓存。
COPY backend/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

# 保留 backend 包目录，使容器内仍可通过 backend.xxx 进行绝对导入。
COPY --chown=app:app backend /app/backend

# /data 保存 SQLite 与加密密钥；/app/logs 保存应用日志。
RUN mkdir -p /app/logs /data \
    && chown -R app:app /app/logs /data \
    && chmod +x /app/backend/docker-entrypoint.sh

USER app

EXPOSE 8022

# 健康检查只在容器内部访问 FastAPI，不向公网开放 8022。
HEALTHCHECK --interval=15s --timeout=5s --start-period=30s --retries=5 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8022/health', timeout=3)"]

# 入口脚本会先运行 Alembic 迁移，再启动 Uvicorn。
ENTRYPOINT ["/app/backend/docker-entrypoint.sh"]
