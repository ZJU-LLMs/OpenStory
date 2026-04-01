from typing import Optional
from pydantic import BaseModel, Field


class LongTask(BaseModel):
    """长期任务数据结构"""
    task_description: str = Field(..., description="任务描述，包含驱动和计划")
    motivation: str = Field(..., description="任务的驱动因素")
    plan: str = Field(..., description="具体的计划内容")
    created_tick: int = Field(..., description="任务创建的回合数")
    status: str = Field(default="pending", description="任务状态：pending, in_progress, completed")

    def to_string(self) -> str:
        """将 LongTask 转换为字符串格式"""
        return self.task_description


class BasicAction(BaseModel):
    """基础行动数据结构"""
    action_type: str = Field(..., description="行动类型")
    target: Optional[str] = Field(None, description="行动目标")
    content: Optional[str] = Field(None, description="行动内容")


class HourlyPlan(BaseModel):
    """时辰计划数据结构"""
    action: str = Field(..., description="行动描述")
    time: int = Field(..., ge=0, le=12, description="时辰，范围0-12")
    target: str = Field(..., description="行动目标人物，如：贾宝玉、林黛玉等")
    location: str = Field(..., description="行动地点，如：怡红院、潇湘馆等")
    importance: int = Field(..., ge=1, le=10, description="重要性分数，1-10，分数越高对剧情越重要")

    def to_list(self) -> list:
        """将时辰计划转换为列表格式 [action, time, target, location, importance]"""
        return [self.action, self.time, self.target, self.location, self.importance]
