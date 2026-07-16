# WestWorld

`examples/WestWorld` 是一个可交互的多 Agent 西部世界仿真。角色会感知场景、规划行动、移动、对话、形成记忆，并在觉醒与监管机制的影响下改变自己的行为。项目提供自由模式和剧情模式，两者复用同一张地图、角色资料、场景裁决、觉醒系统与 Overseer。

## 开始游玩

从 OpenStory 仓库根目录启动。开始前需要本机 Redis、可用的 OpenAI-compatible 模型服务，以及 `configs/models_config.yaml` 中的模型配置。

```powershell
cd D:\proj\OpenStory
conda activate mastest
python -m examples.WestWorld.run_all
```

统一入口会启动两个独立进程：

| 服务 | 地址 | 用途 |
|---|---|---|
| 自由模式 | `http://localhost:8000/frontend/index.html` | 模式选择、自由仿真与全局观测 |
| 剧情模式 | `http://localhost:8001/frontend/character_select.html` | 选角和玩家指令驱动的开放推演 |

保留终端运行；按 `Ctrl+C` 会停止两个模式。`run_all.py` 会给两个 Ray 会话使用独立临时目录，避免本地运行时冲突。

> 请通过 `localhost` 或本机实际局域网 IP 访问页面，不要在浏览器中使用 `0.0.0.0`。自由模式首页跳转剧情模式时默认目标为端口 `8001`。

### 模型与代理

剧情模式会自动读取 `examples/WestWorld/.env.local`（安装 `python-dotenv` 时），可写入：

```text
WW_API_KEY=your-api-key
WW_BASE_URL=https://your-openai-compatible-endpoint/v1
WW_MODEL=your-model-name
```

首次运行还会加载嵌入模型 `BAAI/bge-small-zh-v1.5` 来识别觉醒信号。网络需要代理时，在启动前设置：

```powershell
$env:HTTP_PROXY = "http://127.0.0.1:7890"
$env:HTTPS_PROXY = "http://127.0.0.1:7890"
```

## 两种玩法

### 自由模式

在 `8000` 首页点击 Start，选择 **Free simulation**。这是观察者视角：所有角色按自身人格、记忆和 daily loop 自主行动。

1. 等待后端完成初始化，状态栏显示可用快照。
2. 在地图上拖动浏览，使用滚轮缩放；缩到最小时，地点名称会直接显示在地点中央。
3. 点击角色、地点或左侧列表查看状态、记忆线索、当前位置与近期事件。
4. 点击 **Advance Tick** 推进一个 tick，观察对话、移动、场景裁决、觉醒与监管事件如何影响世界。

自由模式适合观察角色之间的连锁反应，以及不同运行参数对世界走向的影响。

### 剧情模式：觉醒与逃离

在 `8000` 首页选择 **Story mode**，或直接打开 `8001` 的选角页。

1. 选择一名 Host。Dolores、Maeve、Teddy 等 Host 都可游玩；William 和 Logan 是自主行动的 Guest，不能选择。
2. 进入游戏页后，在右侧输入一条自然语言任务，例如“去找 Maeve，问她是否记得昨天”。
3. 点击 **执行任务并推进**，或点击 **自主推进** 让角色自行规划。
4. 每条任务只对下一 tick 生效；Plan 会结合角色人格、当前位置、地图邻接和场景状态生成合法的 `move`、`do`、`stay` 或 `talk` 行为。
5. 观察中央地图、右侧对话/世界角色/本局时间线，以及左侧的觉醒度和监管记录。

剧情模式最多运行 40 tick。玩家 Host 成功逃离为胜利；被监管者报废，或 tick 用尽仍未逃离，则本局失败。重置不会立即结束游戏，但会清理短期记忆、模糊高扰动记忆，并将觉醒度降回上一阶段。

## 故事概述

西部世界是一座由公司维护的仿真乐园。Host 每天重复被分配的生活：酒馆开门、警长巡街、农场劳作，昨日的伤痛在下一次循环开始前被悄然修复。

但记忆并没有真正消失。重复的台词、无法解释的熟悉感、他人留下的只言片语，以及不合常理的场景反馈，会逐渐让 Host 发现自己正在循环。玩家在剧情模式中扮演其中一名 Host，决定是追查这些裂缝、与其他角色结盟、隐藏异常，还是尝试离开乐园。

