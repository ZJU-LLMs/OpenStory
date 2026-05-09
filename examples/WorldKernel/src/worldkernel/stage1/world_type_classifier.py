from __future__ import annotations

import json
from pathlib import Path

from worldkernel.llm.client import chat
from worldkernel.models.stage1_types import IntentResult, WorldTypeResult

_PROMPT_PATH = Path(__file__).parent.parent / "prompts" / "stage1_classify_world.md"


async def classify_world_type(intent: IntentResult) -> WorldTypeResult:
    template = _PROMPT_PATH.read_text(encoding="utf-8")
    prompt = template.replace("{{intent}}", intent.model_dump_json())
    raw = await chat(prompt)
    data = json.loads(raw)
    return WorldTypeResult(**data)
