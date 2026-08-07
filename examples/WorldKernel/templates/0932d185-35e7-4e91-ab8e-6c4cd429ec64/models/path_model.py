"""Auto-generated Path Pydantic model."""
from pydantic import BaseModel


class IdentityDim(BaseModel):
    id: str = ""
    name: str = ""
    type: str = ""
    path_type: str = ""  # world-specific
    is_official: str = ""  # world-specific
    is_monitored: str = ""  # world-specific
    maintenance_status: str = ""  # world-specific
    is_restricted: str = ""  # world-specific
    is_secret: str = ""  # world-specific


class EndpointsDim(BaseModel):
    from_id: str = ""
    to_id: str = ""
    bidirectional: bool = False
    length_km: str = ""  # world-specific
    travel_time_min: str = ""  # world-specific
    credit_requirement_at_start: str = ""  # world-specific
    credit_requirement_at_end: str = ""  # world-specific
    connection_type: str = ""  # world-specific


class ConditionsDim(BaseModel):
    access_level: str = ""
    danger_level: str = ""
    required_items: str = ""
    credit_threshold: str = ""  # world-specific
    requires_id_card: str = ""  # world-specific
    storm_protocol_active: str = ""  # world-specific
    memory_device_allowed: str = ""  # world-specific
    toll_cost_memories: str = ""  # world-specific
    curfew_restricted: str = ""  # world-specific


class PathModel(BaseModel):
    identity: IdentityDim = IdentityDim()
    endpoints: EndpointsDim = EndpointsDim()
    conditions: ConditionsDim = ConditionsDim()
