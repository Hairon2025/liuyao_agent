# 六爻解卦助手 (liuyao_agent)

基于 FastAPI 的多 Agent 六爻解卦服务。

## 项目愿景

构建一个能"像人一样"解卦的 AI 助手。系统先通过纯算法完成起卦与排盘，再由多 Agent 协作完成解卦解读。MVP 阶段使用《增删卜易》作为知识库，后续引入 RAG 检索更多典籍（《卜筮正宗》《火珠林》《易隐》等）。

更多业务背景见 [`六爻算卦助手的商业idea.md`](./六爻算卦助手的商业idea.md)，解卦输出格式见 [`六爻模版.md`](./六爻模版.md)。

## 技术栈

- **Web 框架**：FastAPI + Uvicorn
- **数据校验**：Pydantic v2 + pydantic-settings
- **数据库**：SQLAlchemy 2.x + SQLite + Alembic
- **八字排盘**：lunar_python
- **LLM / Agent**：OpenAI Agents SDK + OpenAI-compatible Chat Completions
- **Agent 能力**：SDK Agent + Function Tool + SQLAlchemySession + Python 多 Agent 编排

## 目录结构

仓库按"端"分组：Python 后端全在 `backend/`，前端保留原名 `frontend/`，跨端的东西放根。

```
liuyao_agent/
├── backend/                  # Python 后端（FastAPI + Agent + core）
│   ├── api/                  #   FastAPI HTTP 接口层
│   │   ├── server.py         #   FastAPI app 入口
│   │   ├── deps.py
│   │   └── routes/
│   │       ├── health.py     #   GET /health
│   │       └── divination.py
│   ├── agent/                #   Agents SDK 运行时、Function Tools、多 Agent 编排
│   ├── db/                   #   SQLAlchemy Base、Engine、Session
│   ├── models/               #   SQLAlchemy ORM Model
│   ├── repositories/         #   数据访问层
│   ├── services/             #   业务服务与事务边界
│   ├── core/                 #   纯算法层（无 LLM 依赖）
│   ├── schema/               #   Pydantic 数据模型
│   ├── utils/                #   通用工具
│   ├── config/               #   全局配置（pydantic-settings）
│   ├── running_data/         #   静态数据 + 本地 SQLite 数据库
│   ├── migrations/           #   Alembic 数据库迁移
│   ├── alembic.ini
│   ├── tests/                #   pytest 单元测试
│   ├── main.py               #   uvicorn 启动入口（默认 127.0.0.1:8022）
│   ├── requirements.txt
│   └── .env.sample
│
├── frontend/                 # Next.js 前端
│
├── assets/
├── logs/
│
├── README.md
├── CLAUDE.md
└── AGENTS.md
```

## 分层职责

| 层 | 职责 | 是否依赖 LLM |
|---|---|---|
| `backend/api/` | 接收 HTTP 请求、参数校验、返回响应 | 否 |
| `backend/core/` | 起卦、排盘等确定性的纯算法 | 否 |
| `backend/schema/` | 数据模型定义 | 否 |
| `backend/models/` | SQLAlchemy ORM 数据结构 | 否 |
| `backend/repositories/` | 数据库读写 | 否 |
| `backend/services/` | 业务规则与事务边界 | 否 |
| `backend/db/` | 数据库连接与 Session | 否 |
| `backend/utils/` | 通用工具（八字、日志、LLM 客户端） | 视具体工具 |
| `backend/config/` | 全局配置加载 | 否 |
| `backend/agent/` | 多 Agent 协作完成解卦解读 | **是** |
| `backend/running_data/` | 静态数据（卦辞爻辞）+ 本地 SQLite 数据库 | 否 |

**调用方向**：`backend.api → backend.services → backend.repositories → backend.models / backend.db`；
起卦链路仍为 `backend.api → backend.core / backend.agent`，无反向依赖。

## 快速开始

### 1. 安装依赖

```bash
pip install -r backend/requirements.txt
```

### 2. 配置环境变量

```bash
cp backend/.env.sample backend/.env
# 编辑 backend/.env，填入 LLM_API_KEY 等配置
```

### 3. 应用数据库迁移

