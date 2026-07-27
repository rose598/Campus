from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime

class Event(BaseModel):
    title: str = Field(..., min_length=1, description="活动标题")
    event_type: str = Field(..., min_length=1, description="类型：讲座/竞赛/其他")
    date: Optional[datetime] = Field(None, description="举办时间")
    location: Optional[str] = Field(None, description="地点")
    organizer: Optional[str] = Field(None, description="主办方")
    url: Optional[str] = Field(None, description="相关链接")
    tags: List[str] = Field(default_factory=list, description="活动主题标签，如 ['人工智能','深度学习']")
    related_courses: List[str] = Field(default_factory=list, description="关联课程代码列表，如 ['CS4101']")
