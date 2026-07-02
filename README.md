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
│       ├── health.py         #   GET /health 健康检查
│       └── divination.py     #   POST /divinations 起卦解卦
│
├── core/                     # 核心业务逻辑（无 LLM 依赖的纯算法层）
│   ├── qigua.py              #   起卦算法（手动 / 时间 / 铜钱 / 随机）
│   ├── paipan.py             #   排盘逻辑（本卦、变卦、六亲、六神、世应）
│   └── hexagrams.py          #   六十四卦基础数据
│
├── schema/                   # Pydantic 数据模型（API 请求/响应）
│   └── divination.py         #   起卦请求、卦象、爻、排盘、解卦结果
│
├── utils/                    # 通用工具（外部依赖/纯函数）
│   ├── bazi.py               #   公历转八字（基于 lunar_python）
│   ├── logger.py             #   结构化日志
│   └── llm_client.py         #   LLM 客户端抽象接口
│
├── config/                   # 全局配置
│   └── settings.py           #   从 .env 读取，支持 Pydantic Settings
│
├── data/                     # 静态数据（六十四卦 JSON、爻辞文本等）
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
uvicorn api.server:app --reload --host 0.0.0.0 --port 8000
```

启动后访问 http://localhost:8000/docs 查看 Swagger API 文档。

### 4. 调用示例

```bash
# 健康检查
curl http://localhost:8000/health

# 时间起卦（示例）
curl -X POST http://localhost:8000/divinations \
  -H 'Content-Type: application/json' \
  -d '{
    "method": "time",
    "question": "最近几周会找到工作吗？",
    "solar_year": 2026,
    "solar_month": 7,
    "solar_day": 2,
    "hour": 11
  }'
```

## 路线图

项目按以下顺序逐步搭建：

- [x] **阶段 0：基础架构** — FastAPI 框架 + 核心目录分层 + 数据模型
- [ ] **阶段 1：起卦 + 排盘** — 在 `core/qigua.py` 和 `core/paipan.py` 中实现确定性算法
- [ ] **阶段 2：六十四卦数据** — 录入六十四卦基础数据到 `core/hexagrams.py` 或 `data/`
- [ ] **阶段 3：单 Agent 解卦** — 接入 LLM，先用单 Agent + 提示词完成端到端解卦
- [ ] **阶段 4：多 Agent 协作** — 按解卦环节拆分为多个 Agent（如取用神、动变分析、综合解读）
- [ ] **阶段 5：RAG 增强** — 接入《增删卜易》等知识库
- [ ] **阶段 6：会话与历史** — 引入持久化存储与会话管理

## API 端点

| 方法 | 路径 | 功能 |
|---|---|---|
| `GET` | `/health` | 健康检查 |
| `POST` | `/divinations` | 创建一次起卦 + 解卦请求 |
| `GET` | `/divinations/{id}` | 查询解卦结果 |

## 合规与免责声明

所有面向用户的产品必须包含以下免责声明：

> 本结果仅供文化娱乐参考，不构成任何人生决策依据。

`schema/divination.py` 中的 `InterpretationResult.disclaimer` 字段已默认携带该声明，所有解卦 Agent 的最终输出必须保留。

## 开发约定

- **API 层不写业务逻辑**，仅做参数校验和响应组装
- **core 层无 LLM 依赖**，保证起卦排盘结果可单元测试、可复现
- **Agent 输出必须结构化**（JSON 或 Markdown），便于聚合与展示
- 所有 Agent 解读输出必须附带免责声明
