from __future__ import annotations

import json
from pathlib import Path

from worldkernel.llm.client import chat
from worldkernel.models.stage1_types import GenerationPlan, IntentResult, WorldTypeResult

_PROMPT_PATH = Path(__file__).parent.parent / "prompts" / "stage1_plan_generation.md"


async def plan_generation(intent: IntentResult, world_type: WorldTypeResult) -> GenerationPlan:
    template = _PROMPT_PATH.read_text(encoding="utf-8")
    prompt = (
        template
        .replace("{{intent}}", intent.model_dump_json())
        .replace("{{world_type}}", world_type.model_dump_json())
    )
    raw = await chat(prompt)
    data = json.loads(raw)
    return GenerationPlan(**data)
