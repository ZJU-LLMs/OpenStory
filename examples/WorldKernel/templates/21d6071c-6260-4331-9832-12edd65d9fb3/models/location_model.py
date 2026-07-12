"""Auto-generated Location Pydantic model."""
from pydantic import BaseModel


class IdentityDim(BaseModel):
    id: str = ""
    name: str = ""
    type: str = ""
    description: str = ""
    archived_memory_capacity: str = ""  # world-specific
    storm_resistance_rating: str = ""  # world-specific
    safety_rating: str = ""  # world-specific
    maintenance_team_size: str = ""  # world-specific
    energy_source: str = ""  # world-specific
    historical_significance: str = ""  # world-specific
    notable_occupants: str = ""  # world-specific


class AccessDim(BaseModel):
    permissions: str = ""
    access_level: str = ""
    access_conditions: str = ""
    entry_min_memory_quota: str = ""  # world-specific
    interior_security_level: str = ""  # world-specific
    visitor_policy_type: str = ""  # world-specific
    memory_detection_system: str = ""  # world-specific
    clearance_override_protocol: str = ""  # world-specific
    biometric_scan_requirements: str = ""  # world-specific


class StateDim(BaseModel):
    current_state: str = ""
    ownership: str = ""
    capacity: int = 0
    current_occupancy_ratio: str = ""  # world-specific
    memory_backlog_volume: str = ""  # world-specific
    structural_integrity_percent: str = ""  # world-specific
    storm_shield_status: str = ""  # world-specific
    atmosphere_pressure_level: str = ""  # world-specific
    quota_allocation_pending: str = ""  # world-specific
    glitch_leak_incidents: str = ""  # world-specific


class LocationModel(BaseModel):
    identity: IdentityDim = IdentityDim()
    access: AccessDim = AccessDim()
    state: StateDim = StateDim()
