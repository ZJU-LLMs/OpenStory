![Cover](assets/Cover.jpg)
<h1 align="center">
  <img src="assets/logo.png" height="70" alt="Logo" align="absmiddle">&nbsp;OpenStory (万象谱)
</h1>

<div align="center">

[简体中文](README.md) | [English](README_en.md) 

</div>

## 🌟  重要新闻

**✨ Story 3《WorldKernel》现已上线！**
现在只需一句话，就能生成属于你的可交互故事世界。无论是海底城邦、轨道集市，还是神话森林、末日列车，`examples/WorldKernel` 都会把你的设想拆解为角色、地点、路径与规则，并接入多智能体模拟。启动后打开 [http://localhost:8100/](http://localhost:8100/) 即可开始创造。

**✨ OpenStory 现已支持 DeepSeek Harness 插件！**
现在可以通过 `dsh-openstory` 将 OpenStory 多智能体推演接入 DeepSeek Harness，让 agent 直接启动模拟、查看角色、下达指令并逐回合推进故事。查看 [DSH 插件配置与使用指南](dsh-openstory/README.zh.md)。

**✨《西部世界》现已上线！**
全新故事《西部世界》现已加入 OpenStory。进入西部世界主界面后，你可以选择自由模式，观察角色在乐园循环中的自主行动；也可以进入剧情模式，扮演一名 Host，在记忆、觉醒与监管者的重重压力下，亲手推演逃离乐园的故事。

**✨ 我们的 OpenStory Launcher 客户端上线啦！**  
之前各位穿越者经常反馈不知道如何安装游戏，让我们意识到了当前的门槛太高的问题。于是我们连夜开发了客户端版本，支持一键点击即玩！前往 [release](https://github.com/ZJU-LLMs/OpenStory/releases) 下载！快点参与到红楼梦世界来吧！

**✨ 我们的项目被《新智元》报道啦！**  
https://mp.weixin.qq.com/s/1Z9LAoombuvMGBkpyyMCrg

**✨ 《红楼梦》的剧情模式现已上线！**  
全新剧情模式将带你走进《红楼梦》，以复兴大观园为目标。你可自由向角色下达指令，AI 会根据你的选择推演剧情走向，影响整个复兴进程。同时新增故事回溯功能，可回到过往节点重选。你的每一次抉择都会衍生全新剧情分支，体验不断变化的故事冒险。

##
OpenStory 是一个基于大语言模型（LLM）和 [Agent-Kernel](https://github.com/ZJU-LLMs/Agent-Kernel) 开发的多智能体推演与模拟框架。

**✨ 我们诚挚地邀请大家一起来共创故事！** 无论你是想续写经典、打破原著框架，还是创造一个完全属于你的平行宇宙，只要你的故事创意足够有趣、脑洞足够大，欢迎提交 PR！我们会将精彩的推演剧本和自定义配置合并到项目中，让更多人看到你的杰作。

## 🌟 核心特性

- **基于 Agent-Kernel 的动态框架**：底层采用强大的 Agent-Kernel 架构，支持在推演过程中**动态增删智能体**。告别僵化的静态设定，赋予系统无限的扩展能力，让你尽情发挥想象力！
- **一比一复刻的红楼梦大观园前端**：精心打造的 1:1 仿真可视化交互界面。你不仅能直观地看到智能体在地图上的动态轨迹，更能随时点击查看人物的详细信息、状态变化与互动档案。
- **富有冲击力的推演剧情**：打破常规的刻板对话，智能体之间将产生深度的化学反应。系统能够根据性格设定与环境变化，自动生成跌宕起伏、精彩绝伦且极具戏剧张力与冲击力的推演剧情！
- **丰富的插件化机制与高可配性**：涵盖智能体感知、计划、执行、反思等完整生命周期插件，并支持通过 YAML 文件灵活管理系统、环境、动作与智能体配置。
- **一句话生成世界（WorldKernel）**：输入一句自然语言设想，系统自动生成角色、地点、路径与规则，并接入可交互的多智能体模拟。

## 📖 Story 1: 红楼梦 (Dream of the Red Chamber)
![Cover](assets/Story1.png)
作为 OpenStory 框架的第一个官方落地故事，本项目中的 `examples/story_of_the_stone` 示例以中国古典名著《红楼梦》为背景。我们利用多智能体系统（MAS）技术，在一比一仿真的红楼梦大观园地图中，生动模拟了书中人物的日常行为、社交互动与故事推演。在这里，你可以看到林黛玉的敏感多思、贾宝玉的叛逆多情，以及整个贾府在历史车轮下的命运交织。

## 📖 Story 2: 西部世界（West World）
![Cover](assets/Story2.png)
作为 OpenStory 框架的第二个官方故事，本项目中的 `examples/WestWorld` 示例以科幻剧集《西部世界》为背景，构建了一座由多智能体共同驱动的仿真乐园。Host 会感知场景、规划行动、移动交谈并积累记忆；那些反复出现的日常、难以解释的熟悉感与他人的只言片语，也会让他们逐渐发现循环背后的真相。在这里，你既可以在自由模式中观察 Dolores、Maeve、Teddy 等角色的自主互动与命运分岔，也可以在剧情模式中扮演一名 Host，选择结盟、隐藏异常或逃离乐园，并在 Overseer 的监控与干预下亲手推演属于自己的觉醒故事。

## 📖 Story 3: WorldKernel（一个想法，一个世界）
![Cover](assets/Story3.png)
作为 OpenStory 框架的第三个官方故事，本项目中的 `examples/WorldKernel` 不再绑定单一原著，而是把一句自然语言设想，生成可以运行的故事世界。系统会拆解出角色、地点、路径与规则，再接入多智能体模拟：你可以创造「西游记·大闹天宫」，也可以生成一座靠交易记忆运转的风暴档案城。打开 [http://localhost:8100/](http://localhost:8100/) 写下你的想法，或继续本地已生成的世界，亲手推演接下来的故事。

## 🚀 快速开始

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

在项目根目录下，选择要运行的故事并执行相应命令。

#### 红楼梦

```bash
python -m examples.story_of_the_stone.run_simulation
```

启动过程中：
1. 系统会初始化 `Ray` 的运行时环境。
2. 构建并加载所有的插件、配置文件和《红楼梦》人物数据。
3. 启动 API Server，默认监听在 `0.0.0.0:8000`。

#### 西部世界

启动前，请确认 Redis 已运行，并在 `examples/WestWorld/configs/models_config.yaml` 中填写可用的 OpenAI-compatible 模型配置。西部世界与红楼梦都会使用 `8000` 端口，因此请勿同时运行两者。

```bash
python -m examples.WestWorld.run_all
```

启动完成后，打开 西部世界主界面
```bash
http://localhost:8000/frontend/index.html
```
并在页面中选择游玩自由模式或剧情模式。

详细玩法和模型配置请参阅 [西部世界说明](examples/WestWorld/README.md)。

#### WorldKernel

WorldKernel 使用 `8100` 端口，可与红楼梦 / 西部世界分开启动。启动前请在 `examples/WorldKernel/configs/models.yaml` 中填写可用的 OpenAI-compatible 模型配置，或设置环境变量 `WORLDKERNEL_API_KEY`。进入模拟时仍需本地 Redis。

```bash
pip install -e "examples/WorldKernel"
python -m worldkernel.server
```

启动完成后，打开 WorldKernel 主界面：
```bash
http://localhost:8100/
```
在页面中描述你想生成的世界，或选择已有本地世界进入模拟。

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

QQ交流群:1091827223

[友链:LINUX.DO](https://linux.do)
