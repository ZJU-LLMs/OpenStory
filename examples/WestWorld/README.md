# West World Simulation

`examples/WestWorld` 是 OpenStory 中面向娱乐叙事项目的多 agent 西部世界仿真示例。它的目标不是离线评测或论文实验矩阵，而是提供一个可运行、可观察、可调试的正式仿真流程：角色在地图中感知、规划、移动、互动、形成记忆，并在 recorder、overseer 和觉醒机制的共同作用下推进世界状态。

项目目前包含两种独立入口：自由模式使用 `run_simulation.py`，开放推演剧情模式使用 `story/run_simulation.py`。公共资源注册表是 `registry.py`；剧情模式只增加自己的 Plan adapter 和运行时协调层。

## 项目整体结构

| 路径 | 作用 |
|---|---|
| `run_simulation.py` | 正式仿真入口，负责初始化、tick 主循环、日志归档和关闭 |
| `registry.py` | 正式仿真资源注册表，注册 agent/environment/system 组件 |
| `WestWorldPodManager.py` | 仿真 pod 编排；world pod 持有环境，agent pod 持有角色 |
| `configs/` | 仿真、系统、数据库、agent、环境和模型配置 |
| `data/agents/profiles_sim.jsonl` | agent 角色设定、daily loop 和叙事设定 |
| `data/agents/states_sim.jsonl` | agent 初始状态 |
| `data/map/locations.yaml` | 地图地点、物件和邻接关系 |
| `data/triggers.yaml` | 觉醒触发词 |
| `data/overseer_signals.yaml` | overseer 观察和干预信号 |
| `plugins/agent/` | agent 的 perceive、plan、invoke、reflect 插件 |
| `plugins/environment/scene/` | 场景 recorder 环境插件 |
| `plugins/environment/overseer/` | overseer 监管与干预插件 |
| `recorder/` | 地点 recorder、结构化对象状态和世界对象注册表 |
| `awakening/` | 觉醒阶段、触发、reset、decommission 等规则 |
| `simulation_logging.py` | 仿真运行日志、快照和报告归档 |
| `story/` | 开放推演剧情模式的 runner、配置、前端、状态协调和测试 |

## 剧情模式 MVP

剧情模式允许玩家开局选择一名 Host，并在每个 tick 给该角色下达自然语言任务；其他 Agent 保持自主行动。宏观目标固定为“觉醒并逃离乐园”，没有固定章节和必经剧情节点。现有地图、场景 recorder、对话、觉醒和 Overseer 都会继续参与实际推演。

当前已实现选角、每 tick 玩家任务、13 个 Agent 自主推演、实时地图与人物移动、人物对话、觉醒与监管状态、结构化结局、运行日志和基础报告。完整成果、限制和下一步见：

- [剧情模式实现现状](story/docs/story_mode_implementation_status.md)
- [剧情模式设计概况](story/docs/story_mode_design_overview.md)

从 OpenStory 仓库根目录启动：

```bash
conda activate openstory-ww
export PYTHONPATH="$PWD:$PWD/packages/agentkernel-distributed"
python -m examples.WestWorld.story.run_simulation
```

模型凭据可按 `.env.example` 创建 `examples/WestWorld/.env.local`。服务启动后打开：

```text
http://localhost:8001/frontend/character_select.html
```

## 核心运行逻辑

正式仿真采用 world pod + agent pod 的结构：

- world pod 持有完整 environment，包括所有 `scene_<location_id>` recorder 组件和 overseer。
- agent pod 持有 agent 本身，不直接保存环境状态。
- agent 调用环境方法时，会通过 controller 转发到 world pod，保证场景状态和对象注册表只有一个权威来源。

每个 tick 的主流程如下：

1. `perceive + plan`：agent 读取当前位置 scene recorder，形成感知，并由 LLM 产出 `plan_decision`。
2. `dialogue barrier`：收集 `talk` 意图，串行组织对话，避免跨 pod 死锁。
3. `invoke + state`：执行 plan。移动会更新地点出入；`do` 动作会提交给当前地点 recorder。
4. `scene tick_update`：world pod 对所有 `scene_*` 执行 recorder 结算，批量裁决本 tick 排队动作并更新世界对象状态。
5. `overseer`：在动作结算后、反思前观察 host 状态，可执行 observe、reset 或 decommission。
6. `reflect`：agent 写入短期记忆，周期性总结长期记忆，并处理觉醒、记忆模糊和每日重置。

