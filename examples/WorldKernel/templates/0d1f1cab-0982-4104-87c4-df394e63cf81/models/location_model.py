"""Auto-generated Location Pydantic model."""
from pydantic import BaseModel


class IdentityDim(BaseModel):
    id: str = ""
    name: str = ""
    type: str = ""
    description: str = ""
    memory_flow_role: str = ""  # world-specific
    storm_exposure_level: str = ""  # world-specific
    security_zone: str = ""  # world-specific
    district_function: str = ""  # world-specific
    narrative_event_entry: str = ""  # world-specific


class AccessDim(BaseModel):
    permissions: str = ""
    access_level: str = ""
    access_conditions: str = ""
    identity_verification_required: str = ""  # world-specific
    memory_collateral_required: str = ""  # world-specific
    approval_chain: str = ""  # world-specific
    secrecy_tier: str = ""  # world-specific
    black_market_penetration: str = ""  # world-specific
    visitation_quota: str = ""  # world-specific


class StateDim(BaseModel):
    current_state: str = ""
    ownership: str = ""
    capacity: int = 0
    structural_integrity: str = ""  # world-specific
    shield_status: str = ""  # world-specific
    energy_supply_level: str = ""  # world-specific
    maintenance_urgency: str = ""  # world-specific
    storm_readiness: str = ""  # world-specific
    occupancy_pressure: str = ""  # world-specific


class LocationModel(BaseModel):
    identity: IdentityDim = IdentityDim()
    access: AccessDim = AccessDim()
    state: StateDim = StateDim()
    visual: str = ""
