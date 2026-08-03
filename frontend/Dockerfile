ARG NODE_BASE_IMAGE=node:22-alpine
FROM ${NODE_BASE_IMAGE} AS builder

WORKDIR /app

# 先安装锁定版本的依赖，便于复用 Docker 构建缓存。
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci

COPY frontend/ ./

# 浏览器统一请求同源的 /api，由 Caddy 转发到后端。
ARG NEXT_PUBLIC_API_BASE_URL=/api
ENV NEXT_PUBLIC_API_BASE_URL=${NEXT_PUBLIC_API_BASE_URL}

# vinext 的 standalone 输出包含生产运行所需的最小文件集合。
RUN npm run build

FROM ${NODE_BASE_IMAGE} AS runtime

# 生产容器监听所有网卡上的 3000 端口，但仅在 Docker 内部网络暴露。
ENV NODE_ENV=production \
    HOST=0.0.0.0 \
    PORT=3000

WORKDIR /app

# 运行阶段不复制源码和完整 node_modules，以减小最终镜像体积。
COPY --from=builder --chown=node:node /app/dist/standalone ./

USER node

EXPOSE 3000

# 由容器内部访问首页，供 Compose 判断前端是否已就绪。
HEALTHCHECK --interval=15s --timeout=5s --start-period=20s --retries=5 \
    CMD ["node", "-e", "fetch('http://127.0.0.1:3000/').then(r => { if (!r.ok) process.exit(1) }).catch(() => process.exit(1))"]

CMD ["node", "server.js"]
