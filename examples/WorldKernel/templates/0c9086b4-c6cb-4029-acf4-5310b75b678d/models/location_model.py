"""Auto-generated Location Pydantic model."""
from pydantic import BaseModel


class IdentityDim(BaseModel):
    id: str = ""
    name: str = ""
    type: str = ""
    importance: str = ""
    description: str = ""
    memory_function: str = ""  # world-specific
    social_stratum: str = ""  # world-specific
    institutional_affiliation: str = ""  # world-specific
    unique_memory_resource: str = ""  # world-specific


class AccessDim(BaseModel):
    permissions: str = ""
    access_level: str = ""
    access_conditions: str = ""
    storm_emergency_access: str = ""  # world-specific
    memory_tax_exempt: bool = False  # world-specific
    required_memory_clearance: int = 0  # world-specific
    secret_access_available: bool = False  # world-specific


class StateDim(BaseModel):
    current_state: str = ""
    ownership: str = ""
    capacity: int = 0
    structural_integrity: float = 0.0  # world-specific
    storm_exposure: str = ""  # world-specific
    memory_reserve_volume: int = 0  # world-specific
    energy_status: str = ""  # world-specific
    operational_status: str = ""  # world-specific


class LocationModel(BaseModel):
    identity: IdentityDim = IdentityDim()
    access: AccessDim = AccessDim()
    state: StateDim = StateDim()
    visual: str = ""
