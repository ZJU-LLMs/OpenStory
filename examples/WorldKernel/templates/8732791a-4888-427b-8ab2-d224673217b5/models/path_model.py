"""Auto-generated Path Pydantic model."""
from pydantic import BaseModel


class IdentityDim(BaseModel):
    id: str = ""
    name: str = ""
    type: str = ""
    storm_exposure_level: str = ""  # world-specific
    construction_material: str = ""  # world-specific
    maintenance_status: str = ""  # world-specific
    historical_significance: str = ""  # world-specific
    covert_route_flag: str = ""  # world-specific


class EndpointsDim(BaseModel):
    from_id: str = ""
    to_id: str = ""
    bidirectional: bool = False
    checkpoint_count: str = ""  # world-specific
    security_sweep_frequency: str = ""  # world-specific
    traffic_capacity: str = ""  # world-specific
    alternate_route_links: str = ""  # world-specific
    memory_flow_pipeline: str = ""  # world-specific
    vulnerability_to_sabotage: str = ""  # world-specific


class ConditionsDim(BaseModel):
    access_level: str = ""
    danger_level: str = ""
    required_items: str = ""
    memory_toll_required: str = ""  # world-specific
    credit_rating_threshold: str = ""  # world-specific
    storm_alert_restriction: str = ""  # world-specific
    emergency_protocol_level: str = ""  # world-specific
    inspection_requirements: str = ""  # world-specific
    black_market_access_flag: str = ""  # world-specific


class PathModel(BaseModel):
    identity: IdentityDim = IdentityDim()
    endpoints: EndpointsDim = EndpointsDim()
    conditions: ConditionsDim = ConditionsDim()
