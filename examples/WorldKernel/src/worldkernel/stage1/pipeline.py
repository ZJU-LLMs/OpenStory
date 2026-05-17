from __future__ import annotations

import json
from pathlib import Path

import yaml

from worldkernel.stage1.types import (
    EntityTemplate,
    GenerationPlan,
    IntentResult,
    WorldTemplate,
)
from worldkernel.stage1.world_spec import SessionInfo
from worldkernel.stage1.generation_planner import plan_generation
from worldkernel.stage1.intent_parser import parse_intent
from worldkernel.stage1.ontology_selector import generate_templates
from worldkernel.stage1.world_type_classifier import build_world_template

_TEMPLATES_DIR = Path(__file__).parent.parent.parent.parent / "templates"


class Stage1Error(Exception):
    def __init__(self, step: str, cause: Exception) -> None:
        self.step = step
        self.cause = cause
        super().__init__(f"Stage 1 failed at [{step}]: {cause}")


async def run_stage1(raw_input: str) -> SessionInfo:
    session = SessionInfo(source_input=raw_input)
    out_dir = _TEMPLATES_DIR / session.session_id
    out_dir.mkdir(parents=True, exist_ok=True)

    try:
        intent: IntentResult = await parse_intent(raw_input)
    except Exception as e:
        raise Stage1Error("intent_parser", e) from e

    try:
        world_type: WorldTemplate = await build_world_template(intent)
    except Exception as e:
        raise Stage1Error("world_type_classifier", e) from e

    try:
        plan: GenerationPlan = await plan_generation(intent, world_type)
    except Exception as e:
        raise Stage1Error("generation_planner", e) from e

    try:
        templates: dict[str, EntityTemplate] = await generate_templates(intent, world_type, plan)
    except Exception as e:
        raise Stage1Error("ontology_selector", e) from e

    _save_json(out_dir / "generated" / "world_template.json", world_type.model_dump())
    _save_plan(out_dir / "generated" / "plan", plan)
    _save_templates(out_dir / "generated" / "templates", templates)
    _save_agent_config(out_dir / "configs" / "agent", templates)

    return session


def _save_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _save_yaml(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        yaml.dump(data, allow_unicode=True, default_flow_style=False, sort_keys=False),
        encoding="utf-8",
    )


def _save_plan(plan_dir: Path, plan: GenerationPlan) -> None:
    _save_json(plan_dir / "steps.json", [s.model_dump() for s in plan.steps])
    _save_json(plan_dir / "ontology_hints.json", plan.ontology_hints.model_dump())

    for category, archetype_dict in [
        ("locations", plan.entity_plan.locations),
        ("characters", plan.entity_plan.characters),
        ("institutions", plan.entity_plan.institutions),
        ("rules", plan.entity_plan.rules),
    ]:
        for archetype_id, seeds in archetype_dict.items():
            _save_json(
                plan_dir / "entity_plan" / category / f"{archetype_id}.json",
                [s.model_dump() for s in seeds],
            )


def _save_templates(templates_dir: Path, templates: dict[str, EntityTemplate]) -> None:
    for entity_key, entity_template in templates.items():
        ent_dir = templates_dir / entity_key
        dim_names = list(entity_template.dimensions.keys())
        _save_json(ent_dir / "index.json", {"dimensions": dim_names})
        for dim_name, dim_data in entity_template.dimensions.items():
            _save_json(ent_dir / f"{dim_name}.json", dim_data.model_dump())


def _save_agent_config(configs_dir: Path, templates: dict[str, EntityTemplate]) -> None:
    """从生成的 character 模版自动导出 Agent config（分层结构）。"""
    char_template = templates.get("character")
    if not char_template:
        return

    dim_names = list(char_template.dimensions.keys())
    config = {
        "name": "Agent",
        "entity_type": "character",
        "dimensions": {
            name: {"type": f"{name.title().replace('_', '')}Dim", "required": True}
            for name in dim_names
        },
    }

    configs_dir.mkdir(parents=True, exist_ok=True)
    _save_yaml(configs_dir / "agent.yaml", config)

    dims_dir = configs_dir / "dims"
    dims_dir.mkdir(parents=True, exist_ok=True)
    for dim_name, dim_data in char_template.dimensions.items():
        dim_fields = []
        for f in dim_data.fields:
            field_entry: dict = {"name": f.name, "type": f.type, "required": f.required}
            if f.ref:
                field_entry["ref"] = f.ref
            dim_fields.append(field_entry)
        _save_yaml(dims_dir / f"{dim_name}.yaml", {"fields": dim_fields})
