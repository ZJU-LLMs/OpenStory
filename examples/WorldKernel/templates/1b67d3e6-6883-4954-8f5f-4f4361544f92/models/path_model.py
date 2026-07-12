"""Auto-generated Path Pydantic model."""
from pydantic import BaseModel


class IdentityDim(BaseModel):
    id: str = ""
    name: str = ""
    type: str = ""
    alias: str = ""  # world-specific
    belongs_to: str = ""  # world-specific
    primary_use: str = ""  # world-specific
    literary_event: str = ""  # world-specific


class EndpointsDim(BaseModel):
    from_id: str = ""
    to_id: str = ""
    bidirectional: bool = False
    is_main_artery: str = ""  # world-specific
    requires_gate: str = ""  # world-specific
    path_type: str = ""  # world-specific
    symbolic_significance: str = ""  # world-specific


class ConditionsDim(BaseModel):
    access_level: str = ""
    danger_level: str = ""
    required_items: str = ""
    needs_announcement: str = ""  # world-specific
    time_restriction: str = ""  # world-specific
    identity_restriction: str = ""  # world-specific
    secret_use_tendency: str = ""  # world-specific


class PathModel(BaseModel):
    identity: IdentityDim = IdentityDim()
    endpoints: EndpointsDim = EndpointsDim()
    conditions: ConditionsDim = ConditionsDim()
