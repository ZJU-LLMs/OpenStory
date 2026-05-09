# CLAUDE.md — WorldKernel

This file provides guidance to Claude Code when working in `examples/WorldKernel`.

---

## Project Purpose

WorldKernel is a **text-to-interactive-world generation system** built on top of Agent-Kernel.

A player types one natural-language sentence such as:

> 创建最后一部中的霍格沃茨魔法学院

The system parses that sentence, constructs a structured `WorldSpec`, generates all world content (characters, locations, relations, rules…), adapts it to Agent-Kernel configs, and launches a tick-based multi-agent simulation that the player can influence in real time.

WorldKernel lives inside the larger OpenStory mono-repo (`examples/WorldKernel/`). It **only uses** the packages in `packages/` as dependencies — it never modifies them.

---

## Scope Constraint (read carefully)

**Only modify files under `examples/WorldKernel/`.** Files in sibling examples, in `packages/`, or at the repo root are dependencies / reference material only — do not touch them.

Start with the **standalone** package (`agentkernel_standalone`). The distributed variant is a later migration.

---

## Full Pipeline (for context — not all stages are implemented yet)

```
User NL input
    │
    ▼
Stage 1  — Understanding & Constraint Preparation    ← CURRENT FOCUS
    │       Intent Parser → World Type Classifier
    │       → Generation Planner → Template Retriever
    │       → Ontology & Schema Selector
    │       Output: world_spec.json
    ▼
Stage 2  — World Generation Core
    │       World Architect Agent orchestrates:
    │         Environment Generator, Agent Generator,
    │         Relation Generator, Action & Rule Generator,
    │         Event Generator (optional), Asset Prompt Generator (optional)
    │       Memory: Recent Tick Memory + Long-term World Memory
    ▼
Stage 3  — Patch Validation, Repair & Adaptation
    │       Patch Composer → Validator & Repair Loop
    │       → World Version Store → AK Adapter → Patch Committer
    ▼
Stage 4  — Agent-Kernel Simulation Runtime
            System Module (Timer + Messager + Recorder)
            Controller Module
            Agent / Environment / Action Modules
            Tick results → UI / Events
```

---

## Current Development Focus: Stage 1

**Goal:** receive a single natural-language string from the frontend, call LLM APIs through a pipeline of five modules, and return a validated `WorldSpec` JSON.

Stage 1 does **not** generate actual characters, locations, or simulation configs. It only produces a structured specification used by Stage 2.

### Stage 1 Modules

#### 1. Intent Parser

Understands the raw player input and extracts structured intent fields.

```json
{
  "raw_text": "创建最后一部中的霍格沃茨魔法学院",
  "world_name_hint": "霍格沃茨魔法学院",
  "source_hint": "最后一部（哈利·波特系列）",
  "user_goal": "创建一个可交互的魔法学院世界",
  "style": "fantasy_school",
  "constraints": [],
  "uncertain_slots": [
    "最后一部具体指电影还是小说",
    "是否允许使用原作角色"
  ]
}
```

#### 2. World Type Classifier

Classifies the world into one or more of the registered types:

| Type ID | Description |
|---|---|
| `fictional_institution_world` | 虚构机构（学校、医院、组织）|
| `school_simulation` | 学校/校园模拟 |
| `fantasy_world` | 幻想/魔法世界 |
| `campus_life_world` | 现代校园生活 |
| `city_world` | 城市社会模拟 |
| `hospital_world` | 医疗机构模拟 |
| `survival_world` | 生存/末日模拟 |
| `historical_society_world` | 历史社会模拟 |

Each world gets a primary type and optionally a secondary type with confidence scores.

#### 3. Generation Planner

Produces an ordered list of generation steps for Stage 2 to execute. Does **not** generate content — only decides what to generate and in what order.

```json
{
  "steps": [
    { "name": "generate_world_background", "target": "世界背景与宏观规则" },
    { "name": "generate_locations",        "target": "大厅、教室、宿舍、图书馆等" },
    { "name": "generate_characters",       "target": "学生、教师、管理者" },
    { "name": "generate_relations",        "target": "师生、同学、学院归属关系" },
    { "name": "generate_rules",            "target": "魔法规则、纪律规则" },
    { "name": "generate_actions",          "target": "可用行动类型" }
  ]
}
```

#### 4. Template Retriever / Grounding

Looks up matching templates from `configs/world_types/` based on world type tags. Uses tag-based matching in v1 — no RAG or vector DB required initially.

Template types: World, Character, Location, Relation, Institution, Rule, Event.

#### 5. Ontology & Schema Selector

Selects the entity types and field schemas for this world.

```json
{
  "entity_types": ["World", "Character", "Location", "Group", "Relation", "Institution", "Rule", "Event", "Action"],
  "schemas": {
    "Character": {
      "id": "string",
      "name": "string",
      "role": "student | teacher | administrator",
      "personality": ["string"],
      "goals": ["string"],
      "location_id": "string",
      "group_id": "string",
      "permissions": ["string"],
      "constraints": ["string"]
    }
  }
}
```

### WorldSpec Output Format

The Stage 1 pipeline writes a single file: `worlds/generated/<session_id>/world_spec.json`.

