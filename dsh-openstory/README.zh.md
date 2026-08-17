# dsh-openstory：安装、配置与使用指南

[English](README.md) | 简体中文

`dsh-openstory` 是 OpenStory 的 DeepSeek Harness（DSH）插件。插件已发布到 npm：<https://www.npmjs.com/package/dsh-openstory>。

它将 OpenStory 注册为 DSH 工具，并在 DSH 设置界面中提供 OpenStory 配置入口。启用 `autoStart` 后，只需启动 DSH；首次打开 OpenStory 前端或调用相关工具时，插件会自动启动 OpenStory 后端。

## 1. 前置条件

- Node.js 22 或更高版本
- 已安装 DeepSeek Harness，并至少初始化过一个 `web` profile
- OpenStory 源码库
- Python 3.11 至 3.13；Windows 推荐 Python 3.12
- Redis 运行在 `localhost:6379`；推荐 Redis 7
- 可用的 OpenAI-compatible 模型 API

不建议使用 Python 3.14：OpenStory 固定的 Ray 版本目前没有对应的 Windows wheel。

## 2. 准备 OpenStory

在 OpenStory 仓库根目录执行。

### Windows + Conda

```powershell
conda create -n openstory python=3.12 -y
conda activate openstory
python -m pip install --upgrade pip
python -m pip install -e "packages/agentkernel-distributed[all]"
```

查询当前环境的 Python 路径：

```powershell
python -c "import sys; print(sys.executable)"
```

### Linux/macOS + venv

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e "packages/agentkernel-distributed[all]"
```

在 `examples/story_of_the_stone/configs/models_config.yaml` 中配置模型：

```yaml
- name: OpenAIProvider
  model: deepseek-chat
  api_key: YOUR_API_KEY
  base_url: https://api.deepseek.com/v1
  capabilities:
    - chat
```

不要将真实 API Key 提交到 Git。

## 3. 从 npm 安装插件

如果 `dsh` 已在 `PATH` 中：

```powershell
dsh plugin --profile web add dsh-openstory@0.2.0
```

如果没有全局 `dsh` 命令：

```powershell
npx @deepseek-ai/dsh plugin --profile web add dsh-openstory@0.2.0
```

安装命令会自动将包加入 profile 的依赖和 `dsh.profile.bundles`，无需手工修改 profile 的 `package.json`。

新版本刚发布时，DSH 可能显示 `ERR_PNPM_MINIMUM_RELEASE_AGE_VIOLATION`。这是供应链保护策略，不是插件损坏；等待策略规定的时间后重试，不要随意关闭安全策略。

## 4. 在 DSH 设置中配置

启动 DSH：

```powershell
dsh web
```

没有全局命令时使用：

```powershell
npx @deepseek-ai/dsh web
```

打开 DSH Web 界面后进入：

```text
设置 → OpenStory → 打开配置文件
```

系统编辑器会打开当前安装包实际加载的 `cordis.patch.yml`。至少设置以下两个字段：

```yaml
python: 'C:/ProgramData/miniconda3/envs/openstory/python.exe'
projectDir: 'C:/path/to/OpenStory'
```

完整配置示例：

```yaml
- insert:
    - id: openstory
      name: 'dsh-openstory'
      config:
        python: 'C:/ProgramData/miniconda3/envs/openstory/python.exe'
        projectDir: 'C:/path/to/OpenStory'
        story: 'story_of_the_stone'
        host: '127.0.0.1'
        port: 8000
        autoStart: true
        startTimeoutMs: 120000
        tickTimeoutMs: 120000
        requestTimeoutMs: 15000
```

Windows YAML 路径建议使用 `/`。保存后重启 DSH，使 Cordis 重新加载配置。配置文件只能从运行 DSH 的本机浏览器打开；插件升级或重新安装可能替换包内配置，升级后请重新检查。

| 字段 | 默认值 | 说明 |
|---|---|---|
| `python` | `python` | 启动 OpenStory 的 Python 解释器，建议使用环境中的绝对路径。 |
| `projectDir` | `''` | OpenStory 仓库根目录；为空时依次使用 `OPENSTORY_HOME` 和 DSH 工作目录。 |
| `story` | `story_of_the_stone` | 要运行的示例。 |
| `host` / `port` | `127.0.0.1` / `8000` | OpenStory FastAPI 和 WebSocket 地址。 |
| `autoStart` | `true` | 服务不可达时自动启动 OpenStory。 |
| `startTimeoutMs` | `120000` | 等待 OpenStory 启动的最长时间。 |
| `tickTimeoutMs` | `120000` | 等待一个完整 tick 的最长时间。 |
| `requestTimeoutMs` | `15000` | 单次 HTTP 请求超时。 |

## 5. 使用插件

确保 Redis 正在运行，然后只需启动 DSH，不需要另外手工启动 OpenStory：

```powershell
dsh web
```

安装插件并重启后，DSH 左侧栏底部会出现 **OpenStory** 按钮。点击后插件会检查服务、按需启动后端，并打开 `http://127.0.0.1:8000/frontend/index.html`。

也可以直接在 DSH 对话中输入：

```text
启动 OpenStory，并检查当前状态。
```

```text
列出当前所有角色。
```

```text
让林黛玉去找贾宝玉交谈，然后推进一个回合。
```

每次 `openstory_tick` 都会触发一轮多智能体推理，可能产生多次模型请求及相应费用。

## 6. 可用工具

| 工具 | 作用 |
|---|---|
| `openstory_status` | 检查后端、受管进程及剧情模式服务状态。 |
| `openstory_start` | 启动 OpenStory 并等待 API Server 就绪。 |
| `openstory_stop` | 停止由插件启动的 OpenStory 进程。 |
| `openstory_tick` | 推进一个 tick，并返回最新记忆摘要。 |
| `openstory_list_agents` | 列出全部角色 id。 |
| `openstory_get_agent` | 获取一个角色的档案。 |
| `openstory_get_state` | 获取角色状态或世界快照。 |
| `openstory_send_directive` | 指定角色下一回合的动作、地点和目标。 |
| `openstory_reset` | 清空 Redis 状态并重启后端；此操作具有破坏性。 |

`openstory_stop` 只停止插件自己启动的进程，不会停止手工启动的 OpenStory 服务。

## 7. 常见问题

### `ERR_PNPM_MINIMUM_RELEASE_AGE_VIOLATION`

包的发布时间未达到 DSH 的供应链安全等待期。等待后重新执行安装命令。

### `No matching distribution found for ray`

检查插件配置的 Python 版本。若为 Python 3.14，请使用 Python 3.12 重新创建环境。

### 插件已安装，但设置项或工具没有出现

确认安装的是 `dsh-openstory@0.2.0` 或更高版本，然后重启 DSH。

### `cannot resolve profile bundle "dsh-openstory"`

profile 已声明插件但依赖未完整安装。重新执行安装命令；若仍被 minimum-release-age 策略拦截，应等待安全窗口结束。

### Redis 报错 `unknown command HELLO 3`

升级到 Redis 6/7；必须使用 Redis 5 时，在 OpenStory 的数据库连接和 API Server Redis 配置中设置 `protocol: 2`。

### 端口 8000 已被占用

停止旧的 OpenStory 进程，或者同时修改 OpenStory API Server 与插件的 `port`。

### 启动超时

首次初始化 Ray 可能较慢。确认 Redis、模型配置、Python 路径和 `projectDir` 后，适当提高 `startTimeoutMs`。

## 8. 卸载

```powershell
dsh plugin --profile web remove dsh-openstory
```

