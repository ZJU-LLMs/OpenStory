"""Auto-generated Location Pydantic model."""
from pydantic import BaseModel


class IdentityDim(BaseModel):
    id: str = ""
    name: str = ""
    type: str = ""
    description: str = ""
    府第级别: str = ""  # world-specific
    建筑功能: str = ""  # world-specific
    关联文学事件: str = ""  # world-specific
    象征意义: str = ""  # world-specific


class AccessDim(BaseModel):
    permissions: str = ""
    access_level: str = ""
    access_conditions: str = ""
    内外宅属性: str = ""  # world-specific
    等级准入: str = ""  # world-specific
    特殊时段开放: str = ""  # world-specific
    钥匙管理: str = ""  # world-specific


class StateDim(BaseModel):
    current_state: str = ""
    ownership: str = ""
    capacity: int = 0
    维护状况: str = ""  # world-specific
    使用频率: str = ""  # world-specific
    时间线状态: str = ""  # world-specific


class LocationModel(BaseModel):
    identity: IdentityDim = IdentityDim()
    access: AccessDim = AccessDim()
    state: StateDim = StateDim()
    visual: str = ""
