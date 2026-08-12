"""Auto-generated Path Pydantic model."""
from pydantic import BaseModel


class IdentityDim(BaseModel):
    id: str = ""
    name: str = ""
    type: str = ""
    path_kind: str = ""  # world-specific
    landscape_desc: str = ""  # world-specific
    is_hidden: bool = False  # world-specific
    spiritual_aura: str = ""  # world-specific


class EndpointsDim(BaseModel):
    from_id: str = ""
    to_id: str = ""
    bidirectional: bool = False
    traversal_time: str = ""  # world-specific
    spatial_layer: str = ""  # world-specific
    requires_teleport: bool = False  # world-specific
    waypoint_names: list[str] = []  # world-specific


class ConditionsDim(BaseModel):
    access_level: str = ""
    danger_level: str = ""
    required_items: str = ""
    guard_entities: list[str] = []  # world-specific
    time_restriction: str = ""  # world-specific
    special_condition_desc: str = ""  # world-specific
    access_restricted_by: str = ""  # world-specific


class PathModel(BaseModel):
    identity: IdentityDim = IdentityDim()
    endpoints: EndpointsDim = EndpointsDim()
    conditions: ConditionsDim = ConditionsDim()
