from __future__ import annotations

from typing import Any, Dict, List, Optional

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
    campaign_id: Optional[int] = Field(default=None, description="可选：项目 ID，用于融合动态意图向量")
    intent: Optional[Dict[str, Any]] = Field(default=None, description="已解析好的意图对象，可跳过重复解析")
    top_k: int = Field(default=20, ge=1, le=200, description="目标返回数量")
    vector_field: str = Field(default="v_overall_style", description="Milvus 检索向量字段")
    experiment_mode: str = Field(default="long_sentence", description="查询向量构造模式")
    tag_weights: Dict[str, float] = Field(default_factory=dict, description="字段标签权重")
    scalar_filters: Dict[str, Any] = Field(default_factory=dict, description="额外的标量过滤条件")
    exclude_ids: List[int] = Field(default_factory=list, description="需要排除的 internal_id 列表")
    use_cache: bool = Field(default=True, description="是否启用检索缓存")
    enable_external_expansion: bool = Field(default=True, description="库内结果不足时是否触发蒲公英扩库")
    enable_greedy_degrade: bool = Field(default=True, description="库内结果仍不足时是否执行贪心降级")
    external_page_size: int = Field(default=20, ge=1, le=50, description="外部扩库时的单页请求数量")
    fusion_alpha: float = Field(default=0.7, ge=0.0, le=2.0, description="campaign 动态向量融合权重")
    fusion_beta: float = Field(default=0.3, ge=0.0, le=2.0, description="文本语义向量融合权重")


class MatchRetrieveResponse(BaseModel):
    success: bool = True
    task_id: str
    status: str
    result: Dict[str, Any]


class NextBatchRecommendRequest(BaseModel):
    brand_name: str = Field(..., min_length=1, description="品牌名")
    spu_name: str = Field(..., min_length=1, description="SPU 名")
    brand_stage: str = Field(default="", description="当前品牌/项目阶段，例如冷启、放量、转化冲刺")
    operator_id: Optional[int] = Field(default=None, description="当前操作人 ID，用于叠加用户私有偏好记忆")
    operator_role: Optional[Any] = Field(default=2, description="当前操作角色，支持 1/2/3 或 采购/策划/客户")
    raw_text: str = Field(default="", description="可选的当前自然语言描述；若不传则回退到 SPU 历史意图")
    intent: Optional[Dict[str, Any]] = Field(default=None, description="可选的当前确认后意图")
    top_k: int = Field(default=10, ge=1, le=200, description="下一批推荐数量")
    vector_field: str = Field(default="v_overall_style", description="Milvus 检索向量字段")
    experiment_mode: str = Field(default="field_tags_weighted", description="下一批推荐默认使用的向量构造模式")
    tag_weights: Dict[str, float] = Field(default_factory=dict, description="在 SPU 推荐特征基础上由前端进一步微调的 tag 权重")
    selected_ids: List[int] = Field(default_factory=list, description="本轮刚选中的达人，用于排重")
    rejected_ids: List[int] = Field(default_factory=list, description="本轮刚淘汰的达人，用于排重")
    pending_ids: List[int] = Field(default_factory=list, description="本轮待定达人，用于排重")
    extra_exclude_ids: List[int] = Field(default_factory=list, description="额外排除的达人 ID")
    exclude_history: bool = Field(default=True, description="是否默认排除该 SPU 历史已看过/已决策达人")
    use_cache: bool = Field(default=True, description="是否启用缓存")
    enable_external_expansion: bool = Field(default=True, description="结果不足时是否触发扩库")
    enable_greedy_degrade: bool = Field(default=True, description="结果不足时是否执行贪心降级")
    external_page_size: int = Field(default=20, ge=1, le=50, description="扩库请求单页大小")
    use_memory_feedback: bool = Field(default=True, description="是否在下一批推荐中叠加 SPU / 用户历史反馈")
    current_feedback_factor: float = Field(default=1.0, ge=0.0, le=3.0, description="本轮 selected/rejected 对进化与权重调整的基础系数")
    history_feedback_decay: float = Field(default=0.55, ge=0.0, le=3.0, description="历史反馈的统一衰减系数")
    spu_history_decay: float = Field(default=0.85, ge=0.0, le=3.0, description="SPU 历史反馈在统一衰减后的额外系数")
    user_history_decay: float = Field(default=1.0, ge=0.0, le=3.0, description="用户历史反馈在统一衰减后的额外系数")
    history_feedback_limit: int = Field(default=6, ge=1, le=50, description="每类历史反馈最多使用多少个达人作为进化种子")
    feedback_tag_step: float = Field(default=0.32, ge=0.0, le=1.0, description="标签权重升降的步长系数")
    feedback_tag_max_delta: float = Field(default=0.45, ge=0.0, le=1.0, description="单次下一批推荐允许的最大标签权重改变量")
    role_time_decay_days: float = Field(default=21.0, ge=1.0, le=180.0, description="历史反馈时间衰减半衰期天数")
    role_time_decay_min_factor: float = Field(default=0.35, ge=0.0, le=1.0, description="历史反馈时间衰减的最低保留系数")
    role_decay_overrides: Dict[str, Dict[str, float]] = Field(default_factory=dict, description="按角色覆盖衰减参数，例如 {'客户': {'decay_days': 30, 'min_factor': 0.5}}")
    brand_stage_match_factor: float = Field(default=1.0, ge=0.1, le=2.0, description="历史反馈品牌阶段与当前阶段一致时的附加系数")
    brand_stage_mismatch_factor: float = Field(default=0.72, ge=0.0, le=2.0, description="历史反馈品牌阶段与当前阶段不一致时的附加系数")
    campaign_freshness_decay_days: float = Field(default=14.0, ge=1.0, le=180.0, description="campaign 新鲜度衰减窗口天数")
    campaign_freshness_min_factor: float = Field(default=0.6, ge=0.0, le=1.0, description="campaign 新鲜度衰减的最低保留系数")
    rocchio_alpha: float = Field(default=1.0, ge=0.0, le=3.0, description="Rocchio 基础查询向量权重")
    rocchio_beta: float = Field(default=0.65, ge=0.0, le=3.0, description="Rocchio 正反馈向量权重")
    rocchio_gamma: float = Field(default=0.30, ge=0.0, le=3.0, description="Rocchio 负反馈向量权重")


