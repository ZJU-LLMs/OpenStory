from __future__ import annotations

from pydantic import BaseModel


class WorldOrigin(BaseModel):
    type: str = "original"          # original | derived | inspired_by
    source_work: str | None = None
    source_reference: str | None = None


class IntentResult(BaseModel):
    raw_text: str
    world_name: str = ""
    world_origin: WorldOrigin = WorldOrigin()
    time_era: str = ""
    scope: str = ""                 # single_location | district | city | region | world
    core_theme: str = ""
    key_elements: list[str] = []
    user_intent: str = ""
    constraints: list[str] = []
    uncertain_slots: list[str] = []


# ── Archetype + Seed 结构（地点 / 人物 / 规则共用同一模式）──────────────

class LocationSeed(BaseModel):
    seed_id: str
    name: str
    importance: str = ""            # core | major | minor
    source_type: str = ""           # canonical | inferred | original
    confidence: float = 0.9
    generation_priority: int = 1
    role_in_world: str = ""


class LocationArchetype(BaseModel):
    type_id: str
    type_name: str
    description: str = ""
    common_fields: list[str] = []
    candidate_location_seeds: list[LocationSeed] = []


class CharacterSeed(BaseModel):
    seed_id: str
    name: str
    importance: str = ""
    source_type: str = ""
    confidence: float = 0.9
    generation_priority: int = 1
    role_in_world: str = ""


class CharacterArchetype(BaseModel):
    type_id: str
    type_name: str
    description: str = ""
    common_fields: list[str] = []
    candidate_character_seeds: list[CharacterSeed] = []


class RuleSeed(BaseModel):
    seed_id: str
    name: str
    importance: str = ""
    source_type: str = ""
    confidence: float = 0.9
    generation_priority: int = 1
    role_in_world: str = ""


class RuleArchetype(BaseModel):
    type_id: str
    type_name: str
    description: str = ""
    common_fields: list[str] = []
    candidate_rule_seeds: list[RuleSeed] = []


# ── 高层世界观约束（非具体规则，是世界运行的根本前提）──────────────────

class WorldConstraint(BaseModel):
    constraint_id: str
    name: str
    description: str = ""
    scope: str = "global"           # global | faction | location


# ── 仿真起始时间节点 ──────────────────────────────────────────────────

class SimulationStart(BaseModel):
    time_point: str = ""            # 如 "1997学年开学"
    trigger_event: str = ""         # 如 "邓布利多去世后食死徒控制霍格沃茨"
    year: str = ""
    narrative_context: str = ""


# ── 世界模版 ──────────────────────────────────────────────────────────

class WorldTemplate(BaseModel):
    primary: str
    secondary: str | None = None
    confidence: float = 0.8
    tags: list[str] = []

    world_name: str = ""
    world_origin_summary: str = ""
    scope: str = ""
    simulation_start: SimulationStart = SimulationStart()

    location_archetypes: list[LocationArchetype] = []
    character_archetypes: list[CharacterArchetype] = []
    rule_archetypes: list[RuleArchetype] = []
    world_constraints: list[WorldConstraint] = []


# ── 本体生成指引（ontology_selector 使用，由 generation_planner 生成）──

class OntologyHints(BaseModel):
    character_hints: list[str] = []
    location_hints: list[str] = []
    relation_hints: list[str] = []
    institution_hints: list[str] = []
    rule_hints: list[str] = []


# ── 生成计划 ──────────────────────────────────────────────────────────

class EntitySeed(BaseModel):
    """entity_plan 中各实体列表的通用种子结构。"""
    seed_id: str
    name: str
    entity_type: str                # location | character | institution | rule
    importance: str = ""            # core | major | minor
    source_type: str = ""           # canonical | inferred | original
    confidence: float = 0.9
    generation_priority: int = 1
    role_in_world: str = ""


class EntityPlan(BaseModel):
    locations: dict[str, list[EntitySeed]] = {}      # archetype_id -> seeds
    characters: dict[str, list[EntitySeed]] = {}
    institutions: dict[str, list[EntitySeed]] = {}
    rules: dict[str, list[EntitySeed]] = {}


class GenerationStep(BaseModel):
    step_id: str
    generator_type: str             # world_background_generator | location_generator |
                                    # character_generator | relation_generator |
                                    # institution_generator | rule_generator | action_generator
    depends_on: list[str] = []      # 必须先完成的 step_id 列表
    target_entity_type: str         # location | character | relation | institution |
                                    # rule | action | world_background
    target_seeds: list[str] = []    # 该步骤负责生成的 seed_id（来自 entity_plan）
    context_refs: list[str] = []    # 需要作为上下文输入的 step_id
    batch_size: int = 5
    priority: int = 1
    description: str = ""


class GenerationPlan(BaseModel):
    steps: list[GenerationStep]
    entity_plan: EntityPlan = EntityPlan()
    ontology_hints: OntologyHints = OntologyHints()


# ── 实体通用模版 ──────────────────────────────────────────────────────

class FieldDef(BaseModel):
    name: str
    type: str = "str"        # str | int | float | bool | list_str
    required: bool = True
    ref: str = ""            # 引用的实体类型，如 "location" | "relation"


class TemplateDimension(BaseModel):
    fields: list[FieldDef] = []


class EntityTemplate(BaseModel):
    dimensions: dict[str, TemplateDimension] = {}
