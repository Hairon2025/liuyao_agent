# AGENTS.md

This file provides guidance to Codex (Codex.ai/code) when working with code in this repository.

## 项目概述

六爻 (Liu Yao) 算卦助手项目 — 一个基于中国传统易经六爻占卜的 AI 辅助解卦工具，采用 FastAPI + 多 Agent 架构。MVP 阶段使用《增删卜易》作为知识库，后续引入 RAG。

## 目录结构（apps-style 单仓库）

仓库按"端"分组：Python 后端全在 `backend/`，前端保留原名 `frontend/`，跨端的东西放根。

```
liuyao_agent/
├── backend/                   # Python 后端（FastAPI + Agent + core）
│   ├── api/                   #   FastAPI 接口层
│   ├── agent/                 #   多 Agent 解卦层（依赖 LLM）
│   │   ├── base_agent.py
│   │   ├── liuyao_agent.py
│   │   └── prompt/liuyao_analyst.txt
│   ├── core/                  #   纯算法层（无 LLM 依赖）
│   │   ├── calendar.py / constants.py
│   │   ├── hexagrams/         #     64 卦包：data/codec/display/__init__
│   │   ├── wangshuai.py / xunkong.py / liushen.py / liuqin.py
│   │   ├── bianhua.py
│   │   ├── paipan.py          #     排盘主入口 arrange_hexagram
│   │   └── qigua.py           #     起卦（4 种方式）
│   ├── schema/                #   Pydantic 数据模型
│   ├── utils/                 #   通用工具
│   ├── config/                #   全局配置
│   ├── running_data/          #   静态数据 + 解卦记录 JSON/MD
│   ├── tests/                 #   pytest 单元测试
│   ├── main.py                #   uvicorn 启动入口（默认 127.0.0.1:8022）
│   ├── requirements.txt
│   └── .env.example
│
├── frontend/                  # Next.js 前端（默认连 http://127.0.0.1:8022）
│
├── assets/                    # 跨端素材
├── logs/                      # 跨端日志
│
├── README.md
├── CLAUDE.md                  # Claude Code 项目指引
└── AGENTS.md                  # 本文件
```

> `CLAUDE.md` 与本文件结构对齐。修改目录/分层时请同时更新两处。

## 分层职责

| 层 | 职责 | 是否依赖 LLM |
|---|---|---|
| `backend/api/` | HTTP 请求/响应、参数校验 | 否 |
| `backend/core/` | 起卦、排盘等确定性纯算法 | 否 |
| `backend/agent/` | 多 Agent 协作完成解卦解读 | **是** |
| `backend/schema/` | 数据模型 | 否 |
| `backend/utils/` | 外部依赖/纯函数工具 | 视工具而定 |
| `backend/running_data/` | 静态数据（卦辞爻辞等）+ 解卦记录 JSON 存储 | 否 |

**调用方向**：`backend.api → backend.core / backend.agent → backend.schema / backend.utils / backend.running_data`，无反向依赖。

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

- **上层**：`from backend.core.hexagrams import parse_hexagram` — 一次性拿到 `meta + 纳甲 + 卦宫五行`。
- **底层**（按需）：`get_hexagram_palace` / `get_hexagram_trigrams` / `encode_hexagram`。

## 常用命令

> 全部命令在 **仓库根目录** 执行（这样 `backend/` 才能被 Python 当成包导入）。

```bash
# 安装依赖
pip install -r backend/requirements.txt
cp backend/.env.example backend/.env

# 启动后端
python -m backend.main
# 或：
uvicorn backend.api.server:app --reload --host 0.0.0.0 --port 8022

# 跑测试
pytest backend/tests
pytest backend/tests/test_xunkong.py
pytest backend/tests/test_routes_divination.py -k coin
pytest backend/tests -x --tb=short
```

> 监听端口以 `backend/main.py` 为准（当前 8022）；Swagger 文档在 `http://127.0.0.1:<port>/docs`。
> 不要 `cd backend && python main.py`——那样 `backend` 不在 `sys.path`，无法解析 `from backend.X import Y`。

## 前端开发

```bash
cd frontend
npm install
npm run dev
```

如后端部署在其他地址，复制 `frontend/.env.example` 为 `frontend/.env.local`，并修改 `NEXT_PUBLIC_API_BASE_URL`。

## API 端点

| 方法 | 路径 | 功能 |
|---|---|---|
| `GET` | `/health` | 健康检查 |
| `POST` | `/divinations` | 起卦 + 排盘（4 种起卦方式），落盘 JSON；可选 `generate_markdown=true` 一步生成 MD |
| `GET` | `/divinations` | 列出所有解卦 ID |
| `GET` | `/divinations/{id}` | 按 ID 查询解卦结果 |
| `POST` | `/divinations/{id}/markdown` | 渲染并落盘 Markdown |
| `GET` | `/divinations/{id}/markdown` | 读取已生成的 Markdown |
| `POST` | `/divinations/{id}/interpret` | 调用 Agent 生成解读并写回记录 |
| `DELETE` | `/divinations/{id}` | 删除记录（JSON + MD） |

## 起卦方式与爻位编码

| 方式 | 必传参数 | 说明 |
|---|---|---|
| `manual` | `numbers: [1..4]×6` | 手动输入爻位编码 |
| `time` | `time: ISO datetime` | 传统时间起卦 |
| `coin` | 无 | 模拟三枚铜钱抛掷 |
| `random` | 无 | 一键随机生成 |

**爻位编码**：`1` = 少阴（-- --），`2` = 少阳（-----），`3` = 纯阳（动爻 → 变少阴），`4` = 纯阴（动爻 → 变少阳）。

## 开发约定

- **api 层不写业务逻辑**，仅做参数校验和响应组装
- **core 层无 LLM 依赖**，保证起卦排盘结果可单元测试、可复现
- **Agent 输出必须结构化**（JSON 或 Markdown），便于聚合与展示
- 所有解卦解读输出必须附带免责声明：`本结果仅供文化娱乐参考，不构成任何人生决策依据`
- 修改跨包 import 时注意保留 `backend.` 前缀（仓库根目录才是 Python 解析 `backend` 包的正确 cwd）
- 参考文档：
  - `六爻模版.md` — 解卦输出的 Markdown 格式规范
  - `六爻算卦助手的商业idea.md` — 商业计划与难点拆解
  - `CLAUDE.md` — Claude Code 视角的同份指引
