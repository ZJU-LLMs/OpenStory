"""Auto-generated Location Pydantic model."""
from pydantic import BaseModel


class IdentityDim(BaseModel):
    id: str = ""
    name: str = ""
    type: str = ""
    description: str = ""
    castle_area: str = ""  # world-specific
    security_level: str = ""  # world-specific
    resident_characters: str = ""  # world-specific
    availability_to_students: str = ""  # world-specific
    hidden_elements: str = ""  # world-specific
    is_variable_space: str = ""  # world-specific
    switch_condition: str = ""  # world-specific


class AccessDim(BaseModel):
    permissions: str = ""
    access_level: str = ""
    access_conditions: str = ""
    surveillance_level: str = ""  # world-specific
    magical_barrier: str = ""  # world-specific
    barrier_type: str = ""  # world-specific
    disillusionment_charm: str = ""  # world-specific
    password_required: str = ""  # world-specific
    evasion_methods: str = ""  # world-specific


class StateDim(BaseModel):
    current_state: str = ""
    ownership: str = ""
    capacity: int = 0
    state_description: str = ""  # world-specific
    state_switch_possible: str = ""  # world-specific
    state_switch_condition: str = ""  # world-specific
    maintenance_level: str = ""  # world-specific
    occupied_by_death_eaters: str = ""  # world-specific


class LocationModel(BaseModel):
    identity: IdentityDim = IdentityDim()
    access: AccessDim = AccessDim()
    state: StateDim = StateDim()
    visual: str = ""
