from __future__ import annotations

import json
from pathlib import Path

from worldkernel.models.stage1_types import (
    EntityTemplate,
    GenerationPlan,
    IntentResult,
    WorldTemplate,
    KnowledgeChunk,  # 新增
)
from worldkernel.models.world_spec import SessionInfo
from worldkernel.stage1.generation_planner import plan_generation
from worldkernel.stage1.intent_parser import parse_intent
from worldkernel.stage1.ontology_selector import generate_templates
from worldkernel.stage1.world_type_classifier import build_world_template
from worldkernel.stage1.rag_extractor import extract_knowledge  # 新增

_WORLDS_DIR = Path(__file__).parent.parent.parent.parent / "worlds" / "generated"


class Stage1Error(Exception):
    def __init__(self, step: str, cause: Exception) -> None:
        self.step = step
        self.cause = cause
        super().__init__(f"Stage 1 failed at [{step}]: {cause}")


async def run_stage1(raw_input: str, reference_text: str = "") -> SessionInfo:
    """
    运行 Stage 1 流水线：从用户意图（及可选的参考资料）生成世界蓝图。
    """
    session = SessionInfo(source_input=raw_input)
    out_dir = _WORLDS_DIR / session.session_id
    out_dir.mkdir(parents=True, exist_ok=True)

    # --- 阶段 0: RAG 知识抽取 (新增) ---
    if reference_text:
        try:
            # 提取原著中的人物、地点、事件和规则
            knowledge: KnowledgeChunk = await extract_knowledge(reference_text)
            _save(out_dir, "extracted_knowledge.json", knowledge.model_dump())
        except Exception as e:
            raise Stage1Error("rag_extractor", e) from e

    # --- 阶段 1: 意图解析 ---
    try:
        intent: IntentResult = await parse_intent(raw_input)
    except Exception as e:
        raise Stage1Error("intent_parser", e) from e

    # --- 阶段 2: 世界类型识别 ---
    try:
        world_type: WorldTemplate = await build_world_template(intent)
    except Exception as e:
        raise Stage1Error("world_type_classifier", e) from e

    # --- 阶段 3: 生成计划制定 ---
    try:
        plan: GenerationPlan = await plan_generation(intent, world_type)
    except Exception as e:
        raise Stage1Error("generation_planner", e) from e

    # --- 阶段 4: 本体模板生成 ---
    try:
        templates: dict[str, EntityTemplate] = await generate_templates(intent, world_type)
    except Exception as e:
        raise Stage1Error("ontology_selector", e) from e

    # --- 持久化输出 ---
    _save(out_dir, "world_template.json", world_type.model_dump())
    _save(out_dir, "generation_plan.json", plan.model_dump())
    for entity_key, entity_template in templates.items():
        _save(out_dir, f"{entity_key}_template.json", entity_template.model_dump())

    return session


def _save(out_dir: Path, filename: str, data: dict) -> None:
    (out_dir / filename).write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )