from __future__ import annotations

import json
from pathlib import Path

from worldkernel.llm.client import chat_json
from worldkernel.models.stage1_types import GenerationPlan, IntentResult, WorldTemplate

_PROMPT_PATH = Path(__file__).parent.parent / "prompts" / "stage1_plan_generation.md"

_SYSTEM = (
    "你是一个世界生成计划制定模块。"
    "你的职责是根据用户意图和世界模版，制定世界内容的生成步骤列表，不直接生成任何内容。"
    "步骤应覆盖世界模版中的所有地点类型、人物身份和宏观规则。"
    "只输出合法 JSON，不输出任何解释、标注或额外文字。"
)


async def plan_generation(intent: IntentResult, world_type: WorldTemplate) -> GenerationPlan:
    type_summary = world_type.world_origin_summary or world_type.primary
    if world_type.secondary:
        type_summary += f"（兼含 {world_type.secondary}）"

    template = _PROMPT_PATH.read_text(encoding="utf-8")
    prompt = (
        template
        .replace("{{user_goal}}", intent.user_intent or intent.raw_text)
        .replace("{{world_type_summary}}", type_summary)
        .replace("{{tags}}", ", ".join(world_type.tags) or "无")
        .replace("{{location_types}}", ", ".join(world_type.location_types) or "无")
        .replace("{{character_roles}}", ", ".join(world_type.character_roles) or "无")
        .replace("{{macro_rules}}", ", ".join(world_type.macro_rules) or "无")
    )
    raw = await chat_json(prompt, system=_SYSTEM)
    data = json.loads(raw)
    # LLM 可能返回裸数组 [{...}, ...] 或单个步骤 {"name":..., "target":...}
    if isinstance(data, list):
        data = {"steps": data}
    elif "steps" not in data:
        if "name" in data and "target" in data:
            data = {"steps": [data]}
        elif len(data) == 1:
            data = next(iter(data.values()))
            if isinstance(data, list):
                data = {"steps": data}
    return GenerationPlan(**data)
