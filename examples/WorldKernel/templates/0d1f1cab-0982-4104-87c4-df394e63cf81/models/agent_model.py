"""Auto-generated Agent Pydantic model."""
from pydantic import BaseModel


class IdentityDim(BaseModel):
    id: str = ""
    name: str = ""
    role: str = ""
    identity_anchor_code: str = ""  # world-specific
    memory_asset_level: str = ""  # world-specific
    legal_status: str = ""  # world-specific
    civic_rank: str = ""  # world-specific
    registry_identification: str = ""  # world-specific


class SocialProfileDim(BaseModel):
    group_id: str = ""
    reputation: str = ""
    memory_credit_score: str = ""  # world-specific
    social_stratum: str = ""  # world-specific
    black_market_standing: str = ""  # world-specific
    civic_trust_level: str = ""  # world-specific
    patron_client_links: str = ""  # world-specific


class CapabilitiesDim(BaseModel):
    skills: list[str] = []
    level: str = ""
    weaknesses: str = ""
    memory_appraisal_skill: str = ""  # world-specific
    memory_manipulation_resistance: str = ""  # world-specific
    storm_tolerance_threshold: str = ""  # world-specific
    anchor_verification_proficiency: str = ""  # world-specific
    blackmail_protocol_knowledge: str = ""  # world-specific


class PersonalityDim(BaseModel):
    traits: list[str] = []
    values: list[str] = []
    speech_style: str = ""
    attitude_toward_memory_trade: str = ""  # world-specific
    risk_tolerance: str = ""  # world-specific
    nostalgia_bias: str = ""  # world-specific
    suspicion_index: str = ""  # world-specific
    reaction_to_identity_threats: str = ""  # world-specific


class GoalsDim(BaseModel):
    short_term_goal: str = ""
    long_term_goal: str = ""
    motivation: str = ""
    target_memory_acquisition_list: str = ""  # world-specific
    desired_social_standing: str = ""  # world-specific
    debt_repayment_target_amount: str = ""  # world-specific
    identity_recovery_priority: str = ""  # world-specific
    political_ambition_level: str = ""  # world-specific


class KnowledgeGroup(BaseModel):
    world_knowledge: list[str] = []
    social_knowledge: list[str] = []


class MemoriesDim(BaseModel):
    knowledge: KnowledgeGroup = KnowledgeGroup()
    background_summary: str = ""
    key_events: list[str] = []
    secrets: list[str] = []
    tradable_memory_inventory: str = ""  # world-specific
    memory_gap_manifestations: str = ""  # world-specific
    implanted_memory_indicators: str = ""  # world-specific
    stolen_memory_records: str = ""  # world-specific
    memory_authenticity_flags: str = ""  # world-specific


class LocationGroup(BaseModel):
    location_id: str = ""


class PositionGroup(BaseModel):
    x: float = 0.0
    y: float = 0.0


class StateDim(BaseModel):
    location: LocationGroup = LocationGroup()
    position: PositionGroup = PositionGroup()
    current_storm_zone: str = ""  # world-specific
    shield_energy_level: str = ""  # world-specific
    memory_reserve_quantity: str = ""  # world-specific
    immediate_debt_status: str = ""  # world-specific
    psychic_instability_current: str = ""  # world-specific


class AgentModel(BaseModel):
    identity: IdentityDim = IdentityDim()
    social_profile: SocialProfileDim = SocialProfileDim()
    capabilities: CapabilitiesDim = CapabilitiesDim()
    personality: PersonalityDim = PersonalityDim()
    goals: GoalsDim = GoalsDim()
    memories: MemoriesDim = MemoriesDim()
    state: StateDim = StateDim()
    visual: str = ""
