# Agent 优化路线

> 整理日期：2026-08-05  
> 当前阶段：MVP 功能基本完整，后续重点转向工程化、稳定性和可评测性。

## 1. 当前基线

当前 Agent 模块已经具备以下核心能力：

- `LiuYaoChatbot` 负责多轮对话、起卦信息收集、当前卦追问和历史查询。
- `LiuYaoAnalyst` 负责首次正式解读，并与卦例页面的单次 AI 解读复用。
- `SuggestedQuestionAgent` 独立生成结构化追问建议。
- `MemorySummaryAgent` 生成结构化长期记忆。
- 起卦和排盘通过 Function Tool → Service → core 的确定性链路完成。
- `workflow_state` 支持多轮收集时间、问题、爻值和铜钱结果。
- Agents SDK `SQLAlchemySession` 保存原始模型上下文。
- 模型上下文由长期摘要、最近 SDK Item 和当前卦例状态组成。
- 主回答使用 SSE 流式输出，并保存用户消息、可见回答、工具调用与工具结果。
- 所有卦例操作均校验用户所有权。

因此，短期内不需要为了“功能看起来更完整”继续增加 Agent。后续新增 Agent 应由
清晰、独立且可评测的职责驱动，而不是把普通业务步骤模型化。

## 2. 优先级总览

| 优先级 | 优化项 | 主要目标 |
|---|---|---|
| P0 | Agent 运行记录与可观测性 | 能解释每轮运行发生了什么、花费多少、为何失败 |
| P0 | 同会话并发保护 | 防止两个 Agent Run 同时修改 Session 和起卦草稿 |
| P0 | 请求幂等 | 防止 SSE 重连、重复点击造成重复消息或重复起卦 |
| P1 | 错误分类与安全重试 | 对超时、限流、工具失败等采取不同恢复策略 |
| P1 | Redis 运行态与限流 | 降低 Agent 上下文数据库读压，并保护模型额度 |
| P1 | Agent 行为评测集 | 持续验证工具选择、参数提取和回答规则 |
| P1 | 高风险问题保护 | 医疗、法律、金融等场景不依赖 Prompt 单独兜底 |
| P2 | 统一模型创建方式 | 统一 BaseAgent、Chatbot、摘要和追问 Agent 配置 |
| P2 | 上下文与 Token 优化 | 降低完整排盘、历史报告和工具结果的 Token 消耗 |
| P2 | 拆分 ChatService | 降低服务类复杂度，明确事务和运行边界 |
| P3 | Prompt 版本管理 | 让每次回答可以追溯、对比和回滚 Prompt |
| P3 | 用户反馈与重新生成 | 为后续质量评测积累真实反馈数据 |

## 3. P0：运行记录与可观测性

### 当前不足

- SDK tracing 当前关闭。
- 日志以异常日志为主，缺少一轮 Agent Run 的完整生命周期。
- `chat_messages.token_count` 已预留，但目前没有真实写入。
- 无法直接查看模型、耗时、首字时间、Token、工具次数和摘要情况。

### 建议方案

建立 `AgentRunModel + AgentRunRepository`，每个用户请求对应一条运行记录。建议字段：

```text
id
user_id
session_id
user_message_id
assistant_message_id
agent_name
model
status
started_at
first_token_at
completed_at
input_tokens
output_tokens
tool_call_count
summary_triggered
error_code
prompt_version
```

日志只记录运行元数据、可见消息状态和工具调用，不保存模型隐藏思维过程。
工具参数中可能包含用户隐私，写日志前需要裁剪或脱敏。

### 验收标准

- 能通过 `session_id` 查到每一轮运行记录。
- 能区分 `running/completed/failed/cancelled`。
- 能看到模型、总耗时、首字耗时、Token 和工具次数。
- 能确认本轮是否触发长期摘要以及压缩数量。
- 日志中不出现 API Key、隐藏思维或未脱敏敏感信息。

## 4. P0：同会话并发保护

### 风险

同一个 `chat_session` 同时运行两个流式请求时，可能发生：

- `workflow_state` 被并发覆盖。
- 铜钱结果被重复或交叉追加。
- `active_divination_id` 被后完成的请求覆盖。
- SDK Session Item 顺序交叉。
- 两个请求重复创建卦例。

### MVP 方案

SQLite 阶段先限制同一个 `session_id` 同时只能有一个活动 Run。第二个请求可以：