```bash
python -m alembic -c backend/alembic.ini upgrade head
```

SQLite 数据库默认创建在 `backend/running_data/liuyao.db`，不会提交到 Git。

### 4. 启动服务（须在仓库根目录执行，使 `backend/` 可作为 Python 包导入）

```bash
python -m backend.main
# 或：
uvicorn backend.api.server:app --reload --host 127.0.0.1 --port 8022
```

> 不要 `cd backend && python main.py`——那样 `backend` 不在 `sys.path`，`from backend.config import settings` 等会 `ModuleNotFoundError`。

启动后访问 http://127.0.0.1:8022/docs 查看 Swagger API 文档。

### 启动前端

前端项目位于 `frontend/`，默认连接 `http://127.0.0.1:8022`：

```bash
cd frontend
npm install
npm run dev
```

如后端部署在其他地址，复制 `frontend/.env.example` 为
`frontend/.env.local`，并修改 `NEXT_PUBLIC_API_BASE_URL`。

## API 端点

| 方法 | 路径 | 功能 |
|---|---|---|
| `GET` | `/health` | 健康检查 |
| `POST` | `/users/guests` | 创建匿名用户 |
| `GET` | `/users/{id}` | 查询用户 |
| `PATCH` | `/users/{id}` | 更新用户昵称 |
| `POST` | `/divinations` | 起卦 + 排盘并保存数据库；可选 `generate_markdown=true` |
| `GET` | `/divinations` | 列出当前用户的全部卦例 ID |
| `GET` | `/divinations/{id}` | 查询当前用户的一条卦例 |
| `POST` | `/divinations/{id}/markdown` | 渲染 Markdown 并保存数据库 |
| `GET` | `/divinations/{id}/markdown` | 读取数据库中的 Markdown |
| `POST` | `/divinations/{id}/interpret` | 调用 Agent 生成解读并写回数据库 |
| `POST` | `/divinations/{id}/interpret/stream` | 通过 SSE 流式生成解读并写回数据库 |
| `DELETE` | `/divinations/{id}` | 删除当前用户的一条卦例 |
| `POST` | `/chat/sessions` | 创建 Chatbot 会话 |
| `GET` | `/chat/sessions` | 分页列出当前用户的会话 |
| `GET` | `/chat/sessions/{id}` | 读取会话 |
| `PATCH` | `/chat/sessions/{id}` | 修改标题、归档状态、模型或当前卦例 |
| `DELETE` | `/chat/sessions/{id}` | 删除会话及其消息 |
| `GET` | `/chat/sessions/{id}/messages` | 按消息序号游标读取历史 |
| `POST` | `/chat/sessions/{id}/messages/stream` | 通过命名 SSE 执行一轮 Agents SDK 对话 |

除用户创建与查询接口外，所有 `/divinations` 请求都需要携带
`X-User-ID: <uuid>`。这是 MVP 阶段的临时身份传输方式；前端会自动创建访客
并在浏览器中保存 ID。它不等同于安全认证，接入登录系统后应替换为服务端
验证的登录态。

## Chatbot 后端

聊天模块后端已经形成完整闭环：

- `chat_sessions`：保存用户归属、标题、归档状态、当前卦例和领域工作流草稿。
- `chat_messages`：保存文本、工具调用、工具结果、结构化追问建议、流式生成状态及会话内序号。
- `agent_sessions` / `agent_messages`：由 SDK `SQLAlchemySession` 保存模型上下文。
- 一个会话可以关联多个卦例，`active_divination_id` 只表示当前主要讨论对象。
- 删除会话时会同时清理业务消息和 SDK 上下文；删除卦例只会把聊天中的
  卦例外键设置为 `NULL`。
- `ChatSessionRepository` 对会话进行用户所有权过滤，并通过数据库原子计数器
  预留消息序号。
- `ChatMessageRepository` 通过所属会话校验用户，支持序号游标分页、最近消息和
  工具调用/结果配对查询。
- 同一会话内 `(session_id, sequence)` 唯一；预留序号和消息写入必须放在同一事务。
- SDK `Runner` 负责标准 Agent 的模型流、工具循环和上下文回填。
- `LiuYaoChatbot` 是协调 Agent，负责理解普通聊天、新起卦、补充信息、
  当前卦追问和历史查询；当前版本不使用 Router、Handoff、Sandbox 或 Skill。
