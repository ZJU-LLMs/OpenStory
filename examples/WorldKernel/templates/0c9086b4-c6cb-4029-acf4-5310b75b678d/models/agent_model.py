"""Auto-generated Agent Pydantic model."""
from pydantic import BaseModel


class IdentityDim(BaseModel):
    id: str = ""
    name: str = ""
    role: str = ""
    memory_asset_value: float = 0.0  # world-specific
    memory_debt: float = 0.0  # world-specific
    identity_archive_id: str = ""  # world-specific
    memory_tax_status: str = ""  # world-specific
    is_amnesiac: bool = False  # world-specific
    memory_integrity: float = 0.0  # world-specific


class SocialProfileDim(BaseModel):
    group_id: str = ""
    reputation: str = ""
    social_class: str = ""  # world-specific
    faction_affiliation: str = ""  # world-specific
    wanted_level: str = ""  # world-specific
    memory_reputation_index: float = 0.0  # world-specific


class CapabilitiesDim(BaseModel):
    skills: list[str] = []
    level: str = ""
    weaknesses: str = ""
    memory_appraisal_precision: str = ""  # world-specific
    negotiation_power: int = 0  # world-specific
    storm_survival_training: str = ""  # world-specific
    memory_clearance_level: str = ""  # world-specific
    illegal_tech_familiarity: str = ""  # world-specific


class PersonalityDim(BaseModel):
    traits: list[str] = []
    values: list[str] = []
    speech_style: str = ""
    memory_ethics_stance: str = ""  # world-specific
    trust_tendency: str = ""  # world-specific
    memory_attachment: str = ""  # world-specific


class GoalsDim(BaseModel):
    short_term_goal: str = ""
    long_term_goal: str = ""
    motivation: str = ""
    memory_wealth_goal: float = 0.0  # world-specific
    debt_repayment_goal: float = 0.0  # world-specific
    missing_memory_goal: str = ""  # world-specific
    status_goal: str = ""  # world-specific


class KnowledgeGroup(BaseModel):
    world_knowledge: list[str] = []
    social_knowledge: list[str] = []


class MemoriesDim(BaseModel):
    knowledge: KnowledgeGroup = KnowledgeGroup()
    background_summary: str = ""
    key_events: list[str] = []
    secrets: list[str] = []
    archive_id: str = ""  # world-specific
    memory_quality_index: float = 0.0  # world-specific
    missing_memory_segments: list[str] = []  # world-specific
    has_forged_memories: bool = False  # world-specific
    memory_fragments: int = 0  # world-specific


class LocationGroup(BaseModel):
    location_id: str = ""


class PositionGroup(BaseModel):
    x: float = 0.0
    y: float = 0.0


class StateDim(BaseModel):
    location: LocationGroup = LocationGroup()
    position: PositionGroup = PositionGroup()
    current_memory_state: str = ""  # world-specific
    current_storm_alert: str = ""  # world-specific
    current_debt_status: str = ""  # world-specific
    in_safe_zone: bool = False  # world-specific


class AgentModel(BaseModel):
    identity: IdentityDim = IdentityDim()
    social_profile: SocialProfileDim = SocialProfileDim()
    capabilities: CapabilitiesDim = CapabilitiesDim()
    personality: PersonalityDim = PersonalityDim()
    goals: GoalsDim = GoalsDim()
    memories: MemoriesDim = MemoriesDim()
    state: StateDim = StateDim()
    visual: str = ""