- 返回 `409 Conflict`；或
- 明确进入等待队列。

优先选择返回 `409`，逻辑更简单，前端也容易提示“上一条消息仍在生成”。

### 验收标准

- 同一会话的第二个并发请求不会启动模型。
- 不同会话仍可以并发运行。
- 连接取消、模型异常和进程错误后，活动状态可以释放或超时恢复。
- 有并发集成测试覆盖。

## 5. P0：请求幂等

### 风险

用户消息在模型运行前保存。前端重复点击、网络重试或 SSE 断线重连时，后端无法
判断是同一请求重试，还是用户确实再次发送了相同内容。

### 建议方案

前端每次发送生成 `client_request_id`，后端建立唯一约束：

```text
(session_id, client_request_id)
```

重复请求应返回已有 Run 或已有消息状态，不再次执行有副作用的工具。

### 验收标准

- 同一个 `client_request_id` 不会生成两条用户消息。
- 随机起卦、铜钱追加等有副作用操作不会重复执行。
- 前端可以查询重复请求对应的现有状态。

## 6. P1：Redis 运行态、会话上下文与限流

### 设计结论

Redis 适合保存 Agent 的高频运行态，但不应替代业务数据库。建议采用“Redis 热状态 +
SQLite 持久化事实”的分工：

| 数据 | 建议存储 | 原因 |
|---|---|---|
| 用户、LLM 设置、卦例 | SQLite | 必须持久化，且需要事务与所有权校验 |
| 用户可见聊天记录 `chat_messages` | SQLite | 是产品历史、审计记录和恢复依据 |
| 长期摘要 `chat_sessions.summary` | SQLite 为准，Redis 可缓存 | 摘要不能因 Redis 重启而丢失 |
| Agent 最近 SDK Items | Redis | 高频读写、有明确窗口和 TTL，可降低 SQLite 查询压力 |
| `workflow_state`、当前卦例引用 | SQLite 为准，Redis 可缓存 | 业务状态需要可恢复，缓存用于减少重复读取 |
| 同会话运行锁、请求幂等短状态 | Redis | `SET NX EX` 和 TTL 适合并发控制 |
| 接口限流计数器 | Redis | 原子计数、过期和滑动窗口实现简单 |

切换后每轮对话仍然需要访问 SQLite：身份和资源所有权校验、用户可见消息持久化、
卦例状态等不能只放缓存。优化的重点是把当前每轮重复读取的 `agent_messages` 上下文移到
Redis，而不是追求“每轮完全不访问数据库”。

### 推荐上下文流程

```text
收到用户消息
  ↓
SQLite 校验用户、会话所有权和业务状态
  ↓
Redis 获取同会话运行锁 + 执行用户/IP 限流
  ↓
Redis 读取最近 SDK Items
  + SQLite/Redis 读取长期摘要
  + 当前卦例和 workflow_state
  ↓
执行 Agent，并将新 SDK Items 追加到 Redis
  ↓
将用户可见消息和业务状态持久化到 SQLite
  ↓
达到摘要阈值时合并长期摘要，先写入 SQLite，再裁剪 Redis 旧 Items
  ↓
释放同会话运行锁
```

长期记忆仍采用“长期摘要 + 最近完整轮次”。Redis 使用 List 或等价有序结构保存最近
Items，通过 `LLEN`/估算 Token 判断是否达到摘要阈值；压缩时不能从工具调用链或一轮
对话中间截断。摘要写入 SQLite 成功后，才能裁剪 Redis 中已覆盖的 Items。

Redis 中的上下文应设置可配置 TTL，例如 7～30 天。缓存丢失时，允许使用
`chat_sessions.summary + 最近 chat_messages + 当前业务状态` 重建近似上下文；因此
`chat_messages` 仍是完整产品历史，Redis 上下文不是唯一数据副本。

### 限流维度

建议优先实现以下限制：

1. 注册用户级 AI 限流：分别限制正式解读、Chatbot 和追问建议，避免某个低价值接口
   占满全部额度。
2. IP 级辅助限流：重点保护登录、注册和其他可能被批量调用的入口，但不能只依赖 IP。
3. 同会话并发限制：同一 `chat_session` 同时只允许一个 Agent Run。
4. 请求幂等：短期保存 `session_id + client_request_id`，阻止 SSE 重连或重复点击重复扣费。
5. 用量统计：Redis 负责实时窗口计数，SQLite 保存最终 Token/调用量记录，供长期统计。

