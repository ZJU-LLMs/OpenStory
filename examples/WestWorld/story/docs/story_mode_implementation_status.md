# WestWorld 剧情模式实现现状

状态：MVP 已可运行，处于联调和规则校准阶段，尚未达到完整产品验收状态。

更新日期：2026-07-16

相关文档：

- 剧情模式设计概况：[story_mode_design_overview.md](story_mode_design_overview.md)
- 开放场景配置：[awakening_escape.yaml](../data/scenarios/awakening_escape.yaml)
- WestWorld 公共仿真说明：[README.md](../../README.md)

## 1. 当前产品形态

剧情模式已经按“开放推演”实现，不是固定章节或预设剧情节点：

- 开局从现有 Host 中选择一个玩家角色。
- 玩家每 tick 给该 Host 下达一条自然语言任务，或者选择自主推进。
- 其余 Agent 始终根据人格、记忆、daily loop、位置和场景自主行动。
- 固定宏观目标为“觉醒并逃离乐园”，进度直接使用玩家 Host 的 `awakening`。
- 保留原 WestWorld Overseer，异常行为可能触发观察、重置或报废。
- `escape` 为胜利，`decommission` 为失败，`reset` 后继续推演；达到 tick 上限仍未逃离也判定失败。
- 不设置固定 `beat`、必经线索、预设对话或另一套 LLM 剧情评分。

剧情模式位于 `examples/WestWorld/story/`，和自由模式使用独立 runner、前端、Agent 配置与 Redis DB 2。地图、角色数据、world pod、recorder、觉醒系统、daily loop 和 Overseer 继续复用 WestWorld 现有实现。

## 2. 已完成能力

| 模块 | 当前成果 | 状态 |
|---|---|---|
| 模式隔离 | 独立 story runner、配置、资源注册表、前端和 Redis DB 2 | 已完成 |
| 选角 | 从 profile 动态筛选 11 个 `agent_type=host` 角色 | 已完成 |
| 世界角色 | 13 个 Agent 全部进入推演；William、Logan 作为 Guest 自主行动但不可选 | 已完成 |
| 玩家任务 | 每 tick 一条自然语言 directive，支持跳过、自主推进和 500 字校验 | 已完成 |
| 任务归属 | 只能控制所选 Host；限制一条待执行任务；按 `client_action_id` 幂等 | 已完成 |
| Plan 适配 | 将 directive 注入所选 Host 的 Plan prompt，再生成合法结构化行动 | 已完成 |
| 自主推演 | 非玩家 Agent 保持原有 perceive、plan、dialogue、invoke、reflect 流程 | 已完成 |
| 对话 | `talk + target` 和带 `recipient_ids` 的 `do` 都可进入 dialogue barrier | 已完成 |
| 结局 | 结构化判断 escape、decommission、tick limit；reset 不结束本局 | 已完成 |
| 前端 | 选角、玩家状态、任务输入、地图、角色移动、对话、时间线和结局层 | 已完成 |
| 日志 | 归档 Agent、场景、世界物体、模型尝试、请求、时间线和一致性检查 | 已完成 |
| 下载报告 | 根据最终结构化状态输出文本摘要 | 部分完成 |
| 叙事报告 | 根据整局日志由 LLM 生成完整故事正文 | 尚未完成 |
| 回溯分支 | 历史 tick 恢复、分支树和分支回放 | 暂未实现 |

## 3. 一次 Tick 如何运行

1. runner 等待前端提交玩家任务，或由玩家点击“自主推进”。
2. 任务写入 Redis 的 `user_plan:{selected_agent_id}`，并绑定下一 tick。
3. `StoryWestWorldPlanPlugin` 只允许所选 Host 读取该任务。
4. 玩家任务被加入原 WestWorld Plan prompt；LLM 仍需输出符合地图和动作 schema 的 `move | do | stay | talk`。
5. 其他 Agent 独立完成感知和规划，不读取玩家任务。
6. dialogue barrier 收集对话意图并生成实际对话。
7. invoke/state 执行移动或把场景动作提交给 recorder。
8. scene recorder 批量裁决动作并更新 `WorldObjectRegistry`。
9. Overseer 检查 Host 的输出和觉醒状态，可能执行 reset 或 decommission。
10. reflect 更新记忆、觉醒和 daily loop 状态。
11. story runtime 只读检查玩家是否逃离、被报废或达到 tick 上限。
12. 后端广播 Agent、场景、地图、对话和 story state，前端完成本 tick 更新。

