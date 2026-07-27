from pydantic import BaseModel, Field
from typing import Optional

class Lab(BaseModel):
    name: str = Field(..., min_length=1, description="实验室名称")
    director: str = Field(..., min_length=1, description="负责人")
    description: Optional[str] = Field(None, description="实验室简介")
    keywords: list[str] = Field(default_factory=list, description="研究方向标签")# default_factory 确保了每个实例获得一个独立、安全的默认空列表
