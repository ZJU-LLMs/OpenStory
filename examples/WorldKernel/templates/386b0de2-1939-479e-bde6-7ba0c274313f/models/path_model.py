"""Auto-generated Path Pydantic model."""
from pydantic import BaseModel


class IdentityDim(BaseModel):
    id: str = ""
    name: str = ""
    type: str = ""
    energy_shield_level: str = ""  # world-specific
    storm_noise_index: str = ""  # world-specific
    memory_traffic_volume: str = ""  # world-specific
    passage_security_level: str = ""  # world-specific


class EndpointsDim(BaseModel):
    from_id: str = ""
    to_id: str = ""
    bidirectional: bool = False
    connected_zone_heights: str = ""  # world-specific
    memory_flow_permitted: str = ""  # world-specific
    passage_class_restriction: str = ""  # world-specific
    black_market_access: str = ""  # world-specific


class ConditionsDim(BaseModel):
    access_level: str = ""
    danger_level: str = ""
    required_items: str = ""
    memory_toll_required: str = ""  # world-specific
    storm_safe_interval: str = ""  # world-specific
    permit_expiration: str = ""  # world-specific
    memory_erasure_risk: str = ""  # world-specific


class PathModel(BaseModel):
    identity: IdentityDim = IdentityDim()
    endpoints: EndpointsDim = EndpointsDim()
    conditions: ConditionsDim = ConditionsDim()
