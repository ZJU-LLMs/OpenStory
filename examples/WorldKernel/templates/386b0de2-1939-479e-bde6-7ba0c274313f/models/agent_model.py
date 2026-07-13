"""Auto-generated Agent Pydantic model."""
from pydantic import BaseModel


class IdentityDim(BaseModel):
    id: str = ""
    name: str = ""
    role: str = ""
    memory_balance: str = ""  # world-specific
    credit_grade: str = ""  # world-specific
    class_color_badge: str = ""  # world-specific
    district_level: str = ""  # world-specific
    has_secret_vault: str = ""  # world-specific


class SocialProfileDim(BaseModel):
    group_id: str = ""
    reputation: str = ""
    credit_grade: str = ""  # world-specific
    trade_reputation_score: str = ""  # world-specific
    faction: str = ""  # world-specific
    memory_trade_license_status: str = ""  # world-specific


class CapabilitiesDim(BaseModel):
    skills: list[str] = []
    level: str = ""
    weaknesses: str = ""
    memory_extraction_skill: str = ""  # world-specific
    memory_storage_capacity: str = ""  # world-specific
    storm_endurance: str = ""  # world-specific
    black_market_contact_level: str = ""  # world-specific


class PersonalityDim(BaseModel):
    traits: list[str] = []
    values: list[str] = []
    speech_style: str = ""
    attitude_towards_memory_trade: str = ""  # world-specific
    memory_addiction_level: str = ""  # world-specific
    risk_preference: str = ""  # world-specific
    trust_in_others: str = ""  # world-specific


class GoalsDim(BaseModel):
    short_term_goal: str = ""
    long_term_goal: str = ""
    motivation: str = ""
    memory_accumulation_target: str = ""  # world-specific
    social_rank_aspiration: str = ""  # world-specific
    secret_vault_size_target: str = ""  # world-specific
    desired_memory_type: str = ""  # world-specific


class KnowledgeGroup(BaseModel):
    world_knowledge: list[str] = []
    social_knowledge: list[str] = []


class MemoriesDim(BaseModel):
    knowledge: KnowledgeGroup = KnowledgeGroup()
    background_summary: str = ""
    key_events: list[str] = []
    secrets: list[str] = []
    extracted_memory_types: str = ""  # world-specific
    remaining_memory_volume: str = ""  # world-specific
    vault_memory_count: str = ""  # world-specific
    forgotten_event_count: str = ""  # world-specific


class LocationGroup(BaseModel):
    location_id: str = ""


class PositionGroup(BaseModel):
    x: float = 0.0
    y: float = 0.0


class StateDim(BaseModel):
    location: LocationGroup = LocationGroup()
    position: PositionGroup = PositionGroup()
    current_memory_balance: str = ""  # world-specific
    fatigue_level: str = ""  # world-specific
    storm_noise_exposure: str = ""  # world-specific
    energy_shield_status: str = ""  # world-specific


class AgentModel(BaseModel):
    identity: IdentityDim = IdentityDim()
    social_profile: SocialProfileDim = SocialProfileDim()
    capabilities: CapabilitiesDim = CapabilitiesDim()
    personality: PersonalityDim = PersonalityDim()
    goals: GoalsDim = GoalsDim()
    memories: MemoriesDim = MemoriesDim()
    state: StateDim = StateDim()
    visual: str = ""
