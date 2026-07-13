"""Auto-generated Path Pydantic model."""
from pydantic import BaseModel


class IdentityDim(BaseModel):
    id: str = ""
    name: str = ""
    type: str = ""
    affiliated_line_or_tribe: str = ""  # world-specific
    channel_type: str = ""  # world-specific
    plant_encroachment_level: str = ""  # world-specific
    is_arterial_passage: str = ""  # world-specific
    structural_integrity_status: str = ""  # world-specific


class EndpointsDim(BaseModel):
    from_id: str = ""
    to_id: str = ""
    bidirectional: bool = False
    from_tribe_control: str = ""  # world-specific
    to_tribe_control: str = ""  # world-specific
    from_plant_activity_index: str = ""  # world-specific
    to_plant_activity_index: str = ""  # world-specific
    from_resource_richness: str = ""  # world-specific
    to_resource_richness: str = ""  # world-specific


class ConditionsDim(BaseModel):
    access_level: str = ""
    danger_level: str = ""
    required_items: str = ""
    required_tribe_document: str = ""  # world-specific
    plant_scan_required: str = ""  # world-specific
    allowed_operating_hours: str = ""  # world-specific
    armed_escort_mandatory: str = ""  # world-specific
    contamination_level_threshold: str = ""  # world-specific
    diplomatic_status_penalty: str = ""  # world-specific


class PathModel(BaseModel):
    identity: IdentityDim = IdentityDim()
    endpoints: EndpointsDim = EndpointsDim()
    conditions: ConditionsDim = ConditionsDim()
