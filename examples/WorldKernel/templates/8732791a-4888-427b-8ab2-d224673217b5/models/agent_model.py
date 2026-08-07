"""Auto-generated Agent Pydantic model."""
from pydantic import BaseModel


class IdentityDim(BaseModel):
    id: str = ""
    name: str = ""
    role: str = ""
    memory_credit_balance: str = ""  # world-specific
    memory_archive_id: str = ""  # world-specific
    identity_credit_level: str = ""  # world-specific
    assigned_district: str = ""  # world-specific
    institution_affiliation: str = ""  # world-specific
    resistance_affiliation: str = ""  # world-specific


class SocialProfileDim(BaseModel):
    group_id: str = ""
    reputation: str = ""
    memory_credit_rating: str = ""  # world-specific
    known_as_memory_debtor: str = ""  # world-specific
    archival_access_permission_label: str = ""  # world-specific
    black_market_contact_status: str = ""  # world-specific
    voting_rights_status_in_storm_council: str = ""  # world-specific


class CapabilitiesDim(BaseModel):
    skills: list[str] = []
    level: str = ""
    weaknesses: str = ""
    memory_negotiation_skill: str = ""  # world-specific
    illegal_memory_trade_knowledge: str = ""  # world-specific
    storm_shelter_survival_skill: str = ""  # world-specific
    data_forgery_ability: str = ""  # world-specific
    emotional_memory_suppression_ability: str = ""  # world-specific
    bribery_and_bartering_skill: str = ""  # world-specific


class PersonalityDim(BaseModel):
    traits: list[str] = []
    values: list[str] = []
    speech_style: str = ""
    attitude_toward_memory_commodification: str = ""  # world-specific
    fear_of_memory_loss: str = ""  # world-specific
    willingness_to_trade_memories: str = ""  # world-specific
    trust_toward_institutions: str = ""  # world-specific
    crisis_response_temperament: str = ""  # world-specific


class GoalsDim(BaseModel):
    short_term_goal: str = ""
    long_term_goal: str = ""
    motivation: str = ""
    memory_debt_repayment_target: str = ""  # world-specific
    desired_identity_credit_rank: str = ""  # world-specific
    planned_memory_retention_priority: str = ""  # world-specific
    ambition_to_access_upper_deck: str = ""  # world-specific
    goal_to_preserve_critical_private_memories: str = ""  # world-specific


class KnowledgeGroup(BaseModel):
    world_knowledge: list[str] = []
    social_knowledge: list[str] = []


class MemoriesDim(BaseModel):
    knowledge: KnowledgeGroup = KnowledgeGroup()
    background_summary: str = ""
    key_events: list[str] = []
    secrets: list[str] = []
    memories_recently_sold_or_seized: str = ""  # world-specific
    hidden_memory_backups_locations: str = ""  # world-specific
    knowledge_of_illegal_memory_routes: str = ""  # world-specific
    records_of_storm_tax_evasion: str = ""  # world-specific
    personal_experiences_of_memory_revaluation: str = ""  # world-specific
    forgotten_memory_gaps_from_forced_extraction: str = ""  # world-specific


class LocationGroup(BaseModel):
    location_id: str = ""


class PositionGroup(BaseModel):
    x: float = 0.0
    y: float = 0.0


class StateDim(BaseModel):
    location: LocationGroup = LocationGroup()
    position: PositionGroup = PositionGroup()
    current_storm_warning_level: str = ""  # world-specific
    memory_access_terminal_proximity: str = ""  # world-specific
    creditor_presence_nearby: str = ""  # world-specific
    surveillance_drone_overhead_status: str = ""  # world-specific
    shelter_occupancy_status: str = ""  # world-specific


class AgentModel(BaseModel):
    identity: IdentityDim = IdentityDim()
    social_profile: SocialProfileDim = SocialProfileDim()
    capabilities: CapabilitiesDim = CapabilitiesDim()
    personality: PersonalityDim = PersonalityDim()
    goals: GoalsDim = GoalsDim()
    memories: MemoriesDim = MemoriesDim()
    state: StateDim = StateDim()
    visual: str = ""
