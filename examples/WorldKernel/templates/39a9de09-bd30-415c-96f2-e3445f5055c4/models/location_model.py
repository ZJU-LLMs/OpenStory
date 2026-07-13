"""Auto-generated Location Pydantic model."""
from pydantic import BaseModel


class IdentityDim(BaseModel):
    id: str = ""
    name: str = ""
    type: str = ""
    description: str = ""
    subway_line_affiliation: str = ""  # world-specific
    plant_control_degree: str = ""  # world-specific
    resource_richness: str = ""  # world-specific
    historical_significance: str = ""  # world-specific
    tribe_occupation_status: str = ""  # world-specific


class AccessDim(BaseModel):
    permissions: str = ""
    access_level: str = ""
    access_conditions: str = ""
    required_passport_type: str = ""  # world-specific
    transit_tax_amount: str = ""  # world-specific
    plant_scan_severity: str = ""  # world-specific
    tribe_relation_modifier: str = ""  # world-specific
    time_restriction_schedule: str = ""  # world-specific


class StateDim(BaseModel):
    current_state: str = ""
    ownership: str = ""
    capacity: int = 0
    resource_stock_level: str = ""  # world-specific
    defense_fortification_level: str = ""  # world-specific
    garrison_tribe_name: str = ""  # world-specific
    structural_damage_percentage: str = ""  # world-specific
    plant_coverage_percentage: str = ""  # world-specific


class LocationModel(BaseModel):
    identity: IdentityDim = IdentityDim()
    access: AccessDim = AccessDim()
    state: StateDim = StateDim()
    visual: str = ""
