"""Auto-generated Agent Pydantic model."""
from pydantic import BaseModel


class IdentityDim(BaseModel):
    id: str = ""
    name: str = ""
    role: str = ""
    house: str = ""  # world-specific
    allegiance_surface: str = ""  # world-specific
    allegiance_actual: str = ""  # world-specific
    hidden_role: str = ""  # world-specific


class SocialProfileDim(BaseModel):
    group_id: str = ""
    reputation: str = ""
    faction: str = ""  # world-specific
    resistance_network_member: str = ""  # world-specific
    trustworthiness_score: str = ""  # world-specific


class CapabilitiesDim(BaseModel):
    skills: list[str] = []
    level: str = ""
    weaknesses: str = ""
    occlumency_level: str = ""  # world-specific
    legilimency_level: str = ""  # world-specific
    specialized_magic: str = ""  # world-specific
    wand_core: str = ""  # world-specific
    animagus_form: str = ""  # world-specific


class PersonalityDim(BaseModel):
    traits: list[str] = []
    values: list[str] = []
    speech_style: str = ""
    fear_level: str = ""  # world-specific
    defiance_level: str = ""  # world-specific
    moral_grey_degree: str = ""  # world-specific
    paranoia_index: str = ""  # world-specific


class GoalsDim(BaseModel):
    short_term_goal: str = ""
    long_term_goal: str = ""
    motivation: str = ""
    survival_priority: str = ""  # world-specific
    secret_mission: str = ""  # world-specific
    sacrifice_willingness: str = ""  # world-specific


class KnowledgeGroup(BaseModel):
    world_knowledge: list[str] = []
    social_knowledge: list[str] = []


class MemoriesDim(BaseModel):
    knowledge: KnowledgeGroup = KnowledgeGroup()
    background_summary: str = ""
    key_events: list[str] = []
    secrets: list[str] = []
    traumatic_events: str = ""  # world-specific
    known_secret_passages: str = ""  # world-specific
    knowledge_of_forbidden_spells: str = ""  # world-specific
    witnessed_crimes: str = ""  # world-specific


class LocationGroup(BaseModel):
    location_id: str = ""


class PositionGroup(BaseModel):
    x: float = 0.0
    y: float = 0.0


class StateDim(BaseModel):
    location: LocationGroup = LocationGroup()
    position: PositionGroup = PositionGroup()
    hidden_status: str = ""  # world-specific
    safety_level: str = ""  # world-specific
    last_seen_location: str = ""  # world-specific
    disguise_active: str = ""  # world-specific


class AgentModel(BaseModel):
    identity: IdentityDim = IdentityDim()
    social_profile: SocialProfileDim = SocialProfileDim()
    capabilities: CapabilitiesDim = CapabilitiesDim()
    personality: PersonalityDim = PersonalityDim()
    goals: GoalsDim = GoalsDim()
    memories: MemoriesDim = MemoriesDim()
    state: StateDim = StateDim()
    visual: str = ""