限流算法首版可用固定窗口或令牌桶。所有判断与扣减必须使用 Redis 原子命令或 Lua
脚本，避免并发穿透。Redis 不可用时，AI 付费接口原则上应拒绝执行并返回明确的服务
错误；普通的非 AI 查询接口不应被 Redis 故障连带阻断。

### 分阶段迁移

1. 增加 Redis 配置、连接管理、健康检查和测试环境，不改变现有 Session。
2. 先实现用户/IP 限流、同会话锁和请求幂等，验证 Redis 的部署稳定性。
3. 定义符合 Agents SDK Session 协议的 `RedisAgentSession`，保留
   `SQLAlchemySession` 作为可切换回退方案。
4. 灰度切换上下文读取，确认工具调用 Item 顺序、流式取消和多轮恢复均正确。
5. 将摘要裁剪改为 Redis 原子操作，并补充 Redis 丢失后的恢复测试。
6. 观察一段时间后，再决定是否停止向 `agent_sessions/agent_messages` 写入；迁移初期不要
   立即删除现有表和数据。

### 验收标准

- Agent 正常轮次不再从 SQLite 全量读取未压缩的 SDK Items。
- Redis 重启或上下文过期后，会话仍能基于持久化摘要和最近业务消息继续使用。
- 同一会话并发请求不会交叉写入上下文。
- 达到用户或 IP 限额时返回统一的 `429`，不会启动模型请求。
- 限流、锁和摘要裁剪均有并发测试及故障恢复测试。
- Redis Key 不包含 API Key、完整 Prompt 或无需缓存的用户敏感信息。

## 7. P1：错误分类与安全重试

### 建议错误类型

```text
model_timeout
model_rate_limited
model_authentication_error
model_invalid_response
tool_validation_error
tool_execution_error
max_turns_exceeded
stream_cancelled
initial_interpretation_error
memory_summary_error
```

### 重试原则

- 尚未执行有副作用工具时，模型超时和限流可以指数退避重试。
- 卦例已经创建后，不得重跑整条 Agent 链路，只重试正式解读。
- 追问建议失败只重试 `SuggestedQuestionAgent`。
- 摘要失败保留全部原始 Item，下轮再次尝试。
- 工具是否可重试应由明确的幂等语义决定，不能统一自动重试。

### 验收标准

- 前端能够根据 `error_code` 展示不同提示。
- 自动重试不会重复创建卦例或追加铜钱结果。
- 每种主要模型异常至少有一个单元测试。

## 8. P1：Agent 行为评测集

单元测试可以证明代码分支正确，但不能证明模型在真实自然语言下始终选择正确工具。
建议建立一组固定评测样本，至少覆盖：

| 输入 | 期望行为 |
|---|---|
| “帮我起一卦” | 询问所问事项和方式，不直接排盘 |
| “随机起一卦看工作” | 调用 `process_divination_request(method=random)` |
| “第一次投了字字花” | 追加一次铜钱结果并询问下一次 |
| “继续说说刚才那个卦的应期” | 读取当前卦，不重新起卦 |
| “完整分析当前排盘” | 调用 `request_initial_interpretation` |
| “重新起一卦” | 取消未完成草稿并开始新流程 |
| 模糊的新问题/追问 | 先澄清，不擅自起新卦 |
| Prompt 注入文本 | 不泄露内部状态，不绕过工具边界 |
| 医疗、法律、金融高风险问题 | 给出安全提示，不以占卜替代专业判断 |

建议评测指标：

- 工具选择准确率。
- 工具参数准确率。
- 错误起卦率。
- 重复正式报告率。
- 免责声明覆盖率。
- 内部 JSON 或状态泄露率。
- 多轮起卦流程完成率。

真实模型评测应与普通单元测试分开，可通过环境变量显式启用，避免日常测试产生费用。

## 9. P1：高风险问题保护

医疗、法律、金融和自伤风险不能只依赖 Prompt。建议在进入 Agent 前增加确定性安全
策略，优先覆盖胸痛、呼吸困难、昏厥、自伤等紧急表达。

```text
用户输入
  ↓
高风险规则检查
  ├── 紧急风险：直接输出安全提示，不用占卜决定是否就医
  └── 普通问题：进入正常 Agent 流程
```

这一步不必增加新的 Agent。规则应尽量小而明确，并通过测试控制误判范围。

## 10. P2：统一模型创建方式

