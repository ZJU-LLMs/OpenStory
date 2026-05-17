from __future__ import annotations

import json
from pathlib import Path

from worldkernel.llm.client import chat_json
from worldkernel.stage1.types import IntentResult, WorldTemplate

_PROMPT_PATH = Path(__file__).parent / "prompts" / "classify_world.md"

_SYSTEM = (
    "你是一个世界模版构建模块。"
    "你的职责是根据用户意图，构建一个完整的通用世界基础模版，"
    "包括世界类型识别、地点类型集合、人物身份集合、规则类型、"
    "高层世界约束，以及具体的仿真起始时间节点。"
    "要充分运用世界背景知识补全用户未明确说明但可合理推断的要素。"
    "只输出合法 JSON，不输出任何解释、标注或额外文字。"
)

_NESTED_KEYS = {"location_archetypes", "character_archetypes", "rule_archetypes",
                "world_constraints", "simulation_start"}


async def build_world_template(intent: IntentResult) -> WorldTemplate:
    summary = (
        f"世界名称：{intent.world_name or '未知'}\n"
        f"来源类型：{intent.world_origin.type}\n"
        f"来源作品：{intent.world_origin.source_work or '无'}\n"
        f"具体指向：{intent.world_origin.source_reference or '无'}\n"
        f"时代背景：{intent.time_era or '未知'}\n"
        f"世界规模：{intent.scope or '未知'}\n"
        f"核心主题：{intent.core_theme or '未知'}\n"
        f"关键要素：{', '.join(intent.key_elements) or '未知'}\n"
        f"用户目标：{intent.user_intent or intent.raw_text}\n"
        f"约束条件：{', '.join(intent.constraints) or '无'}"
    )

    template = _PROMPT_PATH.read_text(encoding="utf-8")
    prompt = template.replace("{{intent_summary}}", summary)
    raw = await chat_json(prompt, system=_SYSTEM)
    data = json.loads(raw)

    # LLM 有时按分节标题嵌套，把顶层非保护键的嵌套 dict 展平
    if "primary" not in data:
        flat: dict = {}
        for k, v in data.items():
            if isinstance(v, dict) and k not in _NESTED_KEYS:
                flat.update(v)
            else:
                flat[k] = v
        data = flat

    return WorldTemplate.model_validate(data)
