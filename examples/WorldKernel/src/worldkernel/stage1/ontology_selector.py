from __future__ import annotations

import asyncio
import json
from pathlib import Path

from worldkernel.llm.client import chat_json
from worldkernel.models.stage1_types import (
    EntityTemplate,
    IntentResult,
    TemplateDimension,
    WorldTemplate,
)

_PROMPT_PATH = Path(__file__).parent.parent / "prompts" / "stage1_generate_templates.md"

_SYSTEM = (
    "你是一个通用实体模版生成模块。"
    "根据世界信息和本体指引，为指定实体类型的每个维度生成该世界专有的特殊属性列表。"
    "只输出合法 JSON，不输出任何解释、标注或额外文字。"
)

_ENTITY_NAMES: dict[str, str] = {
    "character":   "人物/角色（Character）",
    "location":    "地点/场所（Location）",
    "relation":    "关系（Relation）",
    "institution": "机构/组织（Institution）",
    "rule":        "规则/法规（Rule）",
    "action":      "动作/行为（Action）",
}

_FIXED_DIMENSIONS: dict[str, dict[str, list[str]]] = {
    "character": {
        "identity":     ["id", "name", "role"],
        "personality":  ["traits", "values", "speech_style"],
        "capabilities": ["skills", "level", "weaknesses"],
        "social":       ["group_id", "allies", "rivals", "reputation"],
        "goals":        ["short_term_goal", "long_term_goal", "motivation"],
        "constraints":  ["forbidden_actions", "taboos"],
    },
    "location": {
        "identity":   ["id", "name", "type"],
        "spatial":    ["size", "connected_to", "capacity"],
        "access":     ["permissions", "open_hours"],
        "activities": ["associated_events", "typical_occupants"],
        "atmosphere": ["description", "mood"],
        "state":      ["current_state", "ownership"],
    },
    "relation": {
        "identity": ["id", "from_id", "to_id", "type"],
        "nature":   ["direction", "strength", "public_or_secret"],
        "history":  ["origin", "duration"],
        "dynamics": ["change_triggers", "stability"],
        "effects":  ["behavioral_impact", "mutual_obligations"],
    },
    "institution": {
        "identity":   ["id", "name", "type"],
        "purpose":    ["mission", "founding_reason"],
        "membership": ["members", "roles", "entry_criteria"],
        "governance": ["leader", "rules", "decision_process"],
        "resources":  ["assets", "territory"],
        "external":   ["relations_to_others", "public_reputation"],
    },
    "rule": {
        "identity":     ["id", "name", "scope"],
        "source":       ["authority", "legitimacy"],
        "enforcement":  ["enforcer", "mechanism", "detectability"],
        "consequences": ["penalties", "rewards_for_compliance"],
    },
    "action": {
        "identity":      ["id", "name", "category"],
        "preconditions": ["required_state", "required_items"],
        "effects":       ["on_actor", "on_target", "on_environment"],
        "costs":         ["time", "resources", "social_cost"],
    },
}


def _format_dimensions(entity_key: str) -> str:
    lines = []
    for dim_name, fixed_attrs in _FIXED_DIMENSIONS[entity_key].items():
        lines.append(f"- {dim_name}（固有：{', '.join(fixed_attrs)}）")
    return "\n".join(lines)


def _build_entity_template(entity_key: str, llm_data: dict) -> EntityTemplate:
    fixed_dims = _FIXED_DIMENSIONS[entity_key]
    raw_dims = llm_data.get("dimensions", {})
    dimensions: dict[str, TemplateDimension] = {}
    for dim_name, fixed_attrs in fixed_dims.items():
        special_attrs = raw_dims.get(dim_name, {}).get("special", [])
        dimensions[dim_name] = TemplateDimension(fixed=fixed_attrs, special=special_attrs)
    return EntityTemplate(dimensions=dimensions)


async def _call_single(
    entity_key: str,
    template_text: str,
    world_summary: str,
    ontology_hints_json: str,
) -> EntityTemplate:
    prompt = (
        template_text
        .replace("{{world_summary}}", world_summary)
        .replace("{{ontology_hints}}", ontology_hints_json)
        .replace("{{entity_name}}", _ENTITY_NAMES[entity_key])
        .replace("{{entity_dimensions}}", _format_dimensions(entity_key))
    )
    raw = await chat_json(prompt, system=_SYSTEM)
    data = json.loads(raw)
    if "dimensions" not in data and len(data) == 1:
        data = next(iter(data.values()))
    return _build_entity_template(entity_key, data)


async def generate_templates(intent: IntentResult, world_type: WorldTemplate) -> dict[str, EntityTemplate]:
    world_summary = (
        f"世界名称：{world_type.world_name}\n"
        f"来源与主题：{world_type.world_origin_summary}\n"
        f"规模：{world_type.scope}　时间切片：{world_type.time_slice}\n"
        f"地点集合：{', '.join(world_type.location_types)}\n"
        f"人物身份：{', '.join(world_type.character_roles)}\n"
        f"宏观规则：{', '.join(world_type.macro_rules)}\n"
        f"用户目标：{intent.user_intent or intent.raw_text}"
    )
    ontology_hints_json = json.dumps(world_type.ontology_hints.model_dump(), ensure_ascii=False)
    template_text = _PROMPT_PATH.read_text(encoding="utf-8")

    keys = list(_FIXED_DIMENSIONS.keys())
    results = await asyncio.gather(*[
        _call_single(key, template_text, world_summary, ontology_hints_json)
        for key in keys
    ])

    mapping = dict(zip(keys, results))
    return mapping