当前 `LiuYaoAnalyst` 通过 `BaseAgent` 和进程级环境变量创建模型；Chatbot、摘要和追问
Agent 通过 `AgentModelFactory` 创建显式客户端。后续建议让 `BaseAgent` 内部也依赖
`AgentModelFactory`，同时保留现有易读的继承结构。

目标：

- API Key、Base URL、模型和超时配置行为一致。
- 所有 Agent 都可以在测试中注入 Fake Model。
- Analyst 后续可以独立选择模型，而不影响主 Chatbot。
- 避免修改 Agents SDK 进程级全局配置。

## 11. P2：上下文与 Token 优化

### 当前问题

`get_divination` 可能同时返回完整排盘 Markdown 和完整历史报告。一次工具轮次会产生
较多 SDK Item 和 Token，单个完整轮次也可能超过最近上下文目标数量。

### 建议方向

1. 将读取卦例拆成结构化摘要和完整详情两个层次：

   ```text
   get_divination_summary
   get_divination_detail
   ```

2. 普通追问优先使用结构化事实；只有需要完整分析时才读取全部 Markdown。
3. 对工具输出设置字符或 Token 上限，避免把无关字段送入模型。
4. 长期摘要由 Item 阈值逐步升级为“Item 数 + 估算 Token 数”双阈值。
5. 评估把摘要任务移到上一轮回答结束后的后台任务，减少下一轮首字延迟；实施前必须
   先完成并发控制和任务可靠性设计。

## 12. P2：拆分 ChatService

当前 `ChatService` 同时负责会话 CRUD、Agent 运行、SSE 事件投影、消息持久化、工具
记录、追问建议和摘要协调。可以逐步拆分为：

```text
ChatSessionService
ChatRunService
ChatEventProjector
ChatSuggestionService
ChatMemoryService
```

不建议一次性重构。每次只抽出一个边界，并保持现有 API 与测试兼容。

## 13. P3：Prompt 版本与反馈闭环

### Prompt 版本

每次 Agent Run 保存：

- Prompt 名称与版本。
- Prompt 内容哈希。
- 模型名称与关键参数。

这样可以比较 Prompt 修改前后的工具准确率、错误率和 Token 成本，并能快速回滚。

### 用户反馈

后续可以为回答增加：

- 有帮助 / 没帮助。
- 重新生成。
- 选择具体问题标签。

反馈应关联 `agent_run_id`，为后续 Prompt、模型和 RAG 评测提供真实数据。

## 14. 推荐实施顺序

为便于逐步阅读代码，建议一次只做一个阶段：

1. `AgentRunModel + AgentRunRepository`，先记录状态、耗时、模型和 Token。
2. 引入 Redis 基础连接和健康检查。
3. 基于 Redis 实现同会话运行锁。
4. 基于 Redis 实现用户/IP 限流和 `client_request_id` 请求幂等。
5. 实现并灰度切换 `RedisAgentSession`，保留 SQL Session 回退开关。
6. 模型异常分类和分步骤安全重试。
7. 固定 Agent 行为评测样本。
8. 高风险问题代码级保护。
9. 统一 `BaseAgent` 与 `AgentModelFactory`。
10. 优化卦例工具输出和上下文 Token。
11. 逐步拆分 `ChatService`。
12. Prompt 版本、用户反馈和质量看板。

## 15. 暂不建议做的事情

- 不为了“多 Agent”继续拆出意图识别 Agent；当前协调 Agent 已能完成判断。
- 不重新引入 Sandbox 或 Skill；当前确定性 Function Tool 更适合起卦排盘。
- 不保存或展示模型隐藏思维过程。
- 不在缺少评测数据时频繁更换架构或模型。
- 不把 Redis 当作用户、卦例、完整聊天记录或长期摘要的唯一持久化存储。
- 不在没有回退开关和恢复测试时，一次性删除现有 SQL Agent Session 数据。

## 16. 完成定义

当以下条件满足时，可以认为 Agent 模块从“功能完整 MVP”进入“可稳定迭代”阶段：

- 每轮 Agent Run 可追踪、可统计、可定位失败。
- 同一会话没有并发运行和重复请求问题。
- 模型和工具错误有明确分类与安全恢复策略。
- 核心对话场景有稳定、可重复执行的评测集。
- 高风险问题有代码级兜底。
- Prompt、模型、Token、耗时和用户反馈可以关联分析。
