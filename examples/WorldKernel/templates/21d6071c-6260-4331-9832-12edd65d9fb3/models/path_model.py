"""Auto-generated Path Pydantic model."""
from pydantic import BaseModel


class IdentityDim(BaseModel):
    id: str = ""
    name: str = ""
    type: str = ""
    path_name_display: str = ""  # world-specific
    path_subtype: str = ""  # world-specific
    storm_seal_rating: str = ""  # world-specific
    memory_purity_filter_capability: str = ""  # world-specific
    surveillance_level: str = ""  # world-specific


class EndpointsDim(BaseModel):
    from_id: str = ""
    to_id: str = ""
    bidirectional: bool = False
    travel_time_standard: str = ""  # world-specific
    distance_km: str = ""  # world-specific
    requires_memory_card: str = ""  # world-specific
    monitored_by_wardens: str = ""  # world-specific
    is_emergency_route: str = ""  # world-specific
    bi_directional_priority: str = ""  # world-specific


class ConditionsDim(BaseModel):
    access_level: str = ""
    danger_level: str = ""
    required_items: str = ""
    storm_stability_index: str = ""  # world-specific
    memory_contamination_risk: str = ""  # world-specific
    required_pressure_gear: str = ""  # world-specific
    temporary_pass_allowed: str = ""  # world-specific
    evacuation_priority_score: str = ""  # world-specific


class PathModel(BaseModel):
    identity: IdentityDim = IdentityDim()
    endpoints: EndpointsDim = EndpointsDim()
    conditions: ConditionsDim = ConditionsDim()