class NextBatchRecommendResponse(BaseModel):
    success: bool = True
    result: Dict[str, Any]


class PayloadGenerateRequest(BaseModel):
    raw_text: str = Field(default="", description="原始自然语言查询")
    intent: Optional[Dict[str, Any]] = Field(default=None, description="已解析好的意图对象")
    data_requirements: Dict[str, Any] = Field(default_factory=dict, description="显式传入的数据约束")
    query_plan: Dict[str, Any] = Field(default_factory=dict, description="显式传入的视觉 query plan")
    content_query: str = Field(default="", description="用于 contentTag 生成的内容描述")
    page_size: int = Field(default=20, ge=1, le=50, description="生成 payload 的 pageSize")


class PayloadGenerateResponse(BaseModel):
    success: bool = True
    payload_bundle: Dict[str, Any]


class LibraryExpandRequest(BaseModel):
    raw_text: str = Field(default="", description="原始自然语言查询")
    brand_name: str = Field(default="", description="品牌名")
    intent: Optional[Dict[str, Any]] = Field(default=None, description="已解析好的意图对象")
    data_requirements: Dict[str, Any] = Field(default_factory=dict, description="显式传入的数据约束")
    query_plan: Dict[str, Any] = Field(default_factory=dict, description="显式传入的视觉 query plan")
    needed_count: int = Field(default=20, ge=1, le=200, description="希望补齐的达人数量")
    page_size: int = Field(default=20, ge=1, le=50, description="外部接口单页拉取数量")


class LibraryExpandResponse(BaseModel):
    success: bool = True
    result: Dict[str, Any]


class AssetsCommitRequest(BaseModel):
    campaign_id: Optional[int] = Field(default=None, description="已有寻星任务 ID；若不传则自动创建")
    brand_name: str = Field(..., min_length=1, description="品牌名")
    spu_name: str = Field(..., min_length=1, description="SPU 名")
    brand_stage: str = Field(default="", description="当前品牌/项目阶段，用于历史解释和衰减策略")
    raw_text: str = Field(default="", description="原始自然语言查询")
    intent: Optional[Dict[str, Any]] = Field(default=None, description="意图快照")
    query_vector: List[float] = Field(default_factory=list, description="本轮最终查询向量快照")
    tag_weights: Dict[str, float] = Field(default_factory=dict, description="前端确认弹窗中最终调整后的 tag 权重")
    data_requirements: Dict[str, Any] = Field(default_factory=dict, description="前端改写后的数据需求")
    selected_ids: List[int] = Field(default_factory=list, description="用户选中的达人 internal_id 列表")
    rejected_ids: List[int] = Field(default_factory=list, description="用户淘汰的达人 internal_id 列表")
    pending_ids: List[int] = Field(default_factory=list, description="用户待定的达人 internal_id 列表")
    operator_id: Optional[int] = Field(default=None, description="操作人 ID")
    operator_role: Any = Field(default=2, description="操作角色，支持 1/2/3 或 采购/策划/客户")
    evolution_snapshot: Dict[str, Any] = Field(default_factory=dict, description="上一轮 Fission 的权重变化与 Rocchio 摘要，便于沉淀到历史视图")
    content_summary: str = Field(default="", description="本次履约内容摘要，可用于时间线下钻展示")
    collaboration_note: str = Field(default="", description="本次合作备注或履约说明")
    material_assets: List[Dict[str, Any]] = Field(default_factory=list, description="本次合作关联的素材/内容资产列表")
    delivery_links: List[Dict[str, Any]] = Field(default_factory=list, description="本次合作关联的履约链接或外部资产链接")
    action_type: str = Field(default="commit", description="履约动作类型")


