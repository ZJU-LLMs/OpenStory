"""Auto-generated Location Pydantic model."""
from pydantic import BaseModel


class IdentityDim(BaseModel):
    id: str = ""
    name: str = ""
    type: str = ""
    description: str = ""
    magical_signature: str = ""  # world-specific
    historical_importance: str = ""  # world-specific
    house_affiliation: str = ""  # world-specific
    hidden_bounds: str = ""  # world-specific


class AccessDim(BaseModel):
    permissions: str = ""
    access_level: str = ""
    access_conditions: str = ""
    password_policy: str = ""  # world-specific
    surveillance_intensity: str = ""  # world-specific
    magical_warding: str = ""  # world-specific
    creature_access: str = ""  # world-specific


class StateDim(BaseModel):
    current_state: str = ""
    ownership: str = ""
    capacity: int = 0
    structural_condition: str = ""  # world-specific
    occupying_faction: str = ""  # world-specific
    enchantment_state: str = ""  # world-specific
    inventory_capacity: str = ""  # world-specific


class LocationModel(BaseModel):
    identity: IdentityDim = IdentityDim()
    access: AccessDim = AccessDim()
    state: StateDim = StateDim()
    visual: str = ""
