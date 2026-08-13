"""Auto-generated Path Pydantic model."""
from pydantic import BaseModel


class IdentityDim(BaseModel):
    id: str = ""
    name: str = ""
    type: str = ""
    route_code: str = ""  # world-specific
    architecture_style: str = ""  # world-specific
    visual_ambience: str = ""  # world-specific
    traffic_priority: str = ""  # world-specific
    memory_role: str = ""  # world-specific


class EndpointsDim(BaseModel):
    from_id: str = ""
    to_id: str = ""
    bidirectional: bool = False
    transit_time_minutes: float = 0.0  # world-specific
    elevation_change: float = 0.0  # world-specific
    security_gradient: str = ""  # world-specific
    connection_type: str = ""  # world-specific
    carries_live_memory: bool = False  # world-specific


class ConditionsDim(BaseModel):
    access_level: str = ""
    danger_level: str = ""
    required_items: str = ""
    requires_memory_toll: float = 0.0  # world-specific
    storm_rating: int = 0  # world-specific
    identity_scan: bool = False  # world-specific
    patrol_interval: str = ""  # world-specific
    isolation_mode: str = ""  # world-specific
    black_market_route: bool = False  # world-specific


class PathModel(BaseModel):
    identity: IdentityDim = IdentityDim()
    endpoints: EndpointsDim = EndpointsDim()
    conditions: ConditionsDim = ConditionsDim()
