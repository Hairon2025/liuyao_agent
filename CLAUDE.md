# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目概述

六爻 (Liu Yao) 算卦助手项目 — 一个基于中国传统易经六爻占卜的 AI 辅助解卦工具，采用 FastAPI + 多 Agent 架构。MVP 阶段使用《增删卜易》作为知识库，后续引入 RAG。

## 目录结构（apps-style 单仓库）

仓库按"端"分组：Python 后端全在 `backend/`，前端保留原名 `frontend/`，跨端的东西放根。

```
liuyao_agent/
├── backend/                   # Python 后端（FastAPI + Agent + core）
│   ├── api/                   #   FastAPI 接口层
│   │   ├── server.py          #     FastAPI app 入口
│   │   ├── deps.py            #     依赖注入
│   │   └── routes/
│   │       ├── health.py      #     GET /health
│   │       └── divination.py  #     解卦相关路由
│   ├── agent/                 #   多 Agent 解卦层（依赖 LLM）
│   │   ├── memory/            #     Session 包装与长期记忆压缩
│   │   ├── runtime/           #     OpenAI Agents SDK 运行时
│   │   ├── tools/             #     SDK Function Tools
│   │   ├── chat_orchestrator.py #   多 Agent 串行编排
│   │   └── prompt/            #     协调 / 解读 / 追问 / 摘要 Agent 指令
│   ├── core/                  #   纯算法层（无 LLM 依赖）
│   │   ├── calendar.py        #     地支计算
│   │   ├── constants.py       #     共享常量
│   │   ├── hexagrams/         #     64 卦包：data/codec/display/__init__
│   │   ├── wangshuai.py       #     爻旺衰
│   │   ├── xunkong.py         #     旬空
│   │   ├── liushen.py         #     六兽
│   │   ├── liuqin.py          #     六亲
│   │   ├── bianhua.py         #     动爻/变卦
│   │   ├── paipan.py          #     排盘主入口
│   │   └── qigua.py           #     起卦（4 种方式）
│   ├── schema/                #   Pydantic 数据模型
│   │   └── api/divination.py
│   ├── models/                #   SQLAlchemy ORM Model
│   ├── repositories/          #   数据访问层
│   ├── services/              #   业务规则与事务边界
│   ├── db/                    #   异步数据库连接与 Session
│   ├── migrations/            #   Alembic 数据库迁移
│   ├── utils/                 #   通用工具（bazi / logger / llm_client / markdown）
│   ├── config/                #   全局配置（pydantic-settings）
│   ├── running_data/          #   静态数据 + 本地 SQLite 数据库
│   │   └── hexagram_texts.py
│   ├── tests/                 #   pytest 单元测试（conftest.py 提供 client fixture）
│   ├── main.py                #   uvicorn 启动入口（默认 127.0.0.1:8022）
│   ├── requirements.txt
│   └── .env.sample
│
├── frontend/                  # Next.js 前端（默认连 http://127.0.0.1:8022）
│
├── deploy/                    # Docker Caddy 配置与后端环境模板
├── compose.yaml               # 前端、后端、Caddy 编排
├── assets/                    # 跨端素材
├── logs/                      # 跨端日志
│
├── README.md
├── CLAUDE.md                  # 本文件（Claude Code 项目指引）
└── AGENTS.md                  # Codex 同份指引
```

> `AGENTS.md` 与本文件结构对齐。修改目录/分层时请同时更新两处。

## 分层职责

| 层 | 职责 | 是否依赖 LLM |
|---|---|---|
| `backend/api/` | HTTP 请求/响应、参数校验 | 否 |
| `backend/core/` | 起卦、排盘等确定性纯算法 | 否 |
| `backend/agent/` | 多 Agent 协作完成解卦解读 | **是** |
| `backend/schema/` | 数据模型 | 否 |
| `backend/models/` | SQLAlchemy ORM 数据结构 | 否 |
| `backend/repositories/` | 数据库读写 | 否 |
| `backend/services/` | 业务规则与事务边界 | 否 |
| `backend/db/` | 数据库连接与 Session | 否 |
| `backend/utils/` | 外部依赖/纯函数工具 | 视工具而定 |
| `backend/running_data/` | 静态数据（卦辞爻辞等）+ 本地 SQLite 数据库 | 否 |

