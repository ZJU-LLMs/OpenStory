"""Auto-generated Agent Pydantic model."""
from pydantic import BaseModel


class IdentityDim(BaseModel):
    id: str = ""
    name: str = ""
    role: str = ""
    memory_asset_balance: str = ""  # world-specific
    memory_debt_amount: str = ""  # world-specific
    debt_repayment_status: str = ""  # world-specific
    identity_archive_number: str = ""  # world-specific
    social_credit_grade: str = ""  # world-specific
    memory_status_code: str = ""  # world-specific
    identity_qualification_flag: str = ""  # world-specific
    stance_towards_memory_bureau: str = ""  # world-specific


class SocialProfileDim(BaseModel):
    group_id: str = ""
    reputation: str = ""
    memory_trader_reputation: str = ""  # world-specific
    debtor_community_status: str = ""  # world-specific
    archive_bureau_trust_level: str = ""  # world-specific
    resistance_cell_standing: str = ""  # world-specific
    black_market_credibility: str = ""  # world-specific
    social_credit_change_trend: str = ""  # world-specific
    identity_stability_rating: str = ""  # world-specific


class CapabilitiesDim(BaseModel):
    skills: list[str] = []
    level: str = ""
    weaknesses: str = ""
    memory_extraction_skill: str = ""  # world-specific
    memory_synthesis_skill: str = ""  # world-specific
    memory_forgery_skill: str = ""  # world-specific
    debt_negotiation_skill: str = ""  # world-specific
    archive_system_hacking_ability: str = ""  # world-specific
    storm_survival_training: str = ""  # world-specific
    memory_resistance_ability: str = ""  # world-specific
    identity_reconstruction_skill: str = ""  # world-specific


class PersonalityDim(BaseModel):
    traits: list[str] = []
    values: list[str] = []
    speech_style: str = ""
    attitude_towards_debt: str = ""  # world-specific
    trust_in_memory_system: str = ""  # world-specific
    risk_tolerance_in_memory_trading: str = ""  # world-specific
    empathy_for_identity_loss: str = ""  # world-specific
    desire_for_authentic_self: str = ""  # world-specific
    resistance_tendency: str = ""  # world-specific
    compliance_with_archive_rules: str = ""  # world-specific


class GoalsDim(BaseModel):
    short_term_goal: str = ""
    long_term_goal: str = ""
    motivation: str = ""
    memory_debt_clearance_target: str = ""  # world-specific
    memory_asset_accumulation_goal: str = ""  # world-specific
    identity_recovery_goal: str = ""  # world-specific
    archive_access_goal: str = ""  # world-specific
    institutional_reform_intention: str = ""  # world-specific
    escape_from_debt_slavery_plan: str = ""  # world-specific
    resistance_involvement_goal: str = ""  # world-specific


class KnowledgeGroup(BaseModel):
    world_knowledge: list[str] = []
    social_knowledge: list[str] = []


class MemoriesDim(BaseModel):
    knowledge: KnowledgeGroup = KnowledgeGroup()
    background_summary: str = ""
    key_events: list[str] = []
    secrets: list[str] = []
    forgotten_memory_fragments: str = ""  # world-specific
    memory_ownership_claims: str = ""  # world-specific
    traded_memory_inventory: str = ""  # world-specific
    illegal_memory_bootlegs: str = ""  # world-specific
    archive_modification_records: str = ""  # world-specific
    authentic_memory_certificates: str = ""  # world-specific
    traumatic_storm_memories: str = ""  # world-specific
    identity_overwrite_incidents: str = ""  # world-specific


class LocationGroup(BaseModel):
    location_id: str = ""


class PositionGroup(BaseModel):
    x: float = 0.0
    y: float = 0.0


class StateDim(BaseModel):
    location: LocationGroup = LocationGroup()
    position: PositionGroup = PositionGroup()
    current_memory_debt_status: str = ""  # world-specific
    memory_supply_in_body: str = ""  # world-specific
    identity_integrity_level: str = ""  # world-specific
    debt_labor_remaining_hours: str = ""  # world-specific
    storm_shelter_proximity: str = ""  # world-specific
    archive_watchlist_flag: str = ""  # world-specific
    black_market_connection_level: str = ""  # world-specific
    resistance_network_contact_status: str = ""  # world-specific


class AgentModel(BaseModel):
    identity: IdentityDim = IdentityDim()
    social_profile: SocialProfileDim = SocialProfileDim()
    capabilities: CapabilitiesDim = CapabilitiesDim()
    personality: PersonalityDim = PersonalityDim()
    goals: GoalsDim = GoalsDim()
    memories: MemoriesDim = MemoriesDim()
    state: StateDim = StateDim()
    visual: str = ""
