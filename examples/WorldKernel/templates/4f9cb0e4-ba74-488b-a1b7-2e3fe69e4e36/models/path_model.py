"""Auto-generated Path Pydantic model."""
from pydantic import BaseModel


class IdentityDim(BaseModel):
    id: str = ""
    name: str = ""
    type: str = ""
    route_number: str = ""  # world-specific
    historical_memory_value: str = ""  # world-specific
    administrative_district: str = ""  # world-specific
    traffic_purpose: str = ""  # world-specific
    encryption_level: str = ""  # world-specific
    monopoly_authority: str = ""  # world-specific


class EndpointsDim(BaseModel):
    from_id: str = ""
    to_id: str = ""
    bidirectional: bool = False
    pressure_differential: str = ""  # world-specific
    transit_time_minutes: str = ""  # world-specific
    endpoint_security_checkpoints: str = ""  # world-specific
    memory_gateway_type: str = ""  # world-specific
    endpoint_jurisdiction: str = ""  # world-specific
    track_connection_type: str = ""  # world-specific


class ConditionsDim(BaseModel):
    access_level: str = ""
    danger_level: str = ""
    required_items: str = ""
    storm_threat_index: str = ""  # world-specific
    airtight_integrity_rating: str = ""  # world-specific
    memory_toll_cost: str = ""  # world-specific
    surveillance_scan_frequency: str = ""  # world-specific
    operating_hours: str = ""  # world-specific
    memory_storage_device_permission: str = ""  # world-specific
    credential_level_required: str = ""  # world-specific
    emergency_seal_status: str = ""  # world-specific


class PathModel(BaseModel):
    identity: IdentityDim = IdentityDim()
    endpoints: EndpointsDim = EndpointsDim()
    conditions: ConditionsDim = ConditionsDim()
