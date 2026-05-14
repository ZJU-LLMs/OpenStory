from __future__ import annotations

import json
from pathlib import Path

from worldkernel.llm.client import chat_json
from worldkernel.models.stage1_types import IntentResult, OntologyHints, WorldTemplate

_PROMPT_PATH = Path(__file__).parent.parent / "prompts" / "stage1_classify_world.md"

_SYSTEM = (
    "你是一个世界模版构建模块。"
    "你的职责是根据用户意图，构建一个完整的通用世界基础模版，"
    "包括世界类型识别、地点集合、人物身份集合、宏观规则，"
    "以及指导后续 Character/Location/Relation/Institution 模版生成的语义提示。"
    "要充分运用世界背景知识补全用户未明确说明但可合理推断的要素。"
    "只输出合法 JSON，不输出任何解释、标注或额外文字。"
)


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

    # LLM 有时按分节标题嵌套，如 {"type_description": {"primary":...}, "world_identity": {...}}
    # 自动展平：把不是 ontology_hints 的嵌套 dict 合并到顶层
    if "primary" not in data:
        flat: dict = {}
        for k, v in data.items():
            if isinstance(v, dict) and k != "ontology_hints":
                flat.update(v)
            else:
                flat[k] = v
        data = flat

    # 解析嵌套的 ontology_hints
    hints_data = data.pop("ontology_hints", {})
    ontology_hints = OntologyHints(**hints_data) if hints_data else OntologyHints()

    return WorldTemplate(**data, ontology_hints=ontology_hints)