Top-level fields:

```json
{
  "meta": { "session_id": "", "created_at": "", "source_input": "" },
  "intent": { ... },
  "world_type": { "primary": "", "secondary": "", "confidence": 0.0 },
  "generation_plan": { "steps": [] },
  "templates": { "matched": [], "fallback": false },
  "ontology": { "entity_types": [], "schemas": {} },
  "constraints": [],
  "uncertain_slots": [],
  "confidence": 0.0
}
```

---

## Directory Structure

```
examples/WorldKernel/
├── CLAUDE.md                    ← this file
├── pyproject.toml               ← package definition, depends on agentkernel_standalone
├── .env.example                 ← LLM API key template
│
├── src/worldkernel/
│   ├── __init__.py
│   ├── server.py                ← FastAPI entry point (Stage 1 API)
│   │
│   ├── stage1/                  ← Stage 1 pipeline modules
│   │   ├── __init__.py
│   │   ├── pipeline.py          ← orchestrates the 5 modules, returns WorldSpec
│   │   ├── intent_parser.py
│   │   ├── world_type_classifier.py
│   │   ├── generation_planner.py
│   │   ├── template_retriever.py
│   │   └── ontology_selector.py
│   │
│   ├── models/
│   │   ├── __init__.py
│   │   ├── world_spec.py        ← Pydantic models for WorldSpec
│   │   └── llm_client.py        ← thin wrapper for OpenAI-compatible API calls
│   │
│   └── architect/               ← Stage 2+ (future)
│       └── prompts/             ← prompt templates (.md files)
│
├── configs/
│   ├── models.yaml              ← LLM endpoint config (OpenAI-compatible)
│   ├── architect.yaml           ← Stage 2+ architect config
│   ├── simulation.yaml          ← Stage 4 simulation defaults
│   ├── storage.yaml             ← storage backend config
│   └── world_types/             ← world-type template library
│       ├── campus.yaml
│       ├── closed_space.yaml
│       ├── hospital.yaml
│       ├── market.yaml
│       └── town.yaml
│
├── templates/
│   └── agent_kernel_project/    ← scaffold for generated AK projects (Stage 3+)
│       └── configs/
│
├── frontend/                    ← Stage 1 UI: text input + WorldSpec viewer
│   ├── index.html
│   ├── style.css
│   └── app.js
│
└── worlds/
    └── generated/               ← output dir for world_spec.json and future worlds
        └── .gitkeep
```

> Note: `frontend/` uses Vite for development but the final serve is static HTML/CSS/JS, same as the reference example. Do not add a build step to the runtime server.

---

## Setup and Running

Python >= 3.11 required.

```bash
# From repo root — install standalone package + WorldKernel
pip install -e "packages/agentkernel-standalone[all]"
pip install -e "examples/WorldKernel"

# Copy env file and fill in LLM API key
cp examples/WorldKernel/.env.example examples/WorldKernel/.env

# Run Stage 1 server
python -m worldkernel.server
# API: http://localhost:8100
# Frontend: http://localhost:8100/frontend/index.html
```

---

## LLM API Integration

LLM endpoints are configured in `configs/models.yaml` using the same OpenAI-compatible format as the reference example:

```yaml
- name: OpenAIProvider
  model: qwen-plus
  api_key:            # filled from .env: WORLDKERNEL_API_KEY
  base_url: https://dashscope.aliyuncs.com/compatible-mode/v1
  capabilities: [chat]
```

The `llm_client.py` wrapper:
- Reads `configs/models.yaml` at startup
- Exposes a single async function: `async def chat(prompt: str, system: str = "") -> str`
- Returns plain text or raises a typed error — no streaming in Stage 1
- All five Stage 1 modules call through this wrapper; never instantiate the SDK directly in pipeline code

Use the LLM for: NL understanding, type classification, plan generation, schema selection, uncertainty extraction.
Use rule/tag matching for: template retrieval (v1).

---

## Frontend–Backend Interaction (Stage 1)

Follow the same pattern as `story_of_the_stone`:
- FastAPI serves both the API and static frontend files
- POST `/api/stage1/parse` — accepts `{ "input": "..." }`, returns `WorldSpec` JSON
- GET `/api/stage1/spec/{session_id}` — retrieves a previously generated spec
- Frontend is plain HTML/CSS/JS; no React or build step required for runtime

---

## Conventions

- Pydantic models for all data structures in `models/world_spec.py`
- All Stage 1 modules are pure async functions with typed signatures
- Prompt templates live in `architect/prompts/*.md`, loaded at runtime by path
- World type configs in `configs/world_types/` are plain YAML, loaded by `template_retriever.py`
- `worlds/generated/` is gitignored except for `.gitkeep`
- Do not import from `agentkernel_distributed` — standalone only for now
- No test suite configured; verify manually through the frontend

---

## Reference Files (read-only)

| Path | What to look at |
|---|---|
| `examples/story_of_the_stone/run_simulation.py` | Server setup, API mount, tick loop pattern |
| `examples/story_of_the_stone/registry.py` | Plugin/component registration pattern |
| `examples/story_of_the_stone/configs/` | Config YAML structure |
| `packages/agentkernel-standalone/` | Builder API, available components |
