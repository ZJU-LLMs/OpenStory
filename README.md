![Cover](assets/Cover.jpg)
<h1 align="center">
  <img src="assets/logo.png" height="70" alt="Logo" align="absmiddle">&nbsp;OpenStory (万象谱)
</h1>

<div align="center">

[English](README.md) | [简体中文](README_zh.md)

</div>

## 🌟  重要新闻

**✨ 《红楼梦》的剧情模式模式现已上线！**  
全新剧情模式将带你走进《红楼梦》，以复兴大观园为目标。你可自由向角色下达指令，AI 会根据你的选择推演剧情走向，影响整个复兴进程。同时新增故事回溯功能，可回到过往节点重选。你的每一次抉择都会衍生全新剧情分支，体验不断变化的故事冒险。

##
OpenStory 是一个基于大语言模型（LLM）和 [Agent-Kernel](https://github.com/ZJU-LLMs/Agent-Kernel) 开发的多智能体推演与模拟框架。

**✨ 我们诚挚地邀请大家一起来共创故事！** 无论你是想续写经典、打破原著框架，还是创造一个完全属于你的平行宇宙，只要你的故事创意足够有趣、脑洞足够大，欢迎提交 PR！我们会将精彩的推演剧本和自定义配置合并到项目中，让更多人看到你的杰作。

## 🌟 核心特性

- **基于 Agent-Kernel 的动态框架**：底层采用强大的 Agent-Kernel 架构，支持在推演过程中**动态增删智能体**。告别僵化的静态设定，赋予系统无限的扩展能力，让你尽情发挥想象力！
- **一比一复刻的红楼梦大观园前端**：精心打造的 1:1 仿真可视化交互界面。你不仅能直观地看到智能体在地图上的动态轨迹，更能随时点击查看人物的详细信息、状态变化与互动档案。
- **富有冲击力的推演剧情**：打破常规的刻板对话，智能体之间将产生深度的化学反应。系统能够根据性格设定与环境变化，自动生成跌宕起伏、精彩绝伦且极具戏剧张力与冲击力的推演剧情！
- **丰富的插件化机制与高可配性**：涵盖智能体感知、计划、执行、反思等完整生命周期插件，并支持通过 YAML 文件灵活管理系统、环境、动作与智能体配置。

## � Story 1: 红楼梦 (Dream of the Red Chamber)
![Cover](assets/Story1.png)
作为 OpenStory 框架的第一个官方落地故事，本项目中的 `examples/deduction` 示例以中国古典名著《红楼梦》为背景。我们利用多智能体系统（MAS）技术，在一比一仿真的红楼梦大观园地图中，生动模拟了书中人物的日常行为、社交互动与故事推演。在这里，你可以看到林黛玉的敏感多思、贾宝玉的叛逆多情，以及整个贾府在历史车轮下的命运交织。

## � Story 2: Coming Soon
![Cover](assets/Story2.png)
我们正在积极开发新的故事，敬请期待！

## �🚀 快速开始

> **📚 想要更详细的操作指南？**
> 我们为您准备了详尽的图文教程，带您从零开始玩转红楼梦沙盘世界：
> 👉 [点击查看 OpenStory 红楼梦互动教程](tutorial/Story_Of_Stone/tutorial_zh.md)

### 1. 环境准备

- **Python 版本**：推荐 Python 3.10 或以上。
- **中间件**：
  - **Redis**：作为默认的数据总线与缓存，请确保本地 Redis 服务已启动并在 `6379` 端口监听。

### 2. 安装依赖
```bash
git clone https://github.com/ZJU-LLMs/Agent-Kernel.git
cd Agent-Kernel

pip install -e "packages/agentkernel-distributed[all]"

cd ../../..
```

### 3. 运行推演系统

在项目根目录下，执行以下命令启动模拟引擎：

```bash
python -m examples.deduction.run_simulation
```

启动过程中：
1. 系统会初始化 `Ray` 的运行时环境。
2. 构建并加载所有的插件、配置文件和《红楼梦》人物数据。
3. 启动 API Server，默认监听在 `0.0.0.0:8000`。

### 4. 访问可视化界面
![Frontend Preview](assets/frontend.png)
当看到终端输出 `API Server started at http://0.0.0.0:8000` 后，在浏览器中打开以下地址：

👉 [http://localhost:8000/frontend/index.html](http://localhost:8000/frontend/index.html)

在界面中，你可以：
- 查看大观园等场景地图。
- 点击**开始推演** / **下一回合 (Tick)** 观察人物的行动与交互。
- 点击左侧人物列表，查看详细的“人物档案”与实时状态。

## ⚙️ 核心配置说明

在 `configs/` 目录下，您可以自定义推演规则：

- `simulation_config.yaml`：全局主入口，配置 Pod 数量、最大 Tick 数及各配置文件的路径。
- `models_config.yaml`：配置 LLM 模型接口及参数。
- `system_config.yaml`：系统级配置，如 Messager（消息总线）与 Timer（时钟）。

## 🛠️ 数据生成

如果您需要修改或重新生成《红楼梦》的人物数据，可以参考 `data/raw/` 目录下的生成脚本。例如：
- `profile_generator.py`：基于 `database.jsonl` 过滤存活角色并生成唯一的编码 ID 与基础设定。
