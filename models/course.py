from pydantic import BaseModel, Field
from typing import List, Literal, Optional

class Course(BaseModel):
    name: str = Field(..., min_length=1, max_length=100, description="课程名称")
    code: str = Field(..., pattern=r"^[A-Z]*\.?\d{2,5}$", description="课程代码，如 CS2101")
    credits: float = Field(..., ge=0.5, le=30, description="学分")
    prerequisites: List[str] = Field(default_factory=list, description="先修课程代码列表")
    semester: Literal["春季", "秋季", "夏季"] = Field(..., description="开课学期")
    teacher: str = Field(..., min_length=1, description="授课教师姓名")
    description: Optional[str] = Field(None, description="课程简介")