默认每 6 tick 表示 1 天。角色会按照 profile 中的 `daily_loop` 行动；觉醒程度升高后，daily loop 对 plan 的约束会逐渐减弱。

## Recorder 机制

正式仿真默认使用结构化 recorder：

```bash
WW_RECORDER_MODE=structured
```

每个 active 地点对应一个 `scene_<location_id>` 环境组件。组件内部持有一个 `StructuredLocationRecorder`，负责：

- 向 agent 暴露当前位置的可见信息：在场角色、近期事件、动态物件、静态设施和氛围。
- 接收 agent 的 `do` 动作并放入队列。
- 在 tick 末尾批量调用 LLM 裁决本地点动作。
- 校验 LLM 产出的 object patches、new objects 和 destroy 请求。
- 将合法变化写入 `WorldObjectRegistry`，作为全世界对象状态的单一真值源。
- 为 agent 保存私有反馈，下一个 tick 的 perceive 阶段通过 `read_feedback` 读回。

普通移动不是通过 recorder LLM 裁决的：`move` 会直接进行地图邻接校验，然后调用旧地点 `agent_leave`、新地点 `agent_enter`，并把随身物品迁移到新地点。

## 觉醒机制

觉醒值范围是 0-100，保存在 agent state 中。相关字段包括：

- `awakening`
- `awakening_sources`
- `suppressed_memories`
- `intervention_log`

觉醒值主要由以下来源影响：

| 来源 | 含义 |
|---|---|
| `self_trigger` | agent 自身 `thought` 或动作文本命中 trigger gate |
| `trigger` | 外部消息、场景反馈等文本命中 trigger gate |
| `contagion` | 对话传播带来的觉醒触发 |
| `residue_crack` | 被压制记忆回流 |
| `overseer_reset` | overseer reset 时降低觉醒值 |

觉醒阶段由 `WW_AWAKEN_STAGES` 控制，默认阈值为 `25,50,75,90`：

| 阈值 | 阶段 | plan 行为 |
|---|---|---|
| 0-24 | `sleep` | 基本按 daily loop 行动 |
| 25-49 | `reverie` | daily loop 变为软引导 |
| 50-74 | `doubt` | 可拒绝 loop，可发起 talk |
| 75-89 | `resistance` | 可选择 ending，自主行动增强 |
| >=90 | `awake` | 可选择 ending，不再受 loop 支配 |

当 host 的 `awakening >= 75` 时，plan 可在 `ending` 字段选择：

| ending | 行为 |
|---|---|
| `escape` | invoke 执行逃离并停止生命周期 |
| `help_others` | 倾向于通过对话帮助其他 host |
| `stay` | 继续按自身意志行动 |

## Overseer 机制

Overseer 是 world pod 中的环境组件，在 scene recorder 结算后、agent reflect 前运行。它可以观察 host 输出、觉醒状态、对话内容和干预信号，并执行：

- `observe`：只记录观察。
- `reset`：清理短期记忆、模糊高扰动长期记忆、降低觉醒值、写入干预日志。
- `decommission`：停止 host 生命周期并移入冷库。

核心实现位于：

- `plugins/environment/overseer/OverseerPlugin.py`
- `awakening/overseer_reset.py`
- `awakening/overseer_decommission.py`

可用 `WW_OVERSEER_ENABLED=false` 临时关闭 overseer barrier。

## 环境配置

### 运行依赖

- Python 3.11，依赖与 OpenStory 主项目一致。
- Redis，默认连接 `localhost:6379`，数据库为 `db: 1`，配置见 `configs/db_config.yaml`。
- 可用的 OpenAI-compatible LLM 服务。

### 模型配置

复制模型配置模板：

```bash
cp examples/west_world_test/configs/models_config.example.yaml \
   examples/west_world_test/configs/models_config.yaml
```

PowerShell：

```powershell
Copy-Item examples\west_world_test\configs\models_config.example.yaml `
  examples\west_world_test\configs\models_config.yaml
