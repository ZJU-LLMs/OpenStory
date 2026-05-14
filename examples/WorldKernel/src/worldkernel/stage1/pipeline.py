from __future__ import annotations

import json
from pathlib import Path

from worldkernel.models.stage1_types import (
    EntityTemplate,
    GenerationPlan,
    IntentResult,
    WorldTemplate,
)
from worldkernel.models.world_spec import SessionInfo
from worldkernel.stage1.generation_planner import plan_generation
from worldkernel.stage1.intent_parser import parse_intent
from worldkernel.stage1.ontology_selector import generate_templates
from worldkernel.stage1.world_type_classifier import build_world_template

_WORLDS_DIR = Path(__file__).parent.parent.parent.parent / "worlds" / "generated"


class Stage1Error(Exception):
    def __init__(self, step: str, cause: Exception) -> None:
        self.step = step
        self.cause = cause
        super().__init__(f"Stage 1 failed at [{step}]: {cause}")


async def run_stage1(raw_input: str) -> SessionInfo:
    session = SessionInfo(source_input=raw_input)
    out_dir = _WORLDS_DIR / session.session_id
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
        templates: dict[str, EntityTemplate] = await generate_templates(intent, world_type)
    except Exception as e:
        raise Stage1Error("ontology_selector", e) from e

    _save(out_dir, "world_template.json", world_type.model_dump())
    _save(out_dir, "generation_plan.json", plan.model_dump())
    for entity_key, entity_template in templates.items():
        _save(out_dir, f"{entity_key}_template.json", entity_template.model_dump())

    return session


def _save(out_dir: Path, filename: str, data: dict) -> None:
    (out_dir / filename).write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
