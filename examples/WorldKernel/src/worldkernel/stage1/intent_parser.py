from __future__ import annotations

import json
from pathlib import Path

from worldkernel.llm.client import chat_json
from worldkernel.models.stage1_types import IntentResult

_PROMPT_PATH = Path(__file__).parent.parent / "prompts" / "stage1_parse_intent.md"

_SYSTEM = (
    "你是一个世界创建系统的意图解析模块。"
    "你的职责不是简单提取用户所说的内容，而是进行深度意图解析："
    "推断用户模糊表达的真实含义（例如「最后一部」→具体作品和时间段），"
    "基于世界背景知识补全用户未明确说明但可合理推断的信息，"
    "将解析结果按固定模板结构化输出。"
    "只输出合法 JSON，不输出任何解释、标注或额外文字。"
)


async def parse_intent(raw_text: str) -> IntentResult:
    template = _PROMPT_PATH.read_text(encoding="utf-8")
    prompt = template.replace("{{input}}", raw_text)
    raw = await chat_json(prompt, system=_SYSTEM)
    data = json.loads(raw)
    if "raw_text" not in data and len(data) == 1:
        data = next(iter(data.values()))
    return IntentResult(**data)
