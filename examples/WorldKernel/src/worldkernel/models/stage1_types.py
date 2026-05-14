from __future__ import annotations

from pydantic import BaseModel


class WorldOrigin(BaseModel):
    type: str = "original"          # original | derived | inspired_by
    source_work: str | None = None  # 来源作品（original 时为 null）
    source_reference: str | None = None  # 具体指向（如"第七部《死亡圣器》"）


class IntentResult(BaseModel):
    raw_text: str
    world_name: str = ""
    world_origin: WorldOrigin = WorldOrigin()
    time_era: str = ""              # 时代背景，如"中世纪架空"/"现代"/"近未来"
    scope: str = ""                 # single_location | district | city | region | world
    core_theme: str = ""
    key_elements: list[str] = []
    user_intent: str = ""
    constraints: list[str] = []
    uncertain_slots: list[str] = []


class OntologyHints(BaseModel):
    character_hints: list[str] = []    # 指导 Character Template 字段生成
    location_hints: list[str] = []     # 指导 Location Template 字段生成
    relation_hints: list[str] = []     # 指导 Relation Template 生成
    institution_hints: list[str] = []  # 指导 Institution Template 生成
    rule_hints: list[str] = []         # 指导 Rule Template 生成


class WorldTemplate(BaseModel):
    # 类型分类（供 template_retriever 路由）
    primary: str
    secondary: str | None = None
    confidence: float = 0.8
    tags: list[str] = []

    # 世界身份
    world_name: str = ""
    world_origin_summary: str = ""  # 来源与主题摘要（一两句话）
    scope: str = ""                 # single_location|district|city|region|world
    time_slice: str = ""            # 时间切片，如"1997-1998学年"

    # 世界内容集合
    location_types: list[str] = []   # 地点类型集合
    character_roles: list[str] = []  # 人物身份类型集合
    macro_rules: list[str] = []      # 宏观规则列表

    # 后续本体模版生成指引
    ontology_hints: OntologyHints = OntologyHints()


class GenerationStep(BaseModel):
    name: str
    target: str


class GenerationPlan(BaseModel):
    steps: list[GenerationStep]


class TemplateMatch(BaseModel):
    type: str
    name: str
    source: str
    data: dict


class TemplateDimension(BaseModel):
    fixed: list[str] = []    # 所有世界通用的固有属性
    special: list[str] = []  # LLM 根据当前世界生成的特殊属性


class EntityTemplate(BaseModel):
    dimensions: dict[str, TemplateDimension] = {}
