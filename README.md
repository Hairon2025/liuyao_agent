# 六爻解卦助手 (liuyao_agent)

基于 FastAPI 的多 Agent 六爻解卦服务。

## 项目愿景

构建一个能"像人一样"解卦的 AI 助手。系统先通过纯算法完成起卦与排盘，再由多 Agent 协作完成解卦解读。MVP 阶段使用《增删卜易》作为知识库，后续引入 RAG 检索更多典籍（《卜筮正宗》《火珠林》《易隐》等）。

更多业务背景见 [`六爻算卦助手的商业idea.md`](./六爻算卦助手的商业idea.md)，解卦输出格式见 [`六爻模版.md`](./六爻模版.md)。

## 技术栈

- **Web 框架**：FastAPI + Uvicorn
- **数据校验**：Pydantic v2 + pydantic-settings
- **八字排盘**：lunar_python
- **LLM 客户端**：抽象层 (`utils/llm_client.py`)，后续可接入 OpenAI / Anthropic / 本地模型
- **Agent 框架**：待设计（参见下方"路线图"）

## 目录结构

```
liuyao_agent/
├── api/                      # FastAPI HTTP 接口层
│   ├── server.py             #   FastAPI app 入口
│   ├── deps.py               #   依赖注入
│   └── routes/
│       ├── health.py         #   GET /health
│       └── divination.py     #   解卦相关路由
│
├── core/                     # 核心业务（无 LLM 依赖的纯算法层）
│   ├── calendar.py           #   地支计算（年月日时 → 地支）
│   ├── hexagrams.py          #   64 卦卦宫数据 + 编码转换
│   ├── wangshuai.py          #   爻旺衰判断
│   ├── xunkong.py            #   旬空计算
│   ├── liushen.py            #   六兽（青龙/朱雀/...）
│   ├── liuqin.py             #   六亲（父母/兄弟/...）
│   ├── bianhua.py            #   动爻 / 变卦生成
│   ├── qigua.py              #   起卦算法（手动 / 时间 / 铜钱 / 随机）
│   ├── paipan.py             #   排盘主函数 arrange_hexagram
│
├── schema/                   # Pydantic 数据模型（API 请求 / 响应）
│   └── api/
│       └── divination.py
│
├── utils/                    # 通用工具（外部依赖 / 纯函数）
│   ├── bazi.py               #   公历转八字（基于 lunar_python）
│   ├── logger.py             #   结构化日志
│   ├── llm_client.py         #   LLM 客户端抽象接口
│   └── markdown.py           #   排盘结果 → 格式化 Markdown 渲染
│
├── config/                   # 全局配置
│   └── settings.py           #   从 .env 读取
│
├── running_data/             # 运行时数据：静态数据 + 解卦记录
│   ├── hexagram_texts.py     #   64 卦卦辞 + 爻辞
│   ├── divination_store.py   #   解卦结果 JSON / Markdown 存储
│   ├── divinations_json/     #   每个解卦一个 JSON（运行时生成）
│   └── divinations_md/       #   每个解卦一个 Markdown（运行时生成）
│
├── logs/                     # 运行日志
├── tests/                    # 单元测试
│
├── main.py                   # 启动入口（uvicorn）
├── requirements.txt
├── .env.example
├── CLAUDE.md                 # Claude Code 项目指引
└── README.md
```

## 分层职责

| 层 | 职责 | 是否依赖 LLM |
|---|---|---|
| `api/` | 接收 HTTP 请求、参数校验、返回响应 | 否 |
| `core/` | 起卦、排盘等确定性的纯算法 | 否 |
| `schema/` | 数据模型定义 | 否 |
| `utils/` | 通用工具（八字、日志、LLM 客户端） | 视具体工具 |
| `config/` | 全局配置加载 | 否 |
| `agent/` (待设计) | 多 Agent 协作完成解卦解读 | 是 |

**调用方向**：`api → core / agent → schema / utils`，无反向依赖。

## 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 配置环境变量

```bash
cp .env.example .env
# 编辑 .env，填入 LLM_API_KEY 等配置
```

### 3. 启动服务

```bash
python main.py
# 或
uvicorn api.server:app --reload --host 127.0.0.1 --port 8022
```

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
| `POST` | `/divinations` | 起卦 + 排盘，落盘 JSON；可选 `generate_markdown=true` 一步生成 Markdown |
| `GET` | `/divinations` | 列出所有解卦 ID |
| `GET` | `/divinations/{id}` | 按 ID 查询解卦结果 |
| `POST` | `/divinations/{id}/markdown` | 渲染并落盘 Markdown |
| `GET` | `/divinations/{id}/markdown` | 读取已生成的 Markdown |
| `POST` | `/divinations/{id}/interpret` | 调用 Agent 生成解读并写回记录 |
| `DELETE` | `/divinations/{id}` | 删除记录（JSON + MD） |

### 起卦方式

| 方式 | 必传参数 | 说明 |
|---|---|---|
| `manual` | `numbers: [1..4]×6` | 手动输入爻位编码 |
| `time` | `time: ISO datetime` | 传统时间起卦 |
| `coin` | 无 | 模拟三枚铜钱抛掷 |
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

# 2) coin：模拟三枚铜钱抛掷六次（编码规则见下方"铜钱起卦编码"）
curl -X POST http://127.0.0.1:8022/divinations \
  -H 'Content-Type: application/json' \
  -d '{
    "method": "coin",
    "question": "今日运势如何？",
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
- [x] **阶段 1：起卦 + 排盘** — `core/qigua.py` + `core/paipan.py`（移植自参考项目）
- [x] **阶段 2：六十四卦数据** — 卦宫 + 卦辞爻辞全部入库
- [x] **阶段 2.5：本地持久化** — JSON + Markdown 双格式落盘到 `data/`
- [ ] **阶段 3：单 Agent 解卦** — 接入 LLM，完成端到端解卦
- [ ] **阶段 4：多 Agent 协作** — 按解卦环节拆分为多个 Agent
- [ ] **阶段 5：RAG 增强** — 接入《增删卜易》等知识库
- [ ] **阶段 6：会话与历史** — 引入持久化存储与会话管理（当前为文件存储，可平滑迁移到 DB）

## 合规与免责声明

所有面向用户的产品必须包含以下免责声明：

> 本结果仅供文化娱乐参考，不构成任何人生决策依据。

`schema/api/divination.py` 中的 `InterpretationResult.disclaimer` 字段已默认携带该声明；`utils/markdown.py` 渲染时也会附加该声明。

## 开发约定

- **API 层不写业务逻辑**，仅做参数校验和响应组装
- **core 层无 LLM 依赖**，保证起卦排盘结果可单元测试、可复现
- **Agent 输出必须结构化**（JSON 或 Markdown），便于聚合与展示
- 所有解卦解读输出必须附带免责声明