**调用方向**：`backend.api → backend.services → backend.repositories → backend.models / backend.db`；
起卦链路仍为 `backend.services → backend.core / backend.agent`，无反向依赖。

## 核心算法层（`backend/core/`）

`backend.core.paipan.arrange_hexagram(original_hexagram, qigua_time, question)` 是核心入口函数，整合所有 core 子模块，返回完整排盘 dict。

### `backend/core/paipan.py` 内部结构（Step 5 重构后）

`arrange_hexagram()` 只做编排，下沉到 5 个 stage helper + 2 个 frozen dataclass 中间态：

| 阶段 | helper | 输入 | 输出 |
|---|---|---|---|
| 1-2 | `_compute_context` | `qigua_time` | `PaipanContext`（干支 / 月支 / 日支 / 旬空 / 六兽序） |
| 3-4 | `_parse_ben_bian` | `lines` | `(HexagramFull, HexagramFull \| None, bian_lines \| None)` |
| 5 | `_calculate_strengths` | lines, ben, bian, ctx | `PaipanStrengths`（ben + bian 各自的旺衰列表） |
| 5 共享 | `_calculate_single_hex_strengths` | is_original 切换 | 本卦 / 变卦 旺衰通用计算（回头生克等仅对变卦做） |
| 6 | `_build_single_hexagram_result` | lines, hex_full, strengths, ... | `HexagramResult`（本卦或变卦的对外结构） |

中间态：`PaipanContext`（frozen dataclass）、`PaipanStrengths`（frozen dataclass）。
对外 TypedDict 仍为 `LineResult` / `HexagramResult` / `PaipanResult`（保持 API 兼容）。
变卦六亲沿用本卦的 `palace_wuxing`（调用方显式传入 `wo_wuxing=ben.palace_wuxing`）。

### 64 卦包（`backend/core/hexagrams/`）

- **上层**：`from backend.core.hexagrams import parse_hexagram` — `parse_hexagram(lines) → HexagramFull`，一次性拿到 `meta + 纳甲 + 卦宫五行`。
- **底层**（按需）：`get_hexagram_palace` / `get_hexagram_trigrams` / `encode_hexagram`。

## 常用命令

> 全部命令在 **仓库根目录** 执行（这样 `backend/` 才能被 Python 当成包导入）。

```bash
# 安装依赖
pip install -r backend/requirements.txt
cp backend/.env.sample backend/.env        # 生产环境设置 USER_LLM_ENCRYPTION_KEY

# 应用数据库迁移
python -m alembic -c backend/alembic.ini upgrade head

# 启动后端（默认 127.0.0.1:8022；reload 由 settings.debug 控制）
# 方式 A：作为模块运行
python -m backend.main
# 方式 B：直接用 uvicorn（推荐加 --reload 开发）
uvicorn backend.api.server:app --reload --host 0.0.0.0 --port 8022

# 跑测试（backend/tests/conftest.py 提供 client + created_divination_ids fixtures）
python -m pytest backend/tests
python -m pytest backend/tests/test_xunkong.py                  # 单文件
python -m pytest backend/tests/test_routes_divination.py -k coin  # 按关键字过滤
python -m pytest backend/tests -x --tb=short                    # 遇错即停 + 简短回溯
```

> 监听端口以 `backend/main.py` 为准（当前 8022）；Swagger 文档在 `http://127.0.0.1:<port>/docs`。
> 不要 `cd backend && python main.py`——那样 `backend` 不在 `sys.path` 上，无法解析 `from backend.X import Y`。

## 前端开发

```bash
cd frontend
npm install
npm run dev      # 默认连 http://localhost:8022
```

如后端部署在其他地址，复制 `frontend/.env.example` 为 `frontend/.env.local`，并修改 `NEXT_PUBLIC_API_BASE_URL`。

**前端铜钱起卦** 在浏览器逐掷模拟三枚铜钱翻转（共六掷），每掷换算为少阴 / 少阳 / 老阳 / 老阴，最终把 6 个编码通过 `method=manual` 提交给后端，不依赖后端 `backend/core/qigua.py` 的 `coin` 随机实现。

## Docker 部署

无域名测试环境使用根目录 `compose.yaml`，由 Caddy 将 `/api/*` 转发到后端，
其余请求转发到前端。SQLite 单独持久化到 `/data`，不要把整个
`backend/running_data` 挂载成数据卷。详见 `docs/DOCKER_DEPLOYMENT.md`。

