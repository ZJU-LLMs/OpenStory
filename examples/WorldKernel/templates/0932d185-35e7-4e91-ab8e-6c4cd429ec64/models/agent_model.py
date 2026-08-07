"""Auto-generated Agent Pydantic model."""
from pydantic import BaseModel


class IdentityDim(BaseModel):
    id: str = ""
    name: str = ""
    role: str = ""
    credit_score: str = ""  # world-specific
    memory_holdings_grams: str = ""  # world-specific
    social_class_tier: str = ""  # world-specific
    memory_trade_role: str = ""  # world-specific
    identity_reallocation_count: str = ""  # world-specific
    registered_memory_archive_id: str = ""  # world-specific


class SocialProfileDim(BaseModel):
    group_id: str = ""
    reputation: str = ""
    memory_network_position: str = ""  # world-specific
    governing_body_affiliation_level: str = ""  # world-specific
    resistance_membership_status: str = ""  # world-specific
    memory_debtor_creditor_relations: str = ""  # world-specific
    archival_access_clearance: str = ""  # world-specific
    black_market_memory_contact_rating: str = ""  # world-specific


class CapabilitiesDim(BaseModel):
    skills: list[str] = []
    level: str = ""
    weaknesses: str = ""
    memory_extraction_tolerance: str = ""  # world-specific
    memory_forgery_skill: str = ""  # world-specific
    memory_empathy_ability: str = ""  # world-specific
    memory_preservation_capacity: str = ""  # world-specific
    storm_survival_training: str = ""  # world-specific
    forged_memory_detection_skill: str = ""  # world-specific


class PersonalityDim(BaseModel):
    traits: list[str] = []
    values: list[str] = []
    speech_style: str = ""
    persona_integrity_percent: str = ""  # world-specific
    memory_loss_level: str = ""  # world-specific
    attitude_towards_memory_trade: str = ""  # world-specific
    emotional_memory_retention: str = ""  # world-specific
    suspicion_of_authority: str = ""  # world-specific
    desire_for_memory_restoration: str = ""  # world-specific


class GoalsDim(BaseModel):
    short_term_goal: str = ""
    long_term_goal: str = ""
    motivation: str = ""
    target_memory_to_restore: str = ""  # world-specific
    desired_memory_assets: str = ""  # world-specific
    memory_debt_clearance_goal: str = ""  # world-specific
    planned_resistance_action: str = ""  # world-specific
    archival_access_objective: str = ""  # world-specific
    storm_window_exploitation_plan: str = ""  # world-specific


class KnowledgeGroup(BaseModel):
    world_knowledge: list[str] = []
    social_knowledge: list[str] = []


class MemoriesDim(BaseModel):
    knowledge: KnowledgeGroup = KnowledgeGroup()
    background_summary: str = ""
    key_events: list[str] = []
    secrets: list[str] = []
    total_memory_storage_capacity: str = ""  # world-specific
    memory_integrity_ratio: str = ""  # world-specific
    sealed_memory_count: str = ""  # world-specific
    memory_trade_history_entries: str = ""  # world-specific
    forgotten_loved_ones_count: str = ""  # world-specific
    stolen_memory_identification_flag: str = ""  # world-specific


class LocationGroup(BaseModel):
    location_id: str = ""


class PositionGroup(BaseModel):
    x: float = 0.0
    y: float = 0.0


class StateDim(BaseModel):
    location: LocationGroup = LocationGroup()
    position: PositionGroup = PositionGroup()
    current_memory_debt: str = ""  # world-specific
    credit_tier: str = ""  # world-specific
    storm_alert_level: str = ""  # world-specific
    memory_extraction_count_today: str = ""  # world-specific
    contraband_memory_cache_hidden: str = ""  # world-specific
    current_archival_status: str = ""  # world-specific


class AgentModel(BaseModel):
    identity: IdentityDim = IdentityDim()
    social_profile: SocialProfileDim = SocialProfileDim()
    capabilities: CapabilitiesDim = CapabilitiesDim()
    personality: PersonalityDim = PersonalityDim()
    goals: GoalsDim = GoalsDim()
    memories: MemoriesDim = MemoriesDim()
    state: StateDim = StateDim()
    visual: str = ""