class AssetsCommitResponse(BaseModel):
    success: bool = True
    result: Dict[str, Any]


class SpuMemoryResponse(BaseModel):
    success: bool = True
    result: Dict[str, Any]


class UserMemoryResponse(BaseModel):
    success: bool = True
    result: Dict[str, Any]


class LibraryListResponse(BaseModel):
    success: bool = True
    result: Dict[str, Any]


class LibraryHistoryResponse(BaseModel):
    success: bool = True
    result: Dict[str, Any]


class CreatorDataRowPayload(BaseModel):
    creator_id: Optional[int] = Field(default=None, description="仓库内达人 internal_id")
    creator_uid: Optional[str] = Field(default=None, description="外部全量数据接口所需 UID")
    nickname: str = Field(default="", description="达人昵称")
    redbook_id: str = Field(default="", description="小红书号")
    region: str = Field(default="", description="地区")
    followers: Optional[int] = Field(default=None, description="粉丝量")
    tags: List[str] = Field(default_factory=list, description="达人标签")
    raw: Dict[str, Any] = Field(default_factory=dict, description="原始达人记录，便于后端补充识别 UID 与基础字段")


class CreatorDataEnrichRequest(BaseModel):
    brand_name: str = Field(default="", description="品牌名")
    spu_name: str = Field(default="", description="SPU 名")
    influencer_ids: List[int] = Field(default_factory=list, description="需补充数据的达人 internal_id 列表")
    creators: List[CreatorDataRowPayload] = Field(default_factory=list, description="前端已选达人对象列表")
    field_keys: List[str] = Field(default_factory=list, description="本次要补充/展示的字段 key 列表")
    template_id: str = Field(default="", description="可选的导出模板 ID")


class CreatorDataEnrichResponse(BaseModel):
    success: bool = True
    result: Dict[str, Any]


class ExportTemplateSaveRequest(BaseModel):
    template_id: str = Field(default="", description="模板 ID；传入则更新")
    template_name: str = Field(..., min_length=1, description="模板名称")
    description: str = Field(default="", description="模板说明")
    brand_name: str = Field(default="", description="品牌名")
    spu_name: str = Field(default="", description="SPU 名")
    operator_id: Optional[int] = Field(default=None, description="操作人 ID")
    field_keys: List[str] = Field(default_factory=list, description="模板保存的字段 key 列表")


class ExportTemplateSaveResponse(BaseModel):
    success: bool = True
    result: Dict[str, Any]


class ExportTemplateListResponse(BaseModel):
    success: bool = True
    result: Dict[str, Any]


class CreatorDataExportRequest(BaseModel):
    brand_name: str = Field(default="", description="品牌名")
    spu_name: str = Field(default="", description="SPU 名")
    influencer_ids: List[int] = Field(default_factory=list, description="需导出的达人 internal_id 列表")
    creators: List[CreatorDataRowPayload] = Field(default_factory=list, description="前端已选达人对象列表")
    rows: List[Dict[str, Any]] = Field(default_factory=list, description="已补充好的达人数据行，可直接用于导出")
    field_keys: List[str] = Field(default_factory=list, description="本次导出的字段 key 列表")
    template_id: str = Field(default="", description="使用的模板 ID")


class CreatorDataExportResponse(BaseModel):
    success: bool = True
    result: Dict[str, Any]


class CreatorDataCatalogResponse(BaseModel):
    success: bool = True
    result: Dict[str, Any]


class TaskStatusResponse(BaseModel):
    success: bool = True
    task: Dict[str, Any]
