from __future__ import annotations

import asyncio
import json
from pathlib import Path

from worldkernel.llm.client import chat_json
from worldkernel.models.stage1_types import (
    EntityTemplate,
    FieldDef,
    GenerationPlan,
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

def _f(name: str, type: str = "str", ref: str = "") -> FieldDef:
    return FieldDef(name=name, type=type, ref=ref)


_FIXED_DIMENSIONS: dict[str, dict[str, list[FieldDef]]] = {
    "character": {
        "identity":       [_f("id"), _f("name"), _f("role")],
        "personality":    [_f("traits", "list_str"), _f("values", "list_str"), _f("speech_style")],
        "capabilities":   [_f("skills", "list_str"), _f("level"), _f("weaknesses")],
        "goals":          [_f("short_term_goal"), _f("long_term_goal"), _f("motivation")],
        "constraints":    [_f("forbidden_actions", "list_str"), _f("taboos", "list_str")],
        "state":          [_f("location_id", ref="location"), _f("position_x", "float"), _f("position_y", "float")],
        "visual":         [_f("visual_description"), _f("visual_prompt")],
        "social_profile": [_f("group_id", ref="institution"), _f("reputation")],
        "relations":      [_f("relation_ids", "list_str", ref="relation")],
    },
    "location": {
        # ── Profile（地图节点属性）──────────────────────────────────
        "identity":  [_f("id"), _f("name"), _f("type"), _f("description")],
        "access":    [_f("permissions"), _f("access_level"), _f("access_conditions")],
        "state":     [_f("current_state"), _f("ownership"), _f("capacity", "int")],
        "visual":    [_f("visual_description"), _f("visual_prompt")],
        # ── Topology（地图连通结构）─────────────────────────────────
        "topology":  [_f("connected_to", "list_str", ref="location"), _f("parent_id", ref="location"),
                      _f("layer"), _f("entrance_type")],
    },
    "relation": {
        "edge":       [_f("id"), _f("from_id"), _f("to_id"), _f("type"), _f("direction")],
        "properties": [_f("strength"), _f("description")],
    },
    "institution": {
        "identity":   [_f("id"), _f("name"), _f("type")],
        "purpose":    [_f("mission"), _f("founding_reason")],
        "membership": [_f("members", "list_str", ref="character"), _f("roles", "list_str"), _f("entry_criteria")],
        "governance": [_f("leader", ref="character"), _f("rules"), _f("decision_process")],
        "resources":  [_f("assets"), _f("territory")],
        "external":   [_f("relations_to_others"), _f("public_reputation")],
    },
    "rule": {
        "identity":     [_f("id"), _f("name"), _f("scope")],
        "source":       [_f("authority"), _f("legitimacy")],
        "enforcement":  [_f("enforcer"), _f("mechanism"), _f("detectability")],
        "consequences": [_f("penalties"), _f("rewards_for_compliance")],
    },
    "action": {
        "identity":      [_f("id"), _f("name"), _f("category")],
        "preconditions": [_f("required_state"), _f("required_items")],
        "effects":       [_f("on_actor"), _f("on_target"), _f("on_environment")],
        "costs":         [_f("time"), _f("resources"), _f("social_cost")],
    },
}


def _format_dimensions(entity_key: str) -> str:
    lines = []
    for dim_name, fixed_fields in _FIXED_DIMENSIONS[entity_key].items():
        parts = [f"{f.name}:{f.type}" for f in fixed_fields]
        lines.append(f"- {dim_name}（固有：{', '.join(parts)}）")
    return "\n".join(lines)


def _build_entity_template(entity_key: str, llm_data: dict) -> EntityTemplate:
    fixed_dims = _FIXED_DIMENSIONS[entity_key]
    raw_dims = llm_data.get("dimensions", {})
    dimensions: dict[str, TemplateDimension] = {}
    for dim_name, fixed_fields in fixed_dims.items():
        dim_raw = raw_dims.get(dim_name, {})
        extra_names = dim_raw.get("extra") or dim_raw.get("special") or []
        existing_names = {f.name for f in fixed_fields}
        extra_fields = [
            FieldDef(name=n, type="str", required=False)
            for n in extra_names if n not in existing_names
        ]
        dimensions[dim_name] = TemplateDimension(fields=list(fixed_fields) + extra_fields)
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


async def generate_templates(intent: IntentResult, world_type: WorldTemplate, plan: GenerationPlan) -> dict[str, EntityTemplate]:
    loc_names = ", ".join(a.type_name for a in world_type.location_archetypes) or "无"
    char_names = ", ".join(a.type_name for a in world_type.character_archetypes) or "无"
    rule_names = ", ".join(a.type_name for a in world_type.rule_archetypes) or "无"
    sim_start = world_type.simulation_start
    world_summary = (
        f"世界名称：{world_type.world_name}\n"
        f"来源与主题：{world_type.world_origin_summary}\n"
        f"规模：{world_type.scope}　仿真起始：{sim_start.time_point}（{sim_start.trigger_event}）\n"
        f"地点类型：{loc_names}\n"
        f"人物身份类型：{char_names}\n"
        f"规则类型：{rule_names}\n"
        f"用户目标：{intent.user_intent or intent.raw_text}"
    )
    ontology_hints_json = json.dumps(plan.ontology_hints.model_dump(), ensure_ascii=False)
    template_text = _PROMPT_PATH.read_text(encoding="utf-8")

    keys = list(_FIXED_DIMENSIONS.keys())
    results = await asyncio.gather(*[
        _call_single(key, template_text, world_summary, ontology_hints_json)
        for key in keys
    ])

    mapping = dict(zip(keys, results))
    return mapping
