from __future__ import annotations

from typing import Any, Dict, Optional

from pydantic import BaseModel, Field


class IntentParseRequest(BaseModel):
    raw_text: str = Field(..., min_length=1, description="用户输入的自然语言达人需求")
    brand_name: str = Field(default="", description="品牌名")
    spu_name: str = Field(default="", description="SPU 名")


class IntentParseResponse(BaseModel):
    success: bool = True
    intent: Dict[str, Any]


class MatchRetrieveRequest(BaseModel):
    raw_text: str = Field(default="", description="原始自然语言查询")
    brand_name: str = Field(default="", description="品牌名")
    spu_name: str = Field(default="", description="SPU 名")
    intent: Optional[Dict[str, Any]] = Field(default=None, description="已解析好的意图对象，可跳过重复解析")
    top_k: int = Field(default=20, ge=1, le=200, description="返回数量")
    vector_field: str = Field(default="v_overall_style", description="Milvus 检索向量字段")
    experiment_mode: str = Field(default="long_sentence", description="查询向量构造模式")
    tag_weights: Dict[str, float] = Field(default_factory=dict, description="字段标签权重")
    scalar_filters: Dict[str, Any] = Field(default_factory=dict, description="额外的标量过滤条件")
    use_cache: bool = Field(default=True, description="是否启用检索缓存")


class MatchRetrieveResponse(BaseModel):
    success: bool = True
    task_id: str
    status: str
    result: Dict[str, Any]


class TaskStatusResponse(BaseModel):
    success: bool = True
    task: Dict[str, Any]
