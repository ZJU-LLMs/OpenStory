# CLAUDE.md — WorldKernel

This file provides guidance to Claude Code when working in `examples/WorldKernel`.

---

## Project Purpose

WorldKernel is a **text-to-interactive-world generation system** built on top of Agent-Kernel.

用户输入一句自然语言（如"创建最后一部中的霍格沃茨魔法学院"），系统经过多阶段 pipeline 生成完整的世界内容，最终适配 Agent-Kernel 启动可交互的多智能体仿真。

---

## Scope Constraint

**Only modify files under `examples/WorldKernel/`.** Sibling examples、`packages/`、repo root 均为只读依赖。

Runtime target: **`agentkernel_distributed`**.

---

## Pipeline Overview

```
User NL input
    │
    ▼
Stage 1  — 理解与模版准备        ← IMPLEMENTED
    │       意图解析 → 世界模版构建 → 生成计划 → 六类实体通用模版
    │       Output: worlds/generated/<session_id>/ (8 JSON files)
    ▼
Stage 2  — 世界内容生成          ← NOT YET
    │       World Architect Agent orchestrates generators
    ▼
Stage 3  — 校验、修复与适配      ← NOT YET
    │       Patch Validation → AK Adapter
    ▼
Stage 4  — Agent-Kernel 仿真    ← NOT YET
            Tick-based multi-agent simulation
```

---

## Directory Structure

```
examples/WorldKernel/
├── CLAUDE.md
├── pyproject.toml
├── .env.example              ← WORLDKERNEL_API_KEY
│
├── src/worldkernel/
│   ├── server.py             ← FastAPI: API routes + static frontend (mount at /)
│   ├── stage1/               ← Stage 1 pipeline modules
│   │   ├── pipeline.py       ← run_stage1(): orchestrates modules, saves files
│   │   ├── intent_parser.py
│   │   ├── world_type_classifier.py
│   │   ├── generation_planner.py
│   │   └── ontology_selector.py  ← 6 entity template generator (parallel LLM)
│   ├── prompts/              ← Prompt templates (.md), loaded at runtime
│   ├── models/               ← Pydantic data models
│   │   ├── world_spec.py     ← SessionInfo
│   │   └── stage1_types.py   ← IntentResult, WorldTemplate, GenerationPlan, EntityTemplate...
│   ├── llm/                  ← LLM call layer (all stages share)
│   │   ├── client.py         ← init(), chat(), chat_json()
│   │   └── config_loader.py
│   └── architect/            ← Stage 2+ placeholder
│
├── configs/
│   └── models.yaml           ← LLM config (OpenAI-compatible)
│
├── tests/
│   └── test_stage1.py        ← E2E: starts uvicorn + browser + auto-validates
│
├── frontend/                 ← Static HTML/CSS/JS, served by FastAPI at /
│
└── worlds/generated/         ← Output: <session_id>/*.json (gitignored)
```

---

## Setup and Running

```bash
pip install -e "examples/WorldKernel"
cp examples/WorldKernel/.env.example examples/WorldKernel/.env  # fill API key

python -m worldkernel.server          # http://localhost:8100/

cd examples/WorldKernel
python tests/test_stage1.py           # starts server + browser + auto-validates
```

---

## LLM Integration

- Config: `configs/models.yaml` (OpenAI-compatible format, key from `WORLDKERNEL_API_KEY` env var)
- Single entry point: `llm/client.py` — `chat()` and `chat_json()` (auto-strips markdown fences + extracts JSON)
- All modules import `from worldkernel.llm.client import chat_json`, never instantiate SDK directly
- Server lifespan calls `llm_client.init()` at startup

---

## API Endpoints

| Method | Path | Description |
|---|---|---|
| POST | `/api/stage1/parse` | `{"input": "..."}` → runs pipeline → returns SessionInfo |
| GET | `/api/stage1/session/{session_id}` | Returns file list |
| GET | `/api/stage1/session/{session_id}/{filename}` | Returns file content |

---

## Conventions

- Pydantic v2 models for all data structures
- All pipeline modules are pure async functions with typed signatures
- Prompt templates: `src/worldkernel/prompts/*.md`, loaded by path
- `worlds/generated/` is gitignored except `.gitkeep`
- Frontend: static HTML/JS/CSS, no build step, served at `/`

---

## Reference (read-only)

| Path | What to look at |
|---|---|
| `examples/story_of_the_stone/` | Server setup, registry, config structure |
| `packages/agentkernel-distributed/` | Builder API, available components |
