# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目概述

六爻 (Liu Yao) 算卦助手项目 — 一个基于中国传统易经六爻占卜的 AI 辅助解卦工具，采用 FastAPI + 多 Agent 架构。MVP 阶段使用《增删卜易》作为知识库，后续引入 RAG。

## 目录结构

```
liuyao_agent/
├── api/                      # FastAPI 接口层
│   ├── server.py             #   FastAPI app 入口
│   ├── deps.py               #   依赖注入
│   └── routes/
│       ├── health.py         #   GET /health
│       └── divination.py     #   POST /divinations 起卦解卦
│
├── core/                     # 核心业务（无 LLM 的纯算法层）
│   ├── calendar.py           #   地支计算（年月日时 → 地支）
│   ├── constants.py          #   共享常量（天干地支序、五行、八宫五行、旬空等）
│   ├── hexagrams/            #   64 卦包（数据/编码/显示/公共 API）
│   │   ├── data.py           #     _HEXAGRAM_DATA + 纳甲 4 张表
│   │   ├── codec.py          #     编码/卦宫/卦位查询
│   │   ├── display.py        #     LINE_NAMES / LINE_SYMBOLS / MOVING_MARK
│   │   └── __init__.py       #     公共 API: parse_hexagram() → HexagramFull
│   ├── wangshuai.py          #   爻旺衰判断
│   ├── xunkong.py            #   旬空计算
│   ├── liushen.py            #   六兽（青龙/朱雀/...）
│   ├── liuqin.py             #   六亲（父母/兄弟/...）
│   ├── bianhua.py            #   动爻/变卦生成
│   ├── paipan.py             #   排盘主函数 arrange_hexagram
│   └── qigua.py              #   起卦算法（手动/时间/铜钱/随机）
│
├── schema/                   # Pydantic 数据模型
│   └── api/                  #   API 请求/响应模型
│       └── divination.py     #   QiguaRequest / PaipanResult / DivinationResponse
│
├── utils/                    # 通用工具
│   ├── bazi.py               #   公历转八字（lunar_python）
│   ├── logger.py             #   结构化日志
│   ├── llm_client.py         #   LLM 客户端抽象接口
│   └── markdown.py           #   排盘结果 → 格式化 Markdown 字符串
│
├── config/                   # 全局配置（pydantic-settings）
├── running_data/             # 运行时数据：静态数据 + 解卦记录
│   ├── hexagram_texts.py     #   64 卦卦辞 + 爻辞
│   ├── divination_store.py   #   解卦结果 JSON / Markdown 存储
│   ├── divinations_json/     #   每个解卦一个 JSON 文件（运行时生成）
│   └── divinations_md/       #   每个解卦一个 Markdown 文件（运行时生成）
├── logs/                     # 运行日志
├── tests/                    # 单元测试
│
├── main.py                   # 启动入口（uvicorn）
├── requirements.txt
├── .env.example
└── README.md
```

## 分层职责

| 层 | 职责 | 是否依赖 LLM |
|---|---|---|
| `api/` | HTTP 请求/响应、参数校验 | 否 |
| `core/` | 起卦、排盘等确定性纯算法 | 否 |
| `schema/` | 数据模型 | 否 |
| `utils/` | 外部依赖/纯函数工具 | 视工具而定 |
| `running_data/` | 静态数据（卦辞爻辞等）+ 解卦记录 JSON 存储 | 否 |
| `agent/` (待用户设计) | 多 Agent 协作解卦 | 是 |

**调用方向**：`api → core / agent → schema / utils / running_data`，无反向依赖。

## 核心算法层（core/）模块说明

`core/paipan.arrange_hexagram(original_hexagram, qigua_time, question)` 是核心入口函数，整合所有 core 子模块，返回完整排盘 dict。

| 模块 | 职责 |
|---|---|
| `core/calendar` | 公历日期 → 地支（年月日时） |
| `core/constants` | 共享常量（天干地支序、五行、八宫五行、旬空等） |
| `core/hexagrams` | 64 卦包：上层用 `parse_hexagram(lines) → HexagramFull` 一次性拿到 `meta + 纳甲 + 卦宫五行`；底层 `get_hexagram_palace` / `get_hexagram_trigrams` / `encode_hexagram` 按需使用 |
| `core/wangshuai` | 单爻旺衰得分 + 状态（入墓/暗动/化绝等）+ 批量计算 + 入墓扩展 + 回头生克 |
| `core/xunkong` | 日干支 → 旬空 |
| `core/liushen` | 日地支 → 六兽顺序 |
| `core/liuqin` | 我五行 + 目标五行 → 六亲 |
| `core/bianhua` | 动爻识别 + 变卦生成 |
| `core/qigua` | 4 种起卦方式：manual / time / coin / random |
| `core/paipan` | 编排所有上述模块，输出结构化排盘结果 |

## 常用命令

```bash
# 安装依赖
pip install -r requirements.txt

# 配置环境变量
cp .env.example .env

# 启动开发服务器
python main.py
# 或
uvicorn api.server:app --reload --host 0.0.0.0 --port 8000

# 访问 Swagger 文档
open http://localhost:8000/docs
```

## API 端点

| 方法 | 路径 | 功能 |
|---|---|---|
| `GET` | `/health` | 健康检查 |
| `POST` | `/divinations` | 起卦 + 排盘（4 种起卦方式），落盘到 JSON |
| `GET` | `/divinations` | 列出所有解卦 ID |
| `GET` | `/divinations/{id}` | 按 ID 查询解卦结果 |
| `POST` | `/divinations/{id}/markdown` | 渲染并落盘 Markdown |
| `GET` | `/divinations/{id}/markdown` | 读取已生成的 Markdown |
| `DELETE` | `/divinations/{id}` | 删除记录（JSON + MD） |

### 起卦方式

| 方式 | 必传参数 | 说明 |
|---|---|---|
| `manual` | `numbers: [1..4]×6` | 手动输入爻位编码 |
| `time` | `solar_year/month/day/hour` | 传统时间起卦 |
| `coin` | 无 | 模拟三枚铜钱抛掷 |
| `random` | 无 | 一键随机生成 |

### 爻位编码

- `1` = 少阴（-- --）
- `2` = 少阳（-----）
- `3` = 纯阳（动爻，→ 变少阴）
- `4` = 纯阴（动爻，→ 变少阳）

## 开发约定

- **api 层不写业务逻辑**，仅做参数校验和响应组装
- **core 层无 LLM 依赖**，保证起卦排盘结果可单元测试、可复现
- **Agent 输出必须结构化**（JSON 或 Markdown），便于聚合与展示
- 所有解卦解读输出必须附带免责声明：`本结果仅供文化娱乐参考，不构成任何人生决策依据`
- 参考文档：
  - `六爻模版.md` — 解卦输出的 Markdown 格式规范
  - `六爻算卦助手的商业idea.md` — 商业计划与难点拆解

## 路线图

按以下顺序推进（详见 README）：
0. ✅ 基础架构
1. ✅ 起卦 + 排盘算法（移植自参考项目）
2. ✅ 64 卦数据（卦宫 + 卦辞爻辞）
3. ⏳ 单 Agent 解卦（端到端）
4. ⏳ 多 Agent 协作
5. ⏳ RAG 增强
6. ⏳ 会话与历史持久化