## API 端点

| 方法 | 路径 | 功能 |
|---|---|---|
| `GET` | `/health` | 健康检查 |
| `POST` | `/auth/guests` | 创建游客 Session |
| `POST` | `/auth/register` | 游客原地升级为注册用户 |
| `POST` | `/auth/login` | 用户名密码登录 |
| `POST` | `/auth/logout` | 注销当前 Session |
| `GET` | `/auth/me` | 查询当前身份 |
| `GET/PATCH` | `/users/me` | 查询或更新当前资料 |
| `GET/PUT/DELETE` | `/users/me/llm-settings` | 管理个人 LLM 设置 |
| `POST` | `/users/me/llm-settings/test` | 测试已保存模型连接 |
| `POST` | `/divinations` | 起卦 + 排盘并保存数据库 |
| `GET` | `/divinations` | 列出当前用户的卦例 ID |
| `GET` | `/divinations/{id}` | 查询当前用户的一条卦例 |
| `POST` | `/divinations/{id}/markdown` | 渲染 Markdown 并保存数据库 |
| `GET` | `/divinations/{id}/markdown` | 读取数据库中的 Markdown |
| `POST` | `/divinations/{id}/interpret` | 非流式生成解读并写回数据库 |
| `POST` | `/divinations/{id}/interpret/stream` | SSE 流式生成解读并写回数据库 |
| `DELETE` | `/divinations/{id}` | 删除当前用户的一条卦例 |
| `POST` | `/chat/sessions/{id}/messages/stream` | SSE 执行一轮 Chatbot 对话 |
| `POST` | `/chat/sessions/open` | 复用卦例最近会话或基于同一卦例新开讨论 |
| `POST` | `/chat/sessions/{id}/messages/{message_id}/suggestions` | 异步生成并缓存结构化追问 |

身份通过 HttpOnly Cookie 的服务端 Session 传递；Repository 查询必须同时限定资源
ID 和用户 ID。游客可起卦、排盘和查看自己的历史；AI 解读与 Chatbot 要求注册登录
且已配置个人 LLM。用户 API Key 只能以 AES-GCM 密文入库，不得写入日志或响应。

> 与 README 的对应章节保持同步；新增 / 删除路由时同时改两处。

## 起卦方式与爻位编码

| 方式 | 必传参数 | 说明 |
|---|---|---|
| `manual` | `numbers: [1..4]×6` | 手动输入爻位编码 |
| `time` | `time: ISO datetime` | 传统时间起卦 |
| `coin` | `numbers: [1..4]×6` | 接收前端六次投掷后的爻位编码 |
| `random` | 无 | 一键随机生成 |

**爻位编码**：`1` = 少阴（-- --），`2` = 少阳（-----），`3` = 纯阳（动爻 → 变少阴），`4` = 纯阴（动爻 → 变少阳）。

**铜钱起卦编码**（`method=coin`）：每枚铜钱 `0=字(阴)` / `1=花(阳)`，按一掷中"花"总数 `yang_count` 决定本爻类型 — `2=少阴`、`1=少阳`、`3=老阳(动)`、`0=老阴(动)`。共抛六次，从初爻到上爻。

## 开发约定

- **api 层不写业务逻辑**，仅做参数校验和响应组装
- **core 层无 LLM 依赖**，保证起卦排盘结果可单元测试、可复现
- **Agent 层使用 OpenAI Agents SDK**；模型上下文交给 SDK Session，不再手工拼接
- **当前不使用 Skill / Sandbox / Handoff**；起卦排盘必须通过 Function Tool → Service → core
- **多 Agent 由 Python 串行编排**；首次报告与结构化追问不得交给协调 Agent 重复生成
- **Agent 输出必须结构化**（JSON 或 Markdown），便于聚合与展示
- 所有解卦解读输出必须附带免责声明：`本结果仅供文化娱乐参考，不构成任何人生决策依据`
- 修改跨包 import 时注意保留 `backend.` 前缀（仓库根目录才是 Python 解析 `backend` 包的正确 cwd）
- 参考文档：
  - `六爻模版.md` — 解卦输出的 Markdown 格式规范
  - `六爻算卦助手的商业idea.md` — 商业计划与难点拆解
  - `AGENTS.md` — Codex 视角的同份指引
