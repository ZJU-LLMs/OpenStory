"""Auto-generated Location Pydantic model."""
from pydantic import BaseModel


class IdentityDim(BaseModel):
    id: str = ""
    name: str = ""
    type: str = ""
    description: str = ""
    memory_archive_sector_code: str = ""  # world-specific
    facility_function_type: str = ""  # world-specific
    administrative_district: str = ""  # world-specific
    historical_memory_event_id: str = ""  # world-specific
    storm_exposure_zone: str = ""  # world-specific


class AccessDim(BaseModel):
    permissions: str = ""
    access_level: str = ""
    access_conditions: str = ""
    minimum_memory_asset_credit: str = ""  # world-specific
    security_clearance_level: str = ""  # world-specific
    storm_alert_access_status: str = ""  # world-specific
    required_identity_certification: str = ""  # world-specific
    debt_labor_pass_requirement: str = ""  # world-specific


class StateDim(BaseModel):
    current_state: str = ""
    ownership: str = ""
    capacity: int = 0
    memory_storage_capacity_used: str = ""  # world-specific
    debt_maintenance_status: str = ""  # world-specific
    storm_damage_level: str = ""  # world-specific
    current_occupancy_ratio: str = ""  # world-specific
    memory_transaction_volume_today: str = ""  # world-specific


class LocationModel(BaseModel):
    identity: IdentityDim = IdentityDim()
    access: AccessDim = AccessDim()
    state: StateDim = StateDim()
    visual: str = ""
