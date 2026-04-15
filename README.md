![Cover](assets/Cover.jpg)
<h1 align="center">
  <img src="assets/logo.png" height="70" alt="Logo" align="absmiddle">&nbsp;OpenStory (Wanxiangpu)
</h1>

<div align="center">

[English](README.md) | [简体中文](README_zh.md)

</div>

OpenStory is a multi-agent deduction and simulation framework developed based on Large Language Models (LLMs) and [Agent-Kernel](https://github.com/ZJU-LLMs/Agent-Kernel).

**✨ We sincerely invite everyone to co-create stories with us!** Whether you want to continue a classic, break the original plot, or create a parallel universe entirely your own, as long as your story idea is interesting and imaginative enough, feel free to submit a PR! We will merge brilliant deduction scripts and custom configurations into the project, letting more people see your masterpiece.

## 🌟 Core Features

- **Dynamic Framework based on Agent-Kernel**: Built on the powerful Agent-Kernel architecture, it supports **dynamic addition and removal of agents** during the simulation. Say goodbye to rigid static settings, endowing the system with infinite expansibility, and letting your imagination run wild!
- **1:1 Replicated Grand View Garden Frontend**: A meticulously crafted 1:1 simulated visual interactive interface. Not only can you intuitively observe the dynamic trajectories of agents on the map, but you can also click at any time to view detailed character information, status changes, and interaction archives.
- **Impactful Story Deduction**: Breaking away from conventional, rigid dialogues, agents will generate profound chemical reactions with each other. The system can automatically generate a deduction story full of ups and downs, brilliance, dramatic tension, and impact, based on character traits and environmental changes!
- **Rich Plugin Mechanism & High Configurability**: Covers the complete lifecycle plugins of agents including perception, planning, execution, and reflection. It also supports flexible management of system, environment, action, and agent configurations through YAML files.

## 📖 Story 1: Dream of the Red Chamber

As the first official implemented story of the OpenStory framework, the `examples/deduction` example in this project is set against the backdrop of the Chinese classical novel *Dream of the Red Chamber* (*Hongloumeng*). Utilizing Multi-Agent System (MAS) technology, we vividly simulate the daily behaviors, social interactions, and story evolution of the characters within a 1:1 scale map of the Grand View Garden. Here, you can witness Lin Daiyu's sensitive thoughtfulness, Jia Baoyu's rebellious affection, and the intertwined destiny of the entire Jia mansion under the wheel of history.
![Cover](assets/Story1.png)

## 🚀 Story 2: Coming Soon
![Cover](assets/Story2.png)
We are actively developing new stories, stay tuned!

## 🚀 Quick Start

> **📚 Looking for a more detailed guide?**
> We have prepared a comprehensive step-by-step tutorial with images to help you explore the sandbox world of *The Story of the Stone*:
> 👉 [Click here for the OpenStory Tutorial](tutorial/Story_Of_Stone/tutorial_en.md)

### 1. Environment Preparation

- **Python Version**: Python 3.10 or above is recommended.
- **Middleware**:
  - **Redis**: Serves as the default data bus and cache. Please ensure that the local Redis service is running and listening on port `6379`.

### 2. Install Dependencies
```bash
git clone https://github.com/ZJU-LLMs/Agent-Kernel.git
cd Agent-Kernel

pip install -e "packages/agentkernel-distributed[all]"

cd ../../..
```

### 3. Run the Simulation System

In the project root directory, execute the following command to start the simulation engine:

```bash
python -m examples.deduction.run_simulation
```

During startup:
1. The system will initialize the `Ray` runtime environment.
2. Build and load all plugins, configuration files, and *Dream of the Red Chamber* character data.
3. Start the API Server, listening on `0.0.0.0:8000` by default.

### 4. Access the Visual Interface
![Frontend Preview](assets/frontend.png)
When you see the terminal output `API Server started at http://0.0.0.0:8000`, open the following address in your browser:

👉 [http://localhost:8000/frontend/index.html](http://localhost:8000/frontend/index.html)

In the interface, you can:
- View scene maps such as the Grand View Garden.
- Click **Start Deduction (开始推演)** / **Next Tick (下一回合)** to observe character actions and interactions.
- Click the character list on the left to view detailed "Character Profiles" and real-time statuses.

## ⚙️ Core Configuration Guide

In the `configs/` directory, you can customize the deduction rules:

- `simulation_config.yaml`: The global main entry point, configuring the number of Pods, maximum Ticks, and the paths of various configuration files.
- `models_config.yaml`: Configures the LLM interfaces and parameters.
- `system_config.yaml`: System-level configurations, such as Messager (message bus) and Timer (clock).

## 🛠️ Data Generation

If you need to modify or regenerate the character data of *Dream of the Red Chamber*, you can refer to the generation scripts in the `data/raw/` directory. For example:
- `profile_generator.py`: Filters surviving characters based on `database.jsonl` and generates unique encoded IDs and basic profiles.

## Star History

<a href="https://www.star-history.com/?repos=ZJU-LLMs%2FOpenStory&type=date&logscale=&legend=top-left">
 <picture>
   <source media="(prefers-color-scheme: dark)" srcset="https://api.star-history.com/chart?repos=ZJU-LLMs/OpenStory&type=date&theme=dark&legend=top-left" />
   <source media="(prefers-color-scheme: light)" srcset="https://api.star-history.com/chart?repos=ZJU-LLMs/OpenStory&type=date&legend=top-left" />
   <img alt="Star History Chart" src="https://api.star-history.com/chart?repos=ZJU-LLMs/OpenStory&type=date&legend=top-left" />
 </picture>
</a>

QQ交流群:1091827223

[友链:LINUX.DO](https://linux.do)
