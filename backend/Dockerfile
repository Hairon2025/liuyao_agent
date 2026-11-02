# syntax=docker/dockerfile:1.7

# 固定 Debian 发行版，避免 python:3.12-slim 随上游切换后导致软件源配置变化。
ARG PYTHON_BASE_IMAGE=python:3.12-slim-bookworm
FROM ${PYTHON_BASE_IMAGE} AS runtime

# 默认使用清华大学 PyPI 镜像；构建时可通过 PIP_INDEX_URL 覆盖。
ARG PIP_INDEX_URL=https://mirrors.tuna.tsinghua.edu.cn/pypi/web/simple
# apt 与 PyPI 使用不同的软件源。国内云服务器默认使用阿里 Debian 镜像，
# 构建时仍可通过 Compose 环境变量覆盖为其他镜像。
ARG APT_MIRROR=https://mirrors.aliyun.com/debian
ARG APT_SECURITY_MIRROR=https://mirrors.aliyun.com/debian-security

# 关闭 .pyc 文件并让日志立即输出到容器日志。
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_INDEX_URL=${PIP_INDEX_URL} \
    TZ=Asia/Shanghai

WORKDIR /app

# 安装东八区时区数据，使日志和 datetime.now() 使用北京时间。
# BuildKit 缓存 apt 索引与安装包，重建时无需重复下载；重试和超时参数可以避免
# 网络异常时长时间无响应。先替换 security 源，避免被普通 Debian 源规则误匹配。
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt/lists,sharing=locked \
    rm -f /etc/apt/apt.conf.d/docker-clean \
    && sed -i \
        -e "s|http://deb.debian.org/debian-security|${APT_SECURITY_MIRROR}|g" \
        -e "s|https://deb.debian.org/debian-security|${APT_SECURITY_MIRROR}|g" \
        -e "s|http://security.debian.org/debian-security|${APT_SECURITY_MIRROR}|g" \
        -e "s|https://security.debian.org/debian-security|${APT_SECURITY_MIRROR}|g" \
        -e "s|http://deb.debian.org/debian|${APT_MIRROR}|g" \
        -e "s|https://deb.debian.org/debian|${APT_MIRROR}|g" \
        /etc/apt/sources.list.d/debian.sources \
    && apt-get \
        -o Acquire::Retries=5 \
        -o Acquire::ForceIPv4=true \
        -o Acquire::http::Timeout=30 \
        -o Acquire::https::Timeout=30 \
        update \
    && DEBIAN_FRONTEND=noninteractive apt-get \
        -o Acquire::Retries=5 \
        -o Acquire::ForceIPv4=true \
        -o Acquire::http::Timeout=30 \
        -o Acquire::https::Timeout=30 \
        install -y --no-install-recommends tzdata \
    && ln -snf /usr/share/zoneinfo/Asia/Shanghai /etc/localtime \
    && echo "Asia/Shanghai" > /etc/timezone

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
