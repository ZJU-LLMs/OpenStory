"""Auto-generated Agent Pydantic model."""
from pydantic import BaseModel


class IdentityDim(BaseModel):
    id: str = ""
    name: str = ""
    role: str = ""
    family_branch: str = ""  # world-specific
    generation: str = ""  # world-specific
    peerage_rank: str = ""  # world-specific
    origination_type: str = ""  # world-specific
    status_hierarchy: str = ""  # world-specific
    lineage_position: str = ""  # world-specific
    marital_status: str = ""  # world-specific
    clan_membership: str = ""  # world-specific
    room_assignment: str = ""  # world-specific


class SocialProfileDim(BaseModel):
    group_id: str = ""
    reputation: str = ""
    social_circle_tags: str = ""  # world-specific
    intimate_coterie: str = ""  # world-specific
    faction_alignment: str = ""  # world-specific
    gossip_status: str = ""  # world-specific
    matriarchal_favor: str = ""  # world-specific
    peer_regard: str = ""  # world-specific
    servant_relationship: str = ""  # world-specific
    external_connection: str = ""  # world-specific
    marriage_prospect_rank: str = ""  # world-specific


class CapabilitiesDim(BaseModel):
    skills: list[str] = []
    level: str = ""
    weaknesses: str = ""
    poetry_skill: str = ""  # world-specific
    household_management: str = ""  # world-specific
    embroidery_proficiency: str = ""  # world-specific
    medical_knowledge: str = ""  # world-specific
    budget_handling: str = ""  # world-specific
    forbidden_knowledge: str = ""  # world-specific
    social_manipulation: str = ""  # world-specific
    calligraphy_level: str = ""  # world-specific
    musical_talent: str = ""  # world-specific


class PersonalityDim(BaseModel):
    traits: list[str] = []
    values: list[str] = []
    speech_style: str = ""
    judgement_verse: str = ""  # world-specific
    prophetic_hint: str = ""  # world-specific
    fate_omin: str = ""  # world-specific
    moral_code: str = ""  # world-specific
    attitude_towards_ritual: str = ""  # world-specific
    intellectual_temper: str = ""  # world-specific
    emotional_lean: str = ""  # world-specific
    secrecy_level: str = ""  # world-specific
    ambition_type: str = ""  # world-specific


class GoalsDim(BaseModel):
    short_term_goal: str = ""
    long_term_goal: str = ""
    motivation: str = ""
    underlying_wish: str = ""  # world-specific
    fatalistic_push: str = ""  # world-specific
    concealed_ambition: str = ""  # world-specific
    relationship_pursuit: str = ""  # world-specific
    survival_strategy: str = ""  # world-specific
    honor_restoration: str = ""  # world-specific
    rebellion_impulse: str = ""  # world-specific
    legacy_concern: str = ""  # world-specific


class KnowledgeGroup(BaseModel):
    world_knowledge: list[str] = []
    social_knowledge: list[str] = []


class MemoriesDim(BaseModel):
    knowledge: KnowledgeGroup = KnowledgeGroup()
    background_summary: str = ""
    key_events: list[str] = []
    secrets: list[str] = []
    hidden_family_secret: str = ""  # world-specific
    childhood_trauma: str = ""  # world-specific
    dream_omen: str = ""  # world-specific
    taboo_knowledge: str = ""  # world-specific
    previous_life_hint: str = ""  # world-specific
    transgressive_encounter: str = ""  # world-specific
    unwritten_rule_understanding: str = ""  # world-specific
    ancestral_story: str = ""  # world-specific
    lost_letter_content: str = ""  # world-specific


class LocationGroup(BaseModel):
    location_id: str = ""


class PositionGroup(BaseModel):
    x: float = 0.0
    y: float = 0.0


class StateDim(BaseModel):
    location: LocationGroup = LocationGroup()
    position: PositionGroup = PositionGroup()
    current_health_status: str = ""  # world-specific
    emotional_condition: str = ""  # world-specific
    financial_state: str = ""  # world-specific
    assigned_courtyard: str = ""  # world-specific
    current_activity: str = ""  # world-specific
    attendance_duty: str = ""  # world-specific
    seclusion_status: str = ""  # world-specific
    punishment_or_reward: str = ""  # world-specific
    time_period_indicator: str = ""  # world-specific


class AgentModel(BaseModel):
    identity: IdentityDim = IdentityDim()
    social_profile: SocialProfileDim = SocialProfileDim()
    capabilities: CapabilitiesDim = CapabilitiesDim()
    personality: PersonalityDim = PersonalityDim()
    goals: GoalsDim = GoalsDim()
    memories: MemoriesDim = MemoriesDim()
    state: StateDim = StateDim()
    visual: str = ""
