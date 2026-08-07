"""Auto-generated Path Pydantic model."""
from pydantic import BaseModel


class IdentityDim(BaseModel):
    id: str = ""
    name: str = ""
    type: str = ""
    is_secret_passage: str = ""  # world-specific
    current_control_faction: str = ""  # world-specific
    has_portrait_guardian: str = ""  # world-specific
    magical_enhancements: str = ""  # world-specific
    historical_significance: str = ""  # world-specific


class EndpointsDim(BaseModel):
    from_id: str = ""
    to_id: str = ""
    bidirectional: bool = False
    entrance_appearance: str = ""  # world-specific
    exit_appearance: str = ""  # world-specific
    connecting_region: str = ""  # world-specific
    passage_visibility: str = ""  # world-specific
    dynamic_nature: str = ""  # world-specific


class ConditionsDim(BaseModel):
    access_level: str = ""
    danger_level: str = ""
    required_items: str = ""
    password_required: str = ""  # world-specific
    time_restriction: str = ""  # world-specific
    magical_lock_type: str = ""  # world-specific
    surveillance_status: str = ""  # world-specific
    trap_or_alarm: str = ""  # world-specific
    contract_or_oath_required: str = ""  # world-specific


class PathModel(BaseModel):
    identity: IdentityDim = IdentityDim()
    endpoints: EndpointsDim = EndpointsDim()
    conditions: ConditionsDim = ConditionsDim()
