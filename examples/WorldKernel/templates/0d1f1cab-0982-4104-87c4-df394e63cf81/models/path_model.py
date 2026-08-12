"""Auto-generated Path Pydantic model."""
from pydantic import BaseModel


class IdentityDim(BaseModel):
    id: str = ""
    name: str = ""
    type: str = ""
    path_kind: str = ""  # world-specific
    material_structure: str = ""  # world-specific
    maintenance_status: str = ""  # world-specific
    memory_flow_role: str = ""  # world-specific
    signage_system: str = ""  # world-specific
    historical_layer: str = ""  # world-specific


class EndpointsDim(BaseModel):
    from_id: str = ""
    to_id: str = ""
    bidirectional: bool = False
    terminal_gate_type: str = ""  # world-specific
    traffic_control_point: str = ""  # world-specific
    connection_mode: str = ""  # world-specific
    memory_transfer_capacity: str = ""  # world-specific
    emergency_bypass_route: str = ""  # world-specific
    port_security_level: str = ""  # world-specific


class ConditionsDim(BaseModel):
    access_level: str = ""
    danger_level: str = ""
    required_items: str = ""
    storm_clearance_threshold: str = ""  # world-specific
    identity_verification_code: str = ""  # world-specific
    memory_debt_check: str = ""  # world-specific
    contraband_memory_scan: str = ""  # world-specific
    vibration_dampening_status: str = ""  # world-specific
    wind_force_rating: str = ""  # world-specific
    temperature_tolerance: str = ""  # world-specific
    visibility_obscurance_factor: str = ""  # world-specific
    toll_memory_cost: str = ""  # world-specific


class PathModel(BaseModel):
    identity: IdentityDim = IdentityDim()
    endpoints: EndpointsDim = EndpointsDim()
    conditions: ConditionsDim = ConditionsDim()