- `ChatAgentOrchestrator` 在新卦创建后串行调用原有 `LiuYaoAnalyst`：
  报告一边通过 SSE 输出，一边保存到 `divinations.interpretation.detail`，
  同时作为聊天正文落库。
- `SuggestedQuestionAgent` 在正文完成后独立生成 JSON 追问建议；失败只记录日志，
  不会把已经生成的主回答判为失败。
- Function Tools 包括合并起卦信息、取消未完成流程、读取当前/指定卦例、
  列出最近卦例；
  所有读取均校验用户所有权。
- `ChatDivinationWorkflow` 将未收集完整的参数保存在 `workflow_state`，完整后才调用
  确定性的 `DivinationService` 起卦排盘；它也负责逐次追加铜钱结果和区分
  “现在”与指定时间，模型不会自行计算卦象。
- `CHAT_CONTEXT_RECENT_LIMIT` 限制 SDK 每轮读取的最近 Item 数；当前版本不做语义摘要。
- 前端卦例页的单次“AI 解读”和 Chatbot 首次正式报告均复用原始
  `LiuYaoAnalyst + liuyao_analyst.txt`，但仍保留两个独立 HTTP 使用入口。
- 隐藏思考过程不保存；仅持久化用户文本、可见回答、工具调用和工具结果。

Agent 代码的推荐阅读顺序见
[`backend/agent/README.md`](./backend/agent/README.md)。

### Chatbot 配置

```env
LLM_API_KEY=your-api-key
LLM_BASE_URL=https://api.openai.com/v1
LLM_MODEL=gpt-4o
LLM_TIMEOUT_SECONDS=120

CHAT_MAX_STEPS=6
CHAT_CONTEXT_RECENT_LIMIT=50
```

`CHAT_MAX_STEPS` 会传给 SDK `Runner.max_turns`；
`CHAT_CONTEXT_RECENT_LIMIT` 会传给 SDK `SQLAlchemySession`。模型客户端采用
延迟初始化，因此未配置 API Key 时仍可使用会话 CRUD 和历史读取接口；只有实际
发送 Chatbot 消息时才需要模型凭据。

每次模型生成和工具调用后的继续生成都会占用 turn。一次普通业务工具调用通常
至少需要“模型选择工具”和“模型根据工具结果回答”两个阶段，因此默认使用 6。

### Chatbot SSE 契约

`POST /chat/sessions/{id}/messages/stream` 请求体：

```json
{
  "message": "帮我随机起一卦，看看最近的工作机会",
  "model": null
}
```

响应使用命名 SSE，每个 `data` 都是完整 `ChatEvent` JSON：

- `text_delta`：可立即追加显示的文本增量；
- `tool_call_started`：工具开始；
- `tool_call_completed` / `tool_call_failed`：工具结果；
- `message_completed`：本轮完整可见文本；
- `suggestions`：三条结构化追问及其来源消息 ID；
- `error`：结构化错误；
- `done`：流结束，data 为 `[DONE]`。

所有 `/chat/sessions` 接口都需要 `X-User-ID`。会话、消息、卦例关联和工具读取
均按该用户过滤；其他用户访问同一 ID 时统一返回 404。

### 起卦方式

| 方式 | 必传参数 | 说明 |
|---|---|---|
| `manual` | `numbers: [1..4]×6` | 手动输入爻位编码 |
| `time` | `time: ISO datetime` | 传统时间起卦 |
| `coin` | `numbers: [1..4]×6` | 接收前端完成六次投掷后的爻位编码 |
| `random` | 无 | 一键随机生成 |

**爻位编码**：`1`=少阴，`2`=少阳，`3`=纯阳（动爻），`4`=纯阴（动爻）。

前端铜钱起卦会逐次模拟三枚铜钱翻转，共完成六掷；每次即时换算为
少阴 / 少阳 / 老阳 / 老阴，最终将六个爻位编码通过 `manual` 方式提交，
不依赖后端当前的 `coin` 随机实现。

### 调用示例

