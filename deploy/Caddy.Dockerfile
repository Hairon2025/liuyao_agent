ARG CADDY_BASE_IMAGE=caddy:2-alpine
FROM ${CADDY_BASE_IMAGE}

# Caddy 访问日志也统一使用东八区时间。
ENV TZ=Asia/Shanghai

RUN apk add --no-cache tzdata \
    && ln -snf /usr/share/zoneinfo/Asia/Shanghai /etc/localtime \
    && echo "Asia/Shanghai" > /etc/timezone
