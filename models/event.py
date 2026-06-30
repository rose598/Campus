from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime

class Event(BaseModel):
    title: str = Field(..., min_length=1, description="活动标题")
    event_type: str = Field(..., min_length=1, description="类型：讲座/竞赛/其他")
    date: Optional[datetime] = Field(None, description="举办时间")
    location: Optional[str] = Field(None, description="地点")
    organizer: Optional[str] = Field(None, description="主办方")
    url: Optional[str] = Field(None, description="相关链接")