"""Auto-generated Agent Pydantic model."""
from pydantic import BaseModel


class IdentityDim(BaseModel):
    id: str = ""
    name: str = ""
    role: str = ""
    subway_line: str = ""  # world-specific
    tribe_position: str = ""  # world-specific
    origin_zone: str = ""  # world-specific
    special_title: str = ""  # world-specific


class SocialProfileDim(BaseModel):
    group_id: str = ""
    reputation: str = ""
    intra_tribe_rank: str = ""  # world-specific
    inter_tribe_reputation: str = ""  # world-specific
    merchant_credit_rating: str = ""  # world-specific
    allies_list: str = ""  # world-specific


class CapabilitiesDim(BaseModel):
    skills: list[str] = []
    level: str = ""
    weaknesses: str = ""
    survival_skills: str = ""  # world-specific
    plant_interaction_level: str = ""  # world-specific
    resource_control: str = ""  # world-specific
    trading_ability: str = ""  # world-specific


class PersonalityDim(BaseModel):
    traits: list[str] = []
    values: list[str] = []
    speech_style: str = ""
    attitude_toward_plants: str = ""  # world-specific
    tribe_loyalty: str = ""  # world-specific
    risk_taking: str = ""  # world-specific
    trust_in_outsiders: str = ""  # world-specific


class GoalsDim(BaseModel):
    short_term_goal: str = ""
    long_term_goal: str = ""
    motivation: str = ""
    personal_ambition: str = ""  # world-specific
    tribe_objective: str = ""  # world-specific
    plant_research_goal: str = ""  # world-specific
    exploration_target: str = ""  # world-specific


class KnowledgeGroup(BaseModel):
    world_knowledge: list[str] = []
    social_knowledge: list[str] = []


class MemoriesDim(BaseModel):
    knowledge: KnowledgeGroup = KnowledgeGroup()
    background_summary: str = ""
    key_events: list[str] = []
    secrets: list[str] = []
    significant_battles: str = ""  # world-specific
    plant_discoveries: str = ""  # world-specific
    lost_friends: str = ""  # world-specific
    survival_stories: str = ""  # world-specific


class LocationGroup(BaseModel):
    location_id: str = ""


class PositionGroup(BaseModel):
    x: float = 0.0
    y: float = 0.0


class StateDim(BaseModel):
    location: LocationGroup = LocationGroup()
    position: PositionGroup = PositionGroup()
    current_line: str = ""  # world-specific
    hunger_level: str = ""  # world-specific
    plant_exposure_level: str = ""  # world-specific
    is_isolated: str = ""  # world-specific


class AgentModel(BaseModel):
    identity: IdentityDim = IdentityDim()
    social_profile: SocialProfileDim = SocialProfileDim()
    capabilities: CapabilitiesDim = CapabilitiesDim()
    personality: PersonalityDim = PersonalityDim()
    goals: GoalsDim = GoalsDim()
    memories: MemoriesDim = MemoriesDim()
    state: StateDim = StateDim()
    visual: str = ""
