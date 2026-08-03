# Docker 部署指南（公网 IP + HTTP 测试）

本指南对应仓库根目录的 `compose.yaml`。当前方案用于没有域名时验证 Docker
部署链路，统一通过 `http://服务器公网IP:8080` 访问：

- `/`：前端；
- `/api/*`：FastAPI；
- SQLite 与本地加密主密钥：Docker 命名卷 `liuyao_data`。

> 这是 HTTP 测试方案。请勿在这一阶段保存长期使用的真实生产密钥；有域名后应
> 切换 HTTPS，并把 `AUTH_COOKIE_SECURE` 改为 `true`。

## 1. 服务器准备

以下命令都在仓库根目录执行。服务器需要安装 Docker Engine、Buildx 和
Docker Compose 插件。安装完成后确认：

```bash
docker --version
docker compose version
```

云厂商安全组只需放行：

- `22/tcp`：SSH；
- `8080/tcp`：当前 HTTP 测试站点。

不要放行 `3000` 和 `8022`，它们只用于 Docker 内部网络。

## 2. 获取项目与创建运行配置

```bash
git clone https://github.com/Hairon2025/liuyao_agent.git
cd liuyao_agent
cp deploy/backend.env.example deploy/backend.env
```

测试阶段可以直接使用模板。默认行为是首次启动时在 `liuyao_data` 数据卷里生成
`.user_llm_encryption_key`。

如需主动固定主密钥，先执行：

```bash
openssl rand -hex 32
```

再把结果填写到 `deploy/backend.env` 的：

```env
USER_LLM_ENCRYPTION_KEY=生成的值
```

`deploy/backend.env` 已被 Git 忽略，不能提交到仓库。

## 3. 构建与启动

```bash
docker compose config --quiet
docker compose build
docker compose up -d
docker compose ps
```

Compose 默认将 Caddy 映射到服务器的 `8080` 端口。如果需要使用其他端口，例如
`9000`，可以执行：

```bash
LIUYAO_HTTP_PORT=9000 docker compose up -d
```

后端容器每次启动都会先执行：

```bash
python -m alembic -c backend/alembic.ini upgrade head
```

迁移成功后才会启动 Uvicorn。首次构建会下载 Python、Node 和 Caddy 基础镜像，
耗时取决于服务器网络。

## 4. 验证

把 `SERVER_IP` 替换成公网 IP：

```bash
curl http://SERVER_IP:8080/healthz
curl http://SERVER_IP:8080/api/health
```

预期都返回成功。浏览器访问：

```text
http://SERVER_IP:8080
```

Swagger：

```text
http://SERVER_IP:8080/api/docs
```

查看状态和日志：

```bash
docker compose ps
docker compose logs -f backend
docker compose logs -f frontend
docker compose logs -f caddy
```

退出持续日志使用 `Ctrl+C`，不会停止容器。

## 5. 常用维护命令

更新代码并重建：

```bash
git pull
docker compose build
docker compose up -d
```

只重建前端：

```bash
docker compose build frontend
docker compose up -d frontend
```

重启：

```bash
docker compose restart
```

停止但保留数据库：

```bash
docker compose down
```

不要执行下面的命令，`-v` 会删除 SQLite 数据卷：

```bash
docker compose down -v
```

## 6. SQLite 数据与备份

容器中的数据库位置：

```text
/data/liuyao.db
```

查看数据卷：

```bash
docker volume ls
docker volume inspect liuyao-agent_liuyao_data
```

SQLite 当前只适合运行一个后端容器，不要执行：

```bash
docker compose up -d --scale backend=2
```

备份必须同时保证以下内容不会丢失：

- SQLite 数据库；
- `USER_LLM_ENCRYPTION_KEY`，或者数据卷中的
  `.user_llm_encryption_key`。

缺少加密主密钥时，已保存的用户 LLM API Key 无法恢复。

## 7. 将来切换域名和 HTTPS

获得域名后：

1. 把域名 A 记录指向服务器；
2. 将 `deploy/Caddyfile` 的 `:80` 改为域名，例如 `example.com`；
3. 在 `compose.yaml` 为 Caddy 增加 `80:80` 和 `443:443`；
4. 将 `deploy/backend.env` 中 `AUTH_COOKIE_SECURE` 改为 `true`；
5. 设置固定的 `USER_LLM_ENCRYPTION_KEY`；
6. 重新执行 `docker compose up -d`。

前端使用相对地址 `/api`，因此切换域名时不需要修改或重新写死 API 域名。

## 8. 故障排查

### Caddy 一直未启动

先看依赖服务是否健康：

```bash
docker compose ps
docker compose logs backend
docker compose logs frontend
```

### 8080 端口被占用

服务器已有其他服务监听 8080。可以通过环境变量换一个宿主机端口，例如：

```bash
LIUYAO_HTTP_PORT=9000 docker compose up -d
```

然后访问 `http://SERVER_IP:9000`，并在云服务器安全组中放行对应端口。

### 前端能打开但 API 失败

检查：

```bash
curl http://SERVER_IP:8080/api/health
docker compose logs backend
docker compose logs caddy
```

前端镜像必须使用构建参数 `NEXT_PUBLIC_API_BASE_URL=/api`；仓库中的
`compose.yaml` 已经配置。

### Docker Hub 镜像源失效

如果日志显示请求某个第三方 Docker Hub 镜像站失败，可以先修复服务器的 Docker
Registry Mirror。也可以临时通过环境变量覆盖基础镜像来源；`compose.yaml` 支持：

```text
PYTHON_BASE_IMAGE
NODE_BASE_IMAGE
CADDY_IMAGE
```

未设置时始终使用官方 `python:3.12-slim`、`node:22-alpine` 和
`caddy:2-alpine`。