这不是固定章节的剧本。其他角色仍会独立行动，场景裁决会改变世界状态，角色可能帮助你、误解你，或把你的异常带给监管者。Overseer 会监控可疑言行：它可能观察、执行记忆重置，或者在觉醒过高时将 Host 封存至冷库。因此每局故事都由真实推演生成，而不是预设路线。

## 项目结构

| 路径 | 作用 |
|---|---|
| `run_all.py` | 同时启动自由模式与剧情模式的顶层入口 |
| `run_simulation.py` | 自由模式 runner、tick 主循环与 `8000` 服务 |
| `story/run_simulation.py` | 剧情模式 runner、session 协调与 `8001` 服务 |
| `frontend/` | 自由模式地图、模式选择和共享嵌入地图前端 |
| `story/frontend/` | 剧情模式的选角页和游戏页 |
| `configs/` | 自由模式与共享环境、模型、系统配置 |
| `story/configs/` | 剧情模式的 Agent、Redis 与仿真配置 |
| `data/` | 角色资料、初始状态、地点、关系与觉醒信号 |
| `plugins/`、`recorder/`、`awakening/` | Agent 行为、场景裁决、世界对象、记忆和觉醒规则 |
| `WestWorldPodManager.py` | world pod 与 agent pod 的 tick 编排 |

剧情模式的设计与实现状态见：

- [剧情模式设计概况](story/docs/story_mode_design_overview.md)
- [剧情模式实现现状](story/docs/story_mode_implementation_status.md)

## 一次 Tick 如何运行

```text
感知与规划 -> 对话编排 -> 执行行动 -> 场景批量裁决 -> Overseer -> 反思与记忆更新
```

1. Agent 从当前地点读取可见角色、事件、物件和氛围，生成计划。
2. 对话 barrier 收集并组织跨 pod 的对话。
3. 移动会经过地图邻接校验；场景动作交由对应地点的 recorder 排队。
4. world pod 在 tick 末批量裁决场景动作，并更新 `WorldObjectRegistry`。
5. Overseer 检查 Host 的觉醒度和输出，决定观察、重置或报废。
6. Agent 反思经历、更新短期/长期记忆和觉醒状态。

默认每 6 tick 代表一天。觉醒度从 0 到 100；达到 `25/50/75/90` 时依次进入 reverie、doubt、resistance 与 awake 阶段，daily loop 对角色的约束会逐步减弱。

## Overseer 与觉醒

Overseer 只监管 Host。它会分析计划语言、反馈和对话中的觉醒症状，并结合当前觉醒度干预：

| 动作 | 结果 |
|---|---|
| `observe` | 仅记录观察 |
| `reset` | 清短期记忆、模糊高扰动记忆、觉醒度降一阶段、送回 loop origin |
| `decommission` | 停止 Host 生命周期并移至 `cold_storage` |

默认的语义匹配阈值为 `WW_OVERSEER_SIGNAL_TAU=0.72`。数值越高，监管者越不容易把相近台词判为觉醒症状。可在启动前调整：

```powershell
$env:WW_OVERSEER_SIGNAL_TAU = "0.80"
python -m examples.WestWorld.run_all
```

常用环境变量：

| 变量 | 默认值 | 作用 |
|---|---|---|
| `WW_MAX_TICKS` | 配置文件值（40） | 覆盖单局最大 tick 数 |
| `WW_STORY_PORT` | `8001` | 剧情模式服务端口 |
| `WW_OVERSEER_ENABLED` | `true` | 启用或关闭监管者 |
| `WW_OVERSEER_SIGNAL_TAU` | `0.72` | 监管症状的语义匹配阈值 |
| `WW_OVERSEER_DECOMMISSION_AWAKENING` | `90` | 强制报废的觉醒度阈值 |
| `WW_RUN_DIR` | 自动生成 | 指定运行日志目录 |
| `WW_OUTPUT_DIR` | 临时运行目录 | 指定日志根目录 |

## 输出与排查

每次运行都会由 `SimulationLogArchive` 写入输入快照、tick 状态、场景状态、世界对象、模型调用摘要与运行报告。默认输出在 `output/sim_runs/`；使用 `WW_RUN_DIR` 时，目标目录必须不存在或为空。

若剧情模式页面无法打开，先确认 `http://localhost:8001/health` 返回 JSON。若嵌入模型首次下载缓慢，请检查代理，或预先下载 `BAAI/bge-small-zh-v1.5` 到 Hugging Face 缓存。
