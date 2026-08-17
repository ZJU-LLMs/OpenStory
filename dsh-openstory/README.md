# dsh-openstory: installation, configuration, and usage

English | [简体中文](README.zh.md)

`dsh-openstory` is the DeepSeek Harness (DSH) plugin for OpenStory. It is published on npm: <https://www.npmjs.com/package/dsh-openstory>.

The plugin exposes OpenStory as native DSH tools and adds an OpenStory entry to the DSH settings panel. With `autoStart` enabled, only DSH needs to be started; opening the OpenStory frontend or invoking a tool starts the backend when needed.

## 1. Prerequisites

- Node.js 22 or newer
- DeepSeek Harness with an initialized `web` profile
- An OpenStory source checkout
- Python 3.11 through 3.13; Python 3.12 is recommended on Windows
- Redis listening on `localhost:6379`; Redis 7 is recommended
- A working OpenAI-compatible model API

Python 3.14 is not recommended because OpenStory's pinned Ray release has no matching Windows wheel.

## 2. Prepare OpenStory

Run these commands from the OpenStory repository root.

### Windows with Conda

```powershell
conda create -n openstory python=3.12 -y
conda activate openstory
python -m pip install --upgrade pip
python -m pip install -e "packages/agentkernel-distributed[all]"
```

Find the interpreter path after activating the environment:

```powershell
python -c "import sys; print(sys.executable)"
```

### Linux/macOS with venv

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e "packages/agentkernel-distributed[all]"
```

Configure `examples/story_of_the_stone/configs/models_config.yaml`:

```yaml
- name: OpenAIProvider
  model: deepseek-chat
  api_key: YOUR_API_KEY
  base_url: https://api.deepseek.com/v1
  capabilities:
    - chat
```

Do not commit a real API key to Git.

## 3. Install from npm

When `dsh` is available on `PATH`:

```powershell
dsh plugin --profile web add dsh-openstory@0.2.0
```

Without a global `dsh` command:

```powershell
npx @deepseek-ai/dsh plugin --profile web add dsh-openstory@0.2.0
```

The command adds the dependency and bundle entry to the profile automatically. Do not edit the profile's `package.json` manually.

A newly published package can trigger `ERR_PNPM_MINIMUM_RELEASE_AGE_VIOLATION`. This is DSH's supply-chain protection, not a damaged plugin package. Wait for the configured safety window and retry instead of disabling the policy.

## 4. Configure in DSH

Start DSH:

```powershell
dsh web
```

Without a global command:

```powershell
npx @deepseek-ai/dsh web
```

In the DSH Web interface, open:

```text
Settings → OpenStory → Open configuration file
```

The system editor opens the `cordis.patch.yml` loaded by the installed package. At minimum, set:

```yaml
python: 'C:/ProgramData/miniconda3/envs/openstory/python.exe'
projectDir: 'C:/path/to/OpenStory'
```

Complete example:

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

Use `/` in Windows YAML paths. Restart DSH after saving so Cordis reloads the configuration. The file can only be opened from a browser on the DSH host. An upgrade or reinstall may replace package files, so check the configuration after upgrading.

| Field | Default | Meaning |
|---|---|---|
| `python` | `python` | Python interpreter used to start OpenStory; use an absolute environment path. |
| `projectDir` | `''` | OpenStory repository root; falls back to `OPENSTORY_HOME`, then the DSH working directory. |
| `story` | `story_of_the_stone` | Example to run. |
| `host` / `port` | `127.0.0.1` / `8000` | OpenStory FastAPI and WebSocket address. |
| `autoStart` | `true` | Start OpenStory when the service is unreachable. |
| `startTimeoutMs` | `120000` | Maximum startup wait. |
| `tickTimeoutMs` | `120000` | Maximum wait for one complete tick. |
| `requestTimeoutMs` | `15000` | Per-request HTTP timeout. |

## 5. Use the plugin

Ensure Redis is running, then start only DSH. OpenStory does not need to be started separately:

```powershell
dsh web
```

After installation and restart, an **OpenStory** button appears at the bottom of the DSH sidebar. It checks the service, starts the backend when `autoStart` is enabled, and opens `http://127.0.0.1:8000/frontend/index.html`.

You can also ask DSH directly:

```text
Start OpenStory and check its status.
```

```text
List every character in the simulation.
```

```text
Tell Lin Daiyu to visit Jia Baoyu, then advance one tick.
```

Every `openstory_tick` runs a multi-agent reasoning round and may generate multiple billable model requests.

## 6. Tools

| Tool | Action |
|---|---|
| `openstory_status` | Check the backend, managed process, and story-mode service. |
| `openstory_start` | Start OpenStory and wait for the API Server. |
| `openstory_stop` | Stop the OpenStory process started by the plugin. |
| `openstory_tick` | Advance one tick and return recent memory summaries. |
| `openstory_list_agents` | List all character ids. |
| `openstory_get_agent` | Fetch one character profile. |
| `openstory_get_state` | Fetch a character state or world snapshot. |
| `openstory_send_directive` | Set a character's next action, location, and target. |
| `openstory_reset` | Flush Redis state and restart the backend; this is destructive. |

`openstory_stop` only stops a process started by the plugin. It does not stop a manually started OpenStory service.

## 7. Troubleshooting

### `ERR_PNPM_MINIMUM_RELEASE_AGE_VIOLATION`

The package is newer than DSH's supply-chain safety window. Wait and retry the installation.

### `No matching distribution found for ray`

Check the configured Python version. Recreate the environment with Python 3.12 if it uses Python 3.14.

### The settings entry or tools are missing

Install `dsh-openstory@0.2.0` or newer and restart DSH.

### `cannot resolve profile bundle "dsh-openstory"`

The profile declares the plugin but its dependency was not installed completely. Run the installation again. If the minimum-release-age policy still blocks it, wait for the safety window.

### Redis reports `unknown command HELLO 3`

Upgrade to Redis 6/7. If Redis 5 is required, set `protocol: 2` in both the OpenStory database connection and API Server Redis configuration.

### Port 8000 is already in use

Stop the old OpenStory process, or change the port in both OpenStory and the plugin configuration.

### Startup times out

The first Ray initialization can be slow. Verify Redis, model configuration, the Python path, and `projectDir`, then increase `startTimeoutMs` if necessary.

## 8. Uninstall

```powershell
dsh plugin --profile web remove dsh-openstory
```

