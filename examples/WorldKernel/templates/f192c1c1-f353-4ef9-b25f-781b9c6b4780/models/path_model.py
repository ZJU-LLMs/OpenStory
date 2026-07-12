"""Auto-generated Path Pydantic model."""
from pydantic import BaseModel


class IdentityDim(BaseModel):
    id: str = ""
    name: str = ""
    type: str = ""
    alias: str = ""  # world-specific
    magical_signature: str = ""  # world-specific
    is_secret: str = ""  # world-specific
    is_known_to_death_eaters: str = ""  # world-specific
    requires_passphrase: str = ""  # world-specific
    inventory_item_required: str = ""  # world-specific


class EndpointsDim(BaseModel):
    from_id: str = ""
    to_id: str = ""
    bidirectional: bool = False
    from_room_security_level: str = ""  # world-specific
    to_room_security_level: str = ""  # world-specific
    start_has_hidden_entrance: str = ""  # world-specific
    end_has_hidden_entrance: str = ""  # world-specific
    time_restriction: str = ""  # world-specific
    is_one_way: str = ""  # world-specific
    magical_interference: str = ""  # world-specific


class ConditionsDim(BaseModel):
    access_level: str = ""
    danger_level: str = ""
    required_items: str = ""
    password_required: str = ""  # world-specific
    countercurse_required: str = ""  # world-specific
    invisibility_required: str = ""  # world-specific
    anti_disapparition: str = ""  # world-specific
    patrolled_by_filch: str = ""  # world-specific
    monitored_by_carrows: str = ""  # world-specific
    blocked_by_dark_magic: str = ""  # world-specific
    alternative_route_available: str = ""  # world-specific


class PathModel(BaseModel):
    identity: IdentityDim = IdentityDim()
    endpoints: EndpointsDim = EndpointsDim()
    conditions: ConditionsDim = ConditionsDim()
