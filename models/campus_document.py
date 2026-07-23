from pydantic import BaseModel, Field
from typing import Literal, Optional, List
from datetime import date

class CampusDocument(BaseModel):
    doc_id: str = Field(..., pattern=r"^DOC_\d{8}$", description="文档唯一ID")
    category: Literal["academic", "life", "course"] = Field(..., description="分类：教务/生活/课程")
    title: str = Field(..., min_length=1, max_length=200, description="文档标题")
    content: str = Field(..., min_length=1, description="原始文本内容")
    source_url: Optional[str] = Field(None, description="来源URL")
    publish_date: Optional[date] = Field(None, description="发布日期")
    expiry_date: Optional[date] = Field(None, description="失效日期")
    tags: List[str] = Field(default_factory=list, description="关键词标签")
    confidence: float = Field(default=1.0, ge=0.0, le=1.0, description="质量置信度")

class Chunk(BaseModel):
    chunk_id: str = Field(..., pattern=r"^CHK_\d{6}$", description="分块唯一ID")
    doc_id: str = Field(..., pattern=r"^DOC_\d{8}$", description="所属文档ID")
    content: str = Field(..., min_length=1, description="分块文本")
    parent_headings: List[str] = Field(default_factory=list, description="父级标题链")
    position: int = Field(..., ge=0, description="在原文档中的顺序位置")