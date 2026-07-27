from pydantic import BaseModel, Field
from typing import Optional

class Teacher(BaseModel):
    name: str = Field(..., min_length=1, description="教师姓名")
    department: str = Field(..., min_length=1, description="所属学院/部门")
    title: Optional[str] = Field(None, description="职称")
    email: Optional[str] = Field(None, description="邮箱")
    research_interests: list[str] = Field(default_factory=list, description="研究方向关键词")
