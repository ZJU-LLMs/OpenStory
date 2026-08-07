"""Auto-generated Agent Pydantic model."""
from pydantic import BaseModel


class IdentityDim(BaseModel):
    id: str = ""
    name: str = ""
    role: str = ""
    house: str = ""  # world-specific
    blood_status: str = ""  # world-specific
    faction_alignment: str = ""  # world-specific
    secret_loyalty: str = ""  # world-specific
    dark_mark_branded: str = ""  # world-specific
    affiliation_conflict: str = ""  # world-specific


class SocialProfileDim(BaseModel):
    group_id: str = ""
    reputation: str = ""
    social_standing: str = ""  # world-specific
    public_perception: str = ""  # world-specific
    connection_to_order_of_phoenix: str = ""  # world-specific
    connection_to_death_eaters: str = ""  # world-specific
    membership_in_dumbledores_army: str = ""  # world-specific
    membership_in_inquisitorial_squad: str = ""  # world-specific


class CapabilitiesDim(BaseModel):
    skills: list[str] = []
    level: str = ""
    weaknesses: str = ""
    primary_magic_discipline: str = ""  # world-specific
    combat_role: str = ""  # world-specific
    dark_arts_proficiency: str = ""  # world-specific
    defensive_magic_proficiency: str = ""  # world-specific
    occlumency_proficiency: str = ""  # world-specific
    animagus_form: str = ""  # world-specific


class PersonalityDim(BaseModel):
    traits: list[str] = []
    values: list[str] = []
    speech_style: str = ""
    courage_level: str = ""  # world-specific
    prejudice_toward_muggleborns: str = ""  # world-specific
    defiance_willingness: str = ""  # world-specific
    trust_in_authority: str = ""  # world-specific
    emotional_resilience: str = ""  # world-specific
    moral_ambiguity: str = ""  # world-specific


class GoalsDim(BaseModel):
    short_term_goal: str = ""
    long_term_goal: str = ""
    motivation: str = ""
    war_objective: str = ""  # world-specific
    personal_quest: str = ""  # world-specific
    survival_priority: str = ""  # world-specific
    loyalty_goal: str = ""  # world-specific
    power_ambition: str = ""  # world-specific


class KnowledgeGroup(BaseModel):
    world_knowledge: list[str] = []
    social_knowledge: list[str] = []


class MemoriesDim(BaseModel):
    knowledge: KnowledgeGroup = KnowledgeGroup()
    background_summary: str = ""
    key_events: list[str] = []
    secrets: list[str] = []
    traumatic_memories: str = ""  # world-specific
    first_war_experiences: str = ""  # world-specific
    witnessed_deaths: str = ""  # world-specific
    false_memories: str = ""  # world-specific
    suppressed_memories: str = ""  # world-specific
    prophetic_visions: str = ""  # world-specific


class LocationGroup(BaseModel):
    location_id: str = ""


class PositionGroup(BaseModel):
    x: float = 0.0
    y: float = 0.0


class StateDim(BaseModel):
    location: LocationGroup = LocationGroup()
    position: PositionGroup = PositionGroup()
    current_health: str = ""  # world-specific
    magic_reserves: str = ""  # world-specific
    emotional_stability: str = ""  # world-specific
    captivity_status: str = ""  # world-specific
    disguise_active: str = ""  # world-specific
    surveillance_level: str = ""  # world-specific


class AgentModel(BaseModel):
    identity: IdentityDim = IdentityDim()
    social_profile: SocialProfileDim = SocialProfileDim()
    capabilities: CapabilitiesDim = CapabilitiesDim()
    personality: PersonalityDim = PersonalityDim()
    goals: GoalsDim = GoalsDim()
    memories: MemoriesDim = MemoriesDim()
    state: StateDim = StateDim()
    visual: str = ""
