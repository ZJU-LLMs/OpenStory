"""Auto-generated Location Pydantic model."""
from pydantic import BaseModel


class IdentityDim(BaseModel):
    id: str = ""
    name: str = ""
    type: str = ""
    description: str = ""
    belongs_to_zone: str = ""  # world-specific
    architectural_style: str = ""  # world-specific
    prominence_rank: str = ""  # world-specific
    primary_function: str = ""  # world-specific
    owner_or_occupant: str = ""  # world-specific


class AccessDim(BaseModel):
    permissions: str = ""
    access_level: str = ""
    access_conditions: str = ""
    gender_restriction: str = ""  # world-specific
    servant_permission: str = ""  # world-specific
    special_event_access: str = ""  # world-specific
    guest_admission_rules: str = ""  # world-specific


class StateDim(BaseModel):
    current_state: str = ""
    ownership: str = ""
    capacity: int = 0
    spatial_layout: str = ""  # world-specific
    maintenance_level: str = ""  # world-specific
    usage_status: str = ""  # world-specific
    seasonal_variation: str = ""  # world-specific
    event_temporary_state: str = ""  # world-specific


class LocationModel(BaseModel):
    identity: IdentityDim = IdentityDim()
    access: AccessDim = AccessDim()
    state: StateDim = StateDim()
    visual: str = ""
