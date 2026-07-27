from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import date


class Policy(BaseModel):
    """政策文件模型 —— 保研/转专业/选课/补考等教务政策"""
    doc_id: str = Field(..., pattern=r"^DOC_\d{8}$", description="文档唯一ID")
    title: str = Field(..., min_length=1, max_length=200, description="政策标题")
    content: str = Field(..., min_length=1, description="政策正文内容")
    policy_type: str = Field(..., description="政策类型：保研/转专业/选课/补考/毕业/其他")
    source_url: Optional[str] = Field(None, description="来源URL")
    publish_date: Optional[date] = Field(None, description="发布日期")
    expiry_date: Optional[date] = Field(None, description="失效日期")
    tags: List[str] = Field(default_factory=list, description="关键词标签")
    confidence: float = Field(default=1.0, ge=0.0, le=1.0, description="质量置信度")
