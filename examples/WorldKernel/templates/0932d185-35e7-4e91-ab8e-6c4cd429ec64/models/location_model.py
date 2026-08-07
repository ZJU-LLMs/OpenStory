"""Auto-generated Location Pydantic model."""
from pydantic import BaseModel


class IdentityDim(BaseModel):
    id: str = ""
    name: str = ""
    type: str = ""
    description: str = ""
    memory_reserve_capacity: str = ""  # world-specific
    institutional_affiliation: str = ""  # world-specific
    historical_memory_epoch: str = ""  # world-specific
    functional_subtype: str = ""  # world-specific
    symbolic_significance: str = ""  # world-specific
    unique_memory_artifact: str = ""  # world-specific


class AccessDim(BaseModel):
    permissions: str = ""
    access_level: str = ""
    access_conditions: str = ""
    required_credit_score: str = ""  # world-specific
    memory_bond_required: str = ""  # world-specific
    approval_process: str = ""  # world-specific
    storm_safety_clearance: str = ""  # world-specific
    access_time_restriction: str = ""  # world-specific
    identity_verification_level: str = ""  # world-specific


class StateDim(BaseModel):
    current_state: str = ""
    ownership: str = ""
    capacity: int = 0
    memory_reserve_level: str = ""  # world-specific
    operational_status: str = ""  # world-specific
    structural_integrity: str = ""  # world-specific
    emergency_protocol_active: str = ""  # world-specific
    occupation_ratio: str = ""  # world-specific
    last_memory_audit_date: str = ""  # world-specific


class LocationModel(BaseModel):
    identity: IdentityDim = IdentityDim()
    access: AccessDim = AccessDim()
    state: StateDim = StateDim()
    visual: str = ""
