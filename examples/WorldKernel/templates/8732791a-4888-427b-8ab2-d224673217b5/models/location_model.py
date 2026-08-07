"""Auto-generated Location Pydantic model."""
from pydantic import BaseModel


class IdentityDim(BaseModel):
    id: str = ""
    name: str = ""
    type: str = ""
    description: str = ""
    archive_designation: str = ""  # world-specific
    construction_storm_cycle: str = ""  # world-specific
    administrative_district: str = ""  # world-specific
    function_tags: str = ""  # world-specific
    historical_event_markers: str = ""  # world-specific


class AccessDim(BaseModel):
    permissions: str = ""
    access_level: str = ""
    access_conditions: str = ""
    security_clearance_level: str = ""  # world-specific
    memory_access_rights: str = ""  # world-specific
    time_restricted_entry: str = ""  # world-specific
    credit_score_requirement: str = ""  # world-specific
    special_pass_requirements: str = ""  # world-specific


class StateDim(BaseModel):
    current_state: str = ""
    ownership: str = ""
    capacity: int = 0
    storm_protection_rating: str = ""  # world-specific
    infrastructure_integrity: str = ""  # world-specific
    stored_memory_volume: str = ""  # world-specific
    energy_supply_status: str = ""  # world-specific
    occupancy_density: str = ""  # world-specific


class LocationModel(BaseModel):
    identity: IdentityDim = IdentityDim()
    access: AccessDim = AccessDim()
    state: StateDim = StateDim()
    visual: str = ""