四种起卦方式均通过 `POST /divinations` 调用，区别仅在 `method` 与额外参数。

```bash
# 1) manual：手动输入 6 个爻位编码（1=少阴 2=少阳 3=纯阳 4=纯阴）
curl -X POST http://127.0.0.1:8022/divinations \
  -H 'Content-Type: application/json' \
  -d '{
    "method": "manual",
    "question": "这次考试能过吗？",
    "numbers": [1, 2, 3, 4, 2, 1],
    "time": "2026-07-02T11:00:00",
    "generate_markdown": true
  }'

# 2) coin：提交前端模拟三枚铜钱六次投掷后的六爻编码
curl -X POST http://127.0.0.1:8022/divinations \
  -H 'Content-Type: application/json' \
  -d '{
    "method": "coin",
    "question": "今日运势如何？",
    "numbers": [2, 1, 2, 2, 1, 2],
    "time": "2026-07-02T11:00:00",
    "generate_markdown": true
  }'

# 3) time：传统时间起卦（按年月日时计算卦象）
curl -X POST http://127.0.0.1:8022/divinations \
  -H 'Content-Type: application/json' \
  -d '{
    "method": "time",
    "question": "最近几周会找到工作吗？",
    "time": "2026-07-02T11:00:00",
    "generate_markdown": true
  }'

# 4) random：一键随机生成卦象
curl -X POST http://127.0.0.1:8022/divinations \
  -H 'Content-Type: application/json' \
  -d '{
    "method": "random",
    "question": "随便问问",
    "time": "2026-07-02T11:00:00",
    "generate_markdown": true
  }'

# 通用：按 ID 读已生成的 Markdown
curl http://127.0.0.1:8022/divinations/{id}/markdown
```

### 铜钱起卦编码（`method=coin`）

每次抛掷 3 枚铜钱，每枚铜钱的朝向编码为：

- `0` = 字（阴）
- `1` = 花（阳）

按一掷中"花（阳）"的总数 `yang_count ∈ [0, 3]` 决定本爻类型：

| 编码 | 组合 | 爻类型 | 花数 `yang_count` |
|---|---|---|---|
| 1 | 一字二花 | 少阴 | 2 |
| 2 | 二字一花 | 少阳 | 1 |
| 3 | 三花 | 老阳（动爻） | 3 |
| 4 | 三字 | 老阴（动爻） | 0 |

共抛掷 6 次，从初爻到上爻依次生成 6 个爻。

## 路线图

- [x] **阶段 0：基础架构** — FastAPI 框架 + 核心目录分层 + 数据模型
- [x] **阶段 1：起卦 + 排盘** — `backend/core/qigua.py` + `backend/core/paipan.py`（移植自参考项目）
- [x] **阶段 2：六十四卦数据** — 卦宫 + 卦辞爻辞全部入库
- [x] **阶段 2.5：本地持久化** — SQLite + SQLAlchemy + Alembic
- [x] **阶段 2.6：用户与卦例归属** — User / Divination Model、Repository、Service
- [x] **阶段 3：单 Agent 解卦** — 接入 LLM，完成端到端解卦
- [ ] **阶段 4：多 Agent 协作** — 按解卦环节拆分为多个 Agent
- [ ] **阶段 5：RAG 增强** — 接入《增删卜易》等知识库
- [x] **阶段 6：会话管理后端** — Chat Model / Repository / Service、Agents SDK、工具、Skill、SSE API
- [x] **阶段 6.1：Chatbot 前端** — 会话列表、消息流展示与工具状态 UI

## 合规与免责声明

所有面向用户的产品必须包含以下免责声明：

> 本结果仅供文化娱乐参考，不构成任何人生决策依据。

`backend/schema/api/divination.py` 中的 `InterpretationResult.disclaimer` 字段已默认携带该声明；`backend/utils/markdown.py` 渲染时也会附加该声明。

## 开发约定

- **API 层不写业务逻辑**，仅做参数校验和响应组装
- **core 层无 LLM 依赖**，保证起卦排盘结果可单元测试、可复现
- **Agent 输出必须结构化**（JSON 或 Markdown），便于聚合与展示
- 所有解卦解读输出必须附带免责声明