玩家 directive 只决定行动方向，不会直接覆盖 `plan_decision`，因此不会绕过角色人格、地图邻接和 scene recorder 裁决。

## 4. 后端与接口

核心文件：

| 文件 | 职责 |
|---|---|
| `story/run_simulation.py` | API 服务、session 协调、tick 循环、状态广播和日志归档 |
| `story/runtime.py` | 可选角色、任务校验、公开状态和结构化结局判断 |
| `story/registry.py` | 复用 WestWorld 注册表并注册 story Plan adapter |
| `story/plugins/agent/plan/StoryWestWorldPlanPlugin.py` | 读取、注入并一次性消费玩家任务 |
| `story/data/scenarios/awakening_escape.yaml` | MVP 产品规则和场景契约 |
| `story/tests/test_story_mode.py` | story runtime、任务归属、幂等、结局与对话入口测试 |

当前 HTTP 接口：

| 方法 | 路径 | 用途 |
|---|---|---|
| `GET` | `/health` | 服务和 story phase 健康检查 |
| `GET` | `/story/characters` | 返回可选 Host |
| `POST` | `/story/set_player` | 选择玩家 Host 并创建 session |
| `GET` | `/story/state` | 获取最新公开 story state |
| `POST` | `/story/directive` | HTTP 方式提交下一 tick 任务 |
| `POST` | `/story/game_restart` | 结束后清理本局并重新选角 |
| `GET` | `/story/report` | 下载本局文本摘要 |

前端主要通过 `/ws` 接收 `snapshot`、`tick_update`、`simulation_ready`、`story_progress` 和 `simulation_finished`，并通过 `set_plan`、`start_tick` 推进游戏。

## 5. 前端成果

剧情模式前端已经形成完整的可玩页面，而不是单独的调试表单：

- 选角页展示 11 个可玩 Host 的形象、身份和背景。
- 玩家区展示位置、当前决定、反馈、觉醒值、觉醒阶段和监管风险。
- 指令区支持自然语言任务、自主推进、待执行状态、历史任务和 tick 耗时提示。
- 内嵌 WestWorld TMX 地图前端，并根据每次快照更新人物位置和移动动画。
- 对话区从所有 Agent 的 `dialogue_history`、`incoming_dialogue` 和 `message_history` 聚合实际对话。
- 角色列表展示 13 个 Agent 的当前位置、活跃状态和觉醒值。
- 时间线聚合玩家任务、觉醒来源、实际对话以及 Overseer 干预。
- 结局层展示结构化胜负，支持下载记录和重新选择 Host。

对话区只展示实际发生的对话。角色没有选择 `talk`、没有带收件人的交互，或者与其他角色不在同一地点时，页面显示无对话是符合当前数据语义的，不会自动生成旁白来填充。

## 6. 运行方法

依赖 Redis、本项目的 Python 环境和一个 OpenAI-compatible 模型服务。所有命令从 OpenStory 仓库根目录执行。

```bash
conda activate openstory-ww
cp examples/WestWorld/.env.example examples/WestWorld/.env.local
```

在 `.env.local` 中填写本地凭据；该文件已被 `.gitignore` 忽略，不应提交真实 key：

```dotenv
WW_API_KEY=<your-key>
WW_BASE_URL=<openai-compatible-base-url>
WW_MODEL=<model-name>
```

启动剧情模式：

```bash
export PYTHONPATH="$PWD:$PWD/packages/agentkernel-distributed"
python -m examples.WestWorld.story.run_simulation
```

