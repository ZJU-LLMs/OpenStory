from __future__ import annotations

import json
from pathlib import Path

import yaml

from worldkernel.llm.client import chat
from worldkernel.models.stage1_types import IntentResult, OntologySchema, WorldTypeResult

_PROMPT_PATH = Path(__file__).parent.parent / "prompts" / "stage1_select_schema.md"
_SCHEMAS_PATH = Path(__file__).parent.parent.parent.parent / "configs" / "stage1_schemas.yaml"


async def select_ontology(intent: IntentResult, world_type: WorldTypeResult) -> OntologySchema:
    base_schemas = yaml.safe_load(_SCHEMAS_PATH.read_text(encoding="utf-8")) or {}
    template = _PROMPT_PATH.read_text(encoding="utf-8")
    prompt = (
        template
        .replace("{{intent}}", intent.model_dump_json())
        .replace("{{world_type}}", world_type.model_dump_json())
        .replace("{{base_schemas}}", json.dumps(base_schemas, ensure_ascii=False))
    )
    raw = await chat(prompt)
    data = json.loads(raw)
    return OntologySchema(**data)
