"""Auto-generated Path Pydantic model."""
from pydantic import BaseModel


class IdentityDim(BaseModel):
    id: str = ""
    name: str = ""
    type: str = ""
    belongs_to_compound: str = ""  # world-specific
    is_inner_outer_transition: str = ""  # world-specific
    is_daily_use: str = ""  # world-specific
    has_name_story: str = ""  # world-specific
    night_closing: str = ""  # world-specific
    guarded: str = ""  # world-specific


class EndpointsDim(BaseModel):
    from_id: str = ""
    to_id: str = ""
    bidirectional: bool = False
    has_gate_type: str = ""  # world-specific
    has_steps: str = ""  # world-specific
    has_screen_wall: str = ""  # world-specific
    allows_palanquin: str = ""  # world-specific
    gender_restriction: str = ""  # world-specific


class ConditionsDim(BaseModel):
    access_level: str = ""
    danger_level: str = ""
    required_items: str = ""
    requires_announcement: str = ""  # world-specific
    time_access: str = ""  # world-specific
    requires_token: str = ""  # world-specific
    requires_maid_accompany: str = ""  # world-specific
    has_night_watch: str = ""  # world-specific
    weather_affected: str = ""  # world-specific
    lighting: str = ""  # world-specific


class PathModel(BaseModel):
    identity: IdentityDim = IdentityDim()
    endpoints: EndpointsDim = EndpointsDim()
    conditions: ConditionsDim = ConditionsDim()
