"""Auto-generated Path Pydantic model."""
from pydantic import BaseModel


class IdentityDim(BaseModel):
    id: str = ""
    name: str = ""
    type: str = ""
    path_type: str = ""  # world-specific
    name_meaning: str = ""  # world-specific
    decoration: str = ""  # world-specific
    significance: str = ""  # world-specific


class EndpointsDim(BaseModel):
    from_id: str = ""
    to_id: str = ""
    bidirectional: bool = False
    is_public: str = ""  # world-specific
    length_steps: str = ""  # world-specific
    barriers: str = ""  # world-specific
    guards: str = ""  # world-specific
    seasonal_use: str = ""  # world-specific
    direction: str = ""  # world-specific
    visibility: str = ""  # world-specific


class ConditionsDim(BaseModel):
    access_level: str = ""
    danger_level: str = ""
    required_items: str = ""
    time_restrictions: str = ""  # world-specific
    gender_restriction: str = ""  # world-specific
    special_event_rules: str = ""  # world-specific
    maintenance_state: str = ""  # world-specific
    traffic_volume: str = ""  # world-specific


class PathModel(BaseModel):
    identity: IdentityDim = IdentityDim()
    endpoints: EndpointsDim = EndpointsDim()
    conditions: ConditionsDim = ConditionsDim()
