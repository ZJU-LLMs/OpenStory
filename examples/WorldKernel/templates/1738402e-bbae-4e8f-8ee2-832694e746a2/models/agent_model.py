"""Auto-generated Agent Pydantic model."""
from pydantic import BaseModel


class IdentityDim(BaseModel):
    id: str = ""
    name: str = ""
    role: str = ""
    generation: str = ""  # world-specific
    status: str = ""  # world-specific
    economic_role: str = ""  # world-specific
    servant_grade: str = ""  # world-specific
    lineage: str = ""  # world-specific


class SocialProfileDim(BaseModel):
    group_id: str = ""
    reputation: str = ""
    faction: str = ""  # world-specific
    patron: str = ""  # world-specific
    allies: str = ""  # world-specific
    rivals: str = ""  # world-specific


class CapabilitiesDim(BaseModel):
    skills: list[str] = []
    level: str = ""
    weaknesses: str = ""
    domestic_management_skill: str = ""  # world-specific
    literary_skill: str = ""  # world-specific
    financial_acuity: str = ""  # world-specific
    ritual_knowledge: str = ""  # world-specific


class PersonalityDim(BaseModel):
    traits: list[str] = []
    values: list[str] = []
    speech_style: str = ""
    filial_piety_level: str = ""  # world-specific
    ambition: str = ""  # world-specific
    conservativeness: str = ""  # world-specific
    emotion_expressiveness: str = ""  # world-specific


class GoalsDim(BaseModel):
    short_term_goal: str = ""
    long_term_goal: str = ""
    motivation: str = ""
    status_preservation: str = ""  # world-specific
    economic_survival: str = ""  # world-specific
    progeny_continuation: str = ""  # world-specific


class KnowledgeGroup(BaseModel):
    world_knowledge: list[str] = []
    social_knowledge: list[str] = []


class MemoriesDim(BaseModel):
    knowledge: KnowledgeGroup = KnowledgeGroup()
    background_summary: str = ""
    key_events: list[str] = []
    secrets: list[str] = []
    family_history_knowledge: str = ""  # world-specific
    scandal_knowledge: str = ""  # world-specific
    love_affair_secret: str = ""  # world-specific


class LocationGroup(BaseModel):
    location_id: str = ""


class PositionGroup(BaseModel):
    x: float = 0.0
    y: float = 0.0


class StateDim(BaseModel):
    location: LocationGroup = LocationGroup()
    position: PositionGroup = PositionGroup()
    current_location_description: str = ""  # world-specific
    health_condition: str = ""  # world-specific
    age: str = ""  # world-specific


class AgentModel(BaseModel):
    identity: IdentityDim = IdentityDim()
    social_profile: SocialProfileDim = SocialProfileDim()
    capabilities: CapabilitiesDim = CapabilitiesDim()
    personality: PersonalityDim = PersonalityDim()
    goals: GoalsDim = GoalsDim()
    memories: MemoriesDim = MemoriesDim()
    state: StateDim = StateDim()
    visual: str = ""
