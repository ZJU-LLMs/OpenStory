"""Auto-generated Location Pydantic model."""
from pydantic import BaseModel


class IdentityDim(BaseModel):
    id: str = ""
    name: str = ""
    type: str = ""
    description: str = ""
    energy_shield_level: str = ""  # world-specific
    memory_storage_density: str = ""  # world-specific
    storm_noise_index: str = ""  # world-specific
    is_trading_allowed: str = ""  # world-specific


class AccessDim(BaseModel):
    permissions: str = ""
    access_level: str = ""
    access_conditions: str = ""
    required_credit_rank: str = ""  # world-specific
    allowed_memory_types: str = ""  # world-specific
    requires_authorization_token: str = ""  # world-specific
    social_tier_marker: str = ""  # world-specific


class StateDim(BaseModel):
    current_state: str = ""
    ownership: str = ""
    capacity: int = 0
    energy_shield_percentage: str = ""  # world-specific
    current_occupancy: str = ""  # world-specific
    storm_alert_level: str = ""  # world-specific
    last_maintenance_time: str = ""  # world-specific


class LocationModel(BaseModel):
    identity: IdentityDim = IdentityDim()
    access: AccessDim = AccessDim()
    state: StateDim = StateDim()
    visual: str = ""
