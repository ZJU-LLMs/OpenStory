<p align="center">
  <img
    src="https://raw.githubusercontent.com/ZJU-LLMs/Agent-Kernel/main/assets/agentkernel_logo.png"
    width="400"
  />
</p>

# Agent-Kernel Distributed

**Agent-Kernel Distributed** is a distributed Multi-Agent System (MAS) development framework designed to support large-scale environments using **Ray** for distributed execution. It is ideal for coordinating multiple intelligent agents running across different nodes or processes.

---

## 🚀 Quick Start

### 1. Requirements

- `Python ≥ 3.11`

### 2. Install from PyPI

You can install Agent-Kernel Distributed directly from PyPI using `pip`.

```bash
pip install agentkernel-distributed
```

> The distributed package depends on Ray and will install it automatically.

**Installing with Optional Features**

Agent-Kernel Distributed comes with optional dependencies for web services and storage solutions. You can install them as needed.

- `web` → Installs `aiohttp`, `fastapi`, `uvicorn`
- `storages` → Installs `asyncpg`, `pymilvus`, `redis`
- `all` → Installs both `web` and `storages`

To install the package with these extras, use the following format:

```bash
# Install with web features
pip install "agentkernel-distributed[web]"

# Install with storage features
pip install "agentkernel-distributed[storages]"

# Install all optional features
pip install "agentkernel-distributed[all]"
```
