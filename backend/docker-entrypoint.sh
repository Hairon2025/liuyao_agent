#!/bin/sh
set -eu

# 每次容器启动先应用迁移；Alembic 会自动跳过已经执行的版本。
python -m alembic -c backend/alembic.ini upgrade head

exec python -m uvicorn backend.api.server:app \
  --host 0.0.0.0 \
  --port 8022 \
  --proxy-headers \
  --forwarded-allow-ips="*"

