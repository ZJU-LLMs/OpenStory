"""Auto-generated Agent Pydantic model."""
from pydantic import BaseModel


class IdentityDim(BaseModel):
    id: str = ""
    name: str = ""
    role: str = ""
    age: str = ""  # world-specific
    generation: str = ""  # world-specific
    gender: str = ""  # world-specific
    rank: str = ""  # world-specific
    relationship_to_jia: str = ""  # world-specific
    residence: str = ""  # world-specific
    fate_hint: str = ""  # world-specific


class SocialProfileDim(BaseModel):
    group_id: str = ""
    reputation: str = ""
    social_network: str = ""  # world-specific
    standing_in_family: str = ""  # world-specific
    popularity: str = ""  # world-specific


class CapabilitiesDim(BaseModel):
    skills: list[str] = []
    level: str = ""
    weaknesses: str = ""
    special_skills: str = ""  # world-specific
    education: str = ""  # world-specific
    economic_resources: str = ""  # world-specific


class PersonalityDim(BaseModel):
    traits: list[str] = []
    values: list[str] = []
    speech_style: str = ""
    behavior_pattern: str = ""  # world-specific
    emotional_tendency: str = ""  # world-specific
    social_style: str = ""  # world-specific


class GoalsDim(BaseModel):
    short_term_goal: str = ""
    long_term_goal: str = ""
    motivation: str = ""
    immediate_wish: str = ""  # world-specific
    long_term_ambition: str = ""  # world-specific
    conflict_goal: str = ""  # world-specific


class KnowledgeGroup(BaseModel):
    world_knowledge: list[str] = []
    social_knowledge: list[str] = []


class MemoriesDim(BaseModel):
    knowledge: KnowledgeGroup = KnowledgeGroup()
    background_summary: str = ""
    key_events: list[str] = []
    secrets: list[str] = []
    childhood_experience: str = ""  # world-specific
    important_impressions: str = ""  # world-specific
    hidden_memories: str = ""  # world-specific


class LocationGroup(BaseModel):
    location_id: str = ""


class PositionGroup(BaseModel):
    x: float = 0.0
    y: float = 0.0


class StateDim(BaseModel):
    location: LocationGroup = LocationGroup()
    position: PositionGroup = PositionGroup()
    current_activity: str = ""  # world-specific
    health_status: str = ""  # world-specific
    mood: str = ""  # world-specific


class AgentModel(BaseModel):
    identity: IdentityDim = IdentityDim()
    social_profile: SocialProfileDim = SocialProfileDim()
    capabilities: CapabilitiesDim = CapabilitiesDim()
    personality: PersonalityDim = PersonalityDim()
    goals: GoalsDim = GoalsDim()
    memories: MemoriesDim = MemoriesDim()
    state: StateDim = StateDim()
    visual: str = ""