打开：

```text
http://localhost:8001/frontend/character_select.html
```

快速联调可以减少 tick 数：

```bash
WW_MAX_TICKS=5 python -m examples.WestWorld.story.run_simulation
```

runner 在安装 `python-dotenv` 时自动读取 `examples/WestWorld/.env.local`；如果未安装，需要在 shell 中显式 `export WW_API_KEY`、`WW_BASE_URL` 和 `WW_MODEL`。

## 7. 当前验证结果

截至 2026-07-16，已验证：

- story 单元测试共 12 项，覆盖选角过滤、reset 非终局、三种结局、任务注入、任务归属和幂等、失败回滚以及对话意图收集。
- Python 模块可以编译，story 前端 JavaScript 通过语法检查。
- 选角页和游戏页可由 `http://localhost:8001` 正常访问。
- 使用 `deepseek-v4-flash` 完成真实模型联调，模型请求返回 HTTP 200。
- 一次保留的实机运行 `20260716_151510_186518` 已完成 11 tick，记录 13 个 Agent、202 次模型尝试、角色移动、人物对话和 Overseer reset。
- 该运行记录的场景错误和一致性违规均为 0；运行目录位于 `examples/WestWorld/output/sim_runs/`。

`output/` 是本地运行产物，不应整目录提交。报告和输入快照中的模型配置会做脱敏，但提交前仍应检查日志内容。

## 8. 已知问题

### 推演延迟

一个 tick 需要 13 个 Agent 的规划，加上对话和场景裁决，真实运行可能持续数十秒。前端已经显示当前阶段和耗时，但玩家仍需等待后端完成整个 tick，当前没有流式展示单个 Agent 的中间结果。

### Overseer 误报和干预强度

当前默认 `WW_OVERSEER_EMBEDDING_ONLY=true`。只要 embedding gate 超过阈值，`high/mid` 信号级别不会参与二次裁决，Host 会直接 reset。在已观察运行中，“不能在这里耽搁”与“我要离开这里”等语义相近但意图相反的文本产生过误报。

默认 `WW_OVERSEER_SIGNAL_TAU=0.55`，同一进程内一个 Host 累计三次 reset 后会按 `WW_OVERSEER_RESET_MAX=3` 升级为 decommission。这个策略当前偏激进，需要在剧情模式正式验收前校准。

`observe` 目前只写服务端日志，没有写入 Agent 的 `intervention_log`，因此前端监管时间线主要能看到 reset、decommission 和 escape。

### 玩家与对话记录

- 当前没有独立的“主角行为历史”数据流，玩家过去的 thought、非对话动作和场景反馈主要散落在 tick 快照与日志中。
- 角色移动和对话来自实际 Agent 决策，因此玩家角色可能连续多个 tick 没有对话。
- 模型无响应或产生降级 `stay` 时，directive 仍可能被标记为已消费；前端尚未完整区分“已消费”和“按玩家意图成功执行”。

### 报告与回溯

- `/story/report` 当前是结构化纯文本摘要，还不是设计目标中的完整 LLM 叙事报告。
- 场景 YAML 的产品规则已经被 runner 使用，但元数据仍标记为 `draft`。
- 历史 tick 回退、世界状态恢复、分支树和分支回放仍不在当前实现中。

## 9. 下一步优先级

1. 降低 Overseer 误报：引入信号级别、否定语义和上下文二次判断，并把 observe 结构化持久化。
2. 完善任务结果：区分“任务已读取”“结构化计划生成成功”“场景执行成功”，把失败原因返回前端。
3. 增加玩家事件流：单独保存玩家每 tick 的 directive、thought、decision、feedback、移动和对话。
4. 优化 tick 体验：分阶段广播 Agent 进度，评估并发、模型调用数和对话轮数。
5. 使用完整运行日志生成最终故事正文，同时保持结构化 outcome 为唯一胜负来源。
6. 在上述 MVP 稳定后，再单独设计回溯与分支恢复。
