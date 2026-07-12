"""Auto-generated Location Pydantic model."""
from pydantic import BaseModel


class IdentityDim(BaseModel):
    id: str = ""
    name: str = ""
    type: str = ""
    description: str = ""
    location_function: str = ""  # world-specific
    associated_person: str = ""  # world-specific
    hierarchy_level: str = ""  # world-specific
    faction: str = ""  # world-specific


class AccessDim(BaseModel):
    permissions: str = ""
    access_level: str = ""
    access_conditions: str = ""
    time_restriction: str = ""  # world-specific
    gender_restriction: str = ""  # world-specific
    role_restriction: str = ""  # world-specific
    ceremonial_rule: str = ""  # world-specific
    key_holder: str = ""  # world-specific


class StateDim(BaseModel):
    current_state: str = ""
    ownership: str = ""
    capacity: int = 0
    economic_status: str = ""  # world-specific
    repair_condition: str = ""  # world-specific
    current_activity: str = ""  # world-specific
    occupancy: str = ""  # world-specific
    security_level: str = ""  # world-specific


class LocationModel(BaseModel):
    identity: IdentityDim = IdentityDim()
    access: AccessDim = AccessDim()
    state: StateDim = StateDim()
    visual: str = ""
