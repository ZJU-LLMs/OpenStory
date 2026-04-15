from typing import Optional
from pydantic import BaseModel, Field


class LongTask(BaseModel):
    """Data structure for long-term tasks"""
    task_description: str = Field(..., description="Task description, including motivation and plan")
    motivation: str = Field(..., description="The driving factor of the task")
    plan: str = Field(..., description="The specific content of the plan")
    created_tick: int = Field(..., description="The tick when the task was created")
    status: str = Field(default="pending", description="Task status: pending, in_progress, completed")

    def to_string(self) -> str:
        """Convert LongTask to a string format"""
        return self.task_description


class BasicAction(BaseModel):
    """Data structure for basic actions"""
    action_type: str = Field(..., description="Action type")
    target: Optional[str] = Field(None, description="Action target")
    content: Optional[str] = Field(None, description="Action content")


class HourlyPlan(BaseModel):
    """Data structure for hourly plans"""
    action: str = Field(..., description="Action description")
    time: int = Field(..., ge=0, le=12, description="Hour, range 0-12")
    target: str = Field(..., description="Action target character, e.g., Jia Baoyu, Lin Daiyu, etc.")
    location: str = Field(..., description="Action location, e.g., Yihong Courtyard, Xiaoxiang Pavilion, etc.")
    importance: int = Field(..., ge=1, le=10, description="Importance score, 1-10, higher score means more important to the plot")

    def to_list(self) -> list:
        """Convert hourly plan to a list format [action, time, target, location, importance]"""
        return [self.action, self.time, self.target, self.location, self.importance]
