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

构建时默认使用以下国内依赖源：

- Debian 系统包：阿里云 Debian 镜像；
- Alpine 系统包：阿里云 Alpine 镜像；
- Python：清华大学 PyPI 镜像；
- Node.js：阿里 `npmmirror`。

后端基础镜像固定为 `python:3.12-slim-bookworm`，避免上游 `slim` 标签切换
Debian 版本后，软件源格式和包版本在没有修改代码的情况下发生变化。

如需临时恢复官方依赖源，可以执行：

```bash
APT_MIRROR=http://deb.debian.org/debian \
APT_SECURITY_MIRROR=http://deb.debian.org/debian-security \
APK_MIRROR=https://dl-cdn.alpinelinux.org/alpine \
PIP_INDEX_URL=https://pypi.org/simple \
NPM_REGISTRY=https://registry.npmjs.org \
docker compose build
```

如果云服务器访问阿里源较慢，也可以切换清华 Debian/Alpine 镜像：

```bash
APT_MIRROR=https://mirrors.tuna.tsinghua.edu.cn/debian \
APT_SECURITY_MIRROR=https://mirrors.tuna.tsinghua.edu.cn/debian-security \
APK_MIRROR=https://mirrors.tuna.tsinghua.edu.cn/alpine \
docker compose build
```

查看完整构建进度，确认具体卡在哪个网络请求：

```bash
docker compose build --progress=plain backend
```

后端 `apt` 安装层设置了 30 秒单次连接超时、5 次自动重试，并使用 BuildKit
缓存 Debian 索引和安装包。因此短暂网络抖动会自动恢复，后续重建也会更快。

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

### 验证东八区时间

三个容器都内置时区数据库，并统一设置为 `Asia/Shanghai`。可以执行：

```bash
docker compose exec backend date
docker compose exec frontend date
docker compose exec caddy date
```

输出中应包含 `CST`，时间应与北京时间一致。服务器宿主机继续使用 UTC 也没有关系，
应用容器会独立使用东八区。

如果还希望服务器宿主机本身也显示北京时间，可以在常见的 systemd Linux 发行版
中执行：

```bash
sudo timedatectl set-timezone Asia/Shanghai
timedatectl
```

数据库里的 `created_at`、`updated_at`、登录过期时间等审计字段仍统一保存 UTC，这是
有意设计；前端展示时再转换为浏览器本地时间。起卦请求明确携带的时间不会被强制
改写，只有后端使用 `datetime.now()` 的兜底场景会采用容器的东八区时间。

## 5. 常用维护命令

更新代码并重建：

```bash
git pull # 拉取 git 最新代码
docker compose build # 构建镜像
docker compose up -d # 运行 docker 容器
```

如果本次更新前已经部署过旧镜像，需要重新构建三个服务才能安装时区数据：

```bash
docker compose build backend frontend caddy
docker compose up -d --force-recreate
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

未设置时始终使用官方 `python:3.12-slim-bookworm`、`node:22-alpine` 和
`caddy:2-alpine`。

这里的基础镜像源与 Python/npm 依赖源是两回事：Dockerfile 中的清华源和阿里源
只能加速 `apt`、`apk`、`pip install` 与 `npm ci`，不能加速
`FROM python/node` 或拉取 Caddy。
基础镜像下载较慢时，应配置服务器 Docker daemon 的 Registry Mirror，或者通过
上面的三个环境变量指定云厂商提供的镜像地址。

### 后端构建卡在 `apt-get update`

当前 Dockerfile 默认使用阿里 Debian 镜像，并带有超时、重试和缓存。如果仍然
超时，先显示完整日志：

```bash
docker compose build --progress=plain backend
```

BuildKit 输出中的 `CANCELED` 不一定是根因：并行构建时，只要另一个服务先出现
`ERROR`，仍在运行的后端步骤也会被标记为 `CANCELED`。应从完整日志中找到最早的
`ERROR`；单独构建 `backend` 可以排除其他服务的干扰。

再测试服务器能否访问镜像站：

```bash
curl -I --connect-timeout 10 https://mirrors.aliyun.com/debian/dists/bookworm/InRelease
```

如果阿里源不可达，按第 3 节的命令临时切换清华源。若两个国内镜像都不可达，
通常是服务器 DNS、出站 HTTPS（443 端口）或代理配置问题，而不是 Dockerfile
本身；此时应先检查云服务器的出站规则和 `/etc/resolv.conf`。

### 构建提示 `No space left on device`

这表示 Docker 数据目录或服务器根分区空间不足，不是 pip 软件源错误。先检查磁盘、
inode 和 Docker 占用：

```bash
df -h
df -i
docker system df
```

优先只清理可以重新生成的 BuildKit 构建缓存和悬空镜像：

```bash
docker builder prune -af
docker image prune -f
docker system df
df -h
```

如果空间仍然不足，可以查看所有未被容器使用的旧镜像；确认不需要回滚旧版本后再
执行第二条命令：

```bash
docker image ls
docker image prune -af
```

不要执行 `docker volume prune` 或 `docker compose down -v`，它们可能删除保存
SQLite 和用户 LLM 密钥的 `liuyao_data` 数据卷。服务器上还运行其他项目时，
也不要直接执行范围更大的 `docker system prune -af`。

清理后按服务顺序构建，避免三个服务并行构建造成更高的瞬时磁盘占用：

```bash
docker compose build --progress=plain backend
docker compose build --progress=plain frontend
docker compose build --progress=plain caddy
docker compose up -d
```

建议构建前至少保留数 GB 可用空间；如果清理后仍不足，应扩容云硬盘或把 Docker
数据目录迁移到容量更大的挂载盘，而不是继续反复构建。
