# syntax=docker/dockerfile:1.7

ARG CADDY_BASE_IMAGE=caddy:2-alpine
FROM ${CADDY_BASE_IMAGE}

ARG APK_MIRROR=https://mirrors.aliyun.com/alpine

# Caddy 访问日志也统一使用东八区时间。
ENV TZ=Asia/Shanghai

RUN sed -i \
        -e "s|https://dl-cdn.alpinelinux.org/alpine|${APK_MIRROR}|g" \
        -e "s|http://dl-cdn.alpinelinux.org/alpine|${APK_MIRROR}|g" \
        /etc/apk/repositories \
    && apk add --no-cache --no-progress tzdata \
    && ln -snf /usr/share/zoneinfo/Asia/Shanghai /etc/localtime \
    && echo "Asia/Shanghai" > /etc/timezone
