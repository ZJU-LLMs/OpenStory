# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

OpenStory is a multi-agent deduction and simulation framework built on LLMs. The core engine is **Agent-Kernel**, which orchestrates LLM-powered agents through a tick-based simulation loop. The primary showcase simulates *Dream of the Red Chamber* with autonomous character agents interacting in a pixel-art "Grand View Garden" map.

## Setup and Running

Python >= 3.11 required. Redis must be running on localhost:6379.

```bash
# Install (pick one):
pip install -e "packages/agentkernel-distributed[all]"   # distributed (Ray)
pip install -e "packages/agentkernel-standalone[all]"     # standalone (no Ray)

# Run main simulation:
python -m examples.story_of_the_stone.run_simulation
# Frontend at http://localhost:8000/frontend/index.html
```

No test suite or linter is configured in this repo.

## Architecture

### Two package variants in `packages/`

- **agentkernel-distributed** — Uses Ray actors for pod execution across processes/nodes.
- **agentkernel-standalone** — Same architecture, no Ray dependency, runs entirely in-process.

Both share identical internal structure under `agentkernel_{distributed,standalone}/`:

| Subpackage | Role |
|---|---|
| `mas/builder.py` | Loads YAML configs + registry, wires up the full system |
| `mas/pod/` | PodManager + MasPod — agent lifecycle as Ray actors (distributed) or local wrappers (standalone) |
| `mas/agent/` | Agent perceive→plan→invoke→state→reflect lifecycle with plugin/component slots |
| `mas/action/` | Action plugins (communication, movement, etc.) |
| `mas/environment/` | Environment simulation (relations, space) |
| `mas/controller/` | Simulation flow control (tick loop) |
| `mas/system/` | Shared services: Messager (message bus), Timer (clock), Recorder |
| `mas/interface/` | FastAPI server, WebSocket broadcasting |
| `toolkit/models/` | LLM routing via OpenAI-compatible API |
| `toolkit/storages/` | Pluggable adapters: Redis KV, Redis graph, PostgreSQL, Milvus |
| `toolkit/generation/` | PCG for agents, relationships, spaces |
| `types/` | Pydantic config models and data schemas |

### Example implementations in `examples/`

Each example provides its own registry, plugins, configs, and frontend:

- **`story_of_the_stone/`** — Main Dream of the Red Chamber example (Chinese)
- **`story_of_the_stone_en/`** — English translation of the same
- **`WorldKernel/`** — Placeholder/stub (empty files)

Key files in an example:
- `run_simulation.py` — Entry point
- `registry.py` — Maps plugin/component class names to implementations (the central wiring table)
- `configs/` — YAML configs: simulation, models, system, agents, actions, environment, database
- `plugins/` — Example-specific plugin implementations
- `frontend/` — Vanilla JS visualization (no build step)
- `data/` — Character profiles (JSONL), relationships

### Simulation loop (tick cycle)

Each tick: agents **perceive** → **plan** → **invoke actions** → **update state** → **reflect**. The Messager dispatches inter-agent messages. The frontend receives WebSocket broadcasts each tick.

### Plugin system

Plugins are Python classes registered in `registry.py`. The `agents_config.yaml` defines which plugin classes back each lifecycle slot (perceive, plan, invoke, state, reflect) for each agent template. To add new behavior, implement a plugin class and register it.

## Configuration

Simulation configs live under `examples/<name>/configs/`. The master config is `simulation_config.yaml`, which references all other config files and defines data paths, pod size, tick limits, and API server settings. LLM endpoints are configured in `models_config.yaml` using OpenAI-compatible API format.

## Conventions

- No monorepo tooling — each package is independently installable via `pip install -e`.
- Config and data schemas are Pydantic models in the `types/` subpackage.
- Storage backends are pluggable via adapter pattern (configured in `db_config.yaml`).
- The frontend is plain HTML/JS/CSS with no build step — edit and refresh.