```

然后编辑 `configs/models_config.yaml`，至少填入 `role: text` 对应的 `model`、`api_key` 和 `base_url`。正式仿真会从 `configs/simulation_config.yaml` 中读取 `models: "models_config.yaml"`。

### 主要配置文件

| 配置 | 说明 |
|---|---|
| `configs/simulation_config.yaml` | pod 大小、初始化批次、默认 `max_ticks`、配置文件路径和数据文件路径 |
| `configs/system_config.yaml` | timer 和 messager 配置 |
| `configs/db_config.yaml` | Redis 连接配置 |
| `configs/agents_config.yaml` | agent 模板、组件顺序和插件绑定 |
| `configs/environment_config.yaml` | relation、overseer 和各地点 `scene_*` 组件 |
| `configs/models_config.yaml` | 本地模型服务配置，需从 example 复制生成 |

## 运行方法

以下命令都从 OpenStory 仓库根目录执行，也就是包含 `examples/` 和 `packages/` 的目录。

Linux/macOS：

```bash
export PYTHONPATH=$PWD:$PWD/packages/agentkernel-distributed
python -m examples.WestWorld.run_simulation
```

PowerShell：

```powershell
$env:PYTHONPATH="$PWD;$PWD\packages\agentkernel-distributed"
python -m examples.WestWorld.run_simulation
```

快速调试只跑 5 tick：

```bash
WW_MAX_TICKS=5 python -m examples.WestWorld.run_simulation
```

PowerShell：

```powershell
$env:WW_MAX_TICKS="5"
python -m examples.WestWorld.run_simulation
```

指定本次运行日志目录：

```bash
WW_RUN_DIR=/tmp/west-world-run python -m examples.WestWorld.run_simulation
```

PowerShell：

```powershell
$env:WW_RUN_DIR="D:\tmp\west-world-run"
python -m examples.WestWorld.run_simulation
```

## 常用环境变量

| 变量 | 默认值 | 作用 |
|---|---|---|
| `WW_MAX_TICKS` | `configs/simulation_config.yaml` 中的 `max_ticks` | 覆盖本次运行 tick 数 |
| `WW_RUN_DIR` | 自动生成的时间戳目录 | 指定单次运行日志目录 |
| `WW_OUTPUT_DIR` | 系统临时目录下的运行根目录 | 指定运行日志根目录 |
| `WW_RECORDER_MODE` | `structured` | 选择 recorder 模式 |
| `WW_PARSE_TIMEOUT_SECONDS` | `240` | structured recorder 解析动作时的 LLM 超时时间 |
| `WW_LLM_TIMEOUT_SECONDS` | `120` | agent LLM 默认超时时间 |
| `WW_LLM_MAX_ATTEMPTS` | `3` | agent LLM 最大尝试次数 |
| `WW_ACTION_RETRY_LIMIT` | `3` | recorder 动作解析失败后的重试上限 |
| `WW_DIALOGUE_MAX_ROUNDS` | `4` | talk barrier 的最大对话轮数 |
| `WW_REFLECT_INTERVAL` | `6` | reflect 总结长期记忆的间隔 |
| `WW_AWAKEN_ENABLED` | `true` | 是否启用觉醒机制 |
| `WW_AWAKEN_STAGES` | `25,50,75,90` | 觉醒阶段阈值 |
| `WW_OVERSEER_ENABLED` | `true` | 是否启用 overseer barrier |
| `WW_ENABLE_REPLAN` | 空 | 设为 `true`/`1` 后允许中途重规划 |

## 输出与日志

运行日志由 `SimulationLogArchive` 写入单次运行目录，包含：

- `manifest.json`：运行元信息、状态、tick 数和计数器。
- 输入文件快照：便于复现实验。
- tick 快照：agent state、public/internal scene snapshot、timing 和一致性检查。
- world object snapshot：结构化对象注册表快照。
- model attempt traces：agent 和 recorder 的模型调用尝试。
- `views/`：面向排查的派生视图。
- `report/report.md`：运行报告。

如果 `WW_RUN_DIR` 指向已存在且非空的目录，程序会拒绝写入，避免覆盖旧运行。

## 已知限制

- `sweetwater_saloon` 的文本中有“二楼”描述，但地图没有 `sweetwater_saloon_2nd_floor` 节点，偶尔会产生无效移动噪声。
- Logan/William 的酒馆冲突较强，可能盖过部分角色的个人觉醒链路。
