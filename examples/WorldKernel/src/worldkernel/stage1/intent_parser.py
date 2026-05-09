from __future__ import annotations

import json
from pathlib import Path

from worldkernel.llm.client import chat
from worldkernel.models.stage1_types import IntentResult

_PROMPT_PATH = Path(__file__).parent.parent / "prompts" / "stage1_parse_intent.md"


async def parse_intent(raw_text: str) -> IntentResult:
    template = _PROMPT_PATH.read_text(encoding="utf-8")
    prompt = template.replace("{{input}}", raw_text)
    raw = await chat(prompt)
    data = json.loads(raw)
    return IntentResult(**data)
