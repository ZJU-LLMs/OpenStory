from __future__ import annotations

import json
from pathlib import Path

from worldkernel.llm.client import chat_json
from worldkernel.models.stage1_types import GenerationPlan, IntentResult, WorldTemplate

_PROMPT_PATH = Path(__file__).parent.parent / "prompts" / "stage1_plan_generation.md"

_SYSTEM = (
    "你是一个世界生成计划制定模块。"
    "你的职责是根据用户意图和世界模版，"
    "制定世界内容的生成步骤列表，同时生成六类实体模版的语义指引。"
    "不直接生成任何世界内容。"
    "只输出合法 JSON，不输出任何解释、标注或额外文字。"
)


def _fmt_archetypes(archetypes: list) -> str:
    return ", ".join(a.type_name for a in archetypes) or "无"


def _fmt_constraints(constraints: list) -> str:
    return ", ".join(c.name for c in constraints) or "无"


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
        .replace("{{location_archetypes}}", _fmt_archetypes(world_type.location_archetypes))
        .replace("{{character_archetypes}}", _fmt_archetypes(world_type.character_archetypes))
        .replace("{{rule_archetypes}}", _fmt_archetypes(world_type.rule_archetypes))
        .replace("{{world_constraints}}", _fmt_constraints(world_type.world_constraints))
    )
    raw = await chat_json(prompt, system=_SYSTEM)
    data = json.loads(raw)

    # 新格式：顶层含 steps + entity_plan + ontology_hints
    # 容错：LLM 仍返回裸步骤列表时包装为 {"steps": [...]}
    if isinstance(data, list):
        data = {"steps": data}
    elif "steps" not in data and "entity_plan" not in data:
        # 单层包装，如 {"generation_plan": {...}}
        if len(data) == 1:
            data = next(iter(data.values()))

    return GenerationPlan.model_validate(data)
