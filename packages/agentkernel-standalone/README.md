<p align="center">
  <img
    src="https://raw.githubusercontent.com/ZJU-LLMs/Agent-Kernel/main/assets/agentkernel_logo.png"
    width="400"
  />
</p>

# Agent-Kernel Standalone

**Agent-Kernel Standalone** is a lightweight, self-contained Multi-Agent System (MAS) development framework for local environments. It provides the same modular microkernel architecture as the distributed version but runs entirely on a single machine — no Ray or external services required.

---

## 🚀 Installation

### 1. Requirements

- Python ≥ 3.11

### 2. Install from PyPI

You can install Agent-Kernel Standalone directly from PyPI using `pip`.

```bash
pip install agentkernel-standalone
```

**Installing with Optional Features**

Agent-Kernel Standalone comes with optional dependencies for web services and storage solutions. You can install them as needed.

- `web` → Installs `aiohttp`, `fastapi`, `uvicorn`
- `storages` → Installs `asyncpg`, `pymilvus`, `redis`
- `all` → Installs both `web` and `storages`

To install the package with these extras, use the following format:

```bash
# Install with web features
pip install "agentkernel-standalone[web]"

# Install with storage features
pip install "agentkernel-standalone[storages]"

# Install all optional features
pip install "agentkernel-standalone[all]"
```
