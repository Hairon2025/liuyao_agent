ARG NODE_BASE_IMAGE=node:22-alpine
FROM ${NODE_BASE_IMAGE} AS builder

ARG NPM_REGISTRY=https://registry.npmmirror.com

WORKDIR /app

# 默认使用阿里 npmmirror 安装锁定版本的依赖；构建时可覆盖 NPM_REGISTRY。
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --registry="${NPM_REGISTRY}"

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
    PORT=3000 \
    TZ=Asia/Shanghai

WORKDIR /app

# 安装东八区时区数据，确保 Node 服务端日志使用北京时间。
RUN apk add --no-cache tzdata \
    && ln -snf /usr/share/zoneinfo/Asia/Shanghai /etc/localtime \
    && echo "Asia/Shanghai" > /etc/timezone

# 运行阶段不复制源码和完整 node_modules，以减小最终镜像体积。
COPY --from=builder --chown=node:node /app/dist/standalone ./

USER node

EXPOSE 3000

# 由容器内部访问首页，供 Compose 判断前端是否已就绪。
HEALTHCHECK --interval=15s --timeout=5s --start-period=20s --retries=5 \
    CMD ["node", "-e", "fetch('http://127.0.0.1:3000/').then(r => { if (!r.ok) process.exit(1) }).catch(() => process.exit(1))"]

CMD ["node", "server.js"]
