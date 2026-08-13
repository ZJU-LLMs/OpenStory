"""Auto-generated Location Pydantic model."""
from pydantic import BaseModel


class IdentityDim(BaseModel):
    id: str = ""
    name: str = ""
    type: str = ""
    description: str = ""
    celestial_domain: str = ""  # world-specific
    affiliation: str = ""  # world-specific
    mythological_significance: str = ""  # world-specific
    spiritual_level: str = ""  # world-specific


class AccessDim(BaseModel):
    permissions: str = ""
    access_level: str = ""
    access_conditions: str = ""
    entry_token: str = ""  # world-specific
    guardians: str = ""  # world-specific
    restriction_level: int = 0  # world-specific
    alignment_requirement: str = ""  # world-specific


class StateDim(BaseModel):
    current_state: str = ""
    ownership: str = ""
    capacity: int = 0
    spiritual_energy: str = ""  # world-specific
    current_event: str = ""  # world-specific
    celestial_weather: str = ""  # world-specific
    danger_level: int = 0  # world-specific


class LocationModel(BaseModel):
    identity: IdentityDim = IdentityDim()
    access: AccessDim = AccessDim()
    state: StateDim = StateDim()
    visual: str = ""
