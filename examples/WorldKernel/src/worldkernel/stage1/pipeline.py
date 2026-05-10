from __future__ import annotations

import json
from pathlib import Path

from worldkernel.models.stage1_types import (
    GenerationPlan,
    IntentResult,
    OntologySchema,
    TemplateMatch,
    WorldTypeResult,
)
from worldkernel.models.world_spec import WorldSpec, WorldSpecMeta
from worldkernel.stage1.generation_planner import plan_generation
from worldkernel.stage1.intent_parser import parse_intent
from worldkernel.stage1.ontology_selector import select_ontology
from worldkernel.stage1.template_retriever import retrieve_templates
from worldkernel.stage1.world_type_classifier import classify_world_type

_WORLDS_DIR = Path(__file__).parent.parent.parent.parent / "worlds" / "generated"


async def run_stage1(raw_input: str) -> WorldSpec:
    intent: IntentResult = await parse_intent(raw_input)
    world_type: WorldTypeResult = await classify_world_type(intent)
    plan: GenerationPlan = await plan_generation(intent, world_type)
    templates: list[TemplateMatch] = retrieve_templates(world_type)
    ontology: OntologySchema = await select_ontology(intent, world_type)

    spec = WorldSpec(
        meta=WorldSpecMeta(source_input=raw_input),
        intent=intent.model_dump(),
        world_type=world_type.model_dump(),
        generation_plan=plan.model_dump(),
        templates={
            "matched": [t.model_dump() for t in templates],
            "fallback": len(templates) == 0,
        },
        ontology=ontology.model_dump(),
        constraints=intent.constraints,
        uncertain_slots=intent.uncertain_slots,
        confidence=world_type.confidence,
    )

    _persist(spec)
    return spec


def _persist(spec: WorldSpec) -> None:
    out_dir = _WORLDS_DIR / spec.meta.session_id
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "world_spec.json").write_text(
        json.dumps(spec.model_dump(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
