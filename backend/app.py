from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env", override=False)
load_dotenv(BASE_DIR / ".env.production", override=False)

from api.schemas import (
    AssetsCommitRequest,
    AssetsCommitResponse,
    CreatorDataCatalogResponse,
    CreatorDataEnrichRequest,
    CreatorDataEnrichResponse,
    CreatorDataExportRequest,
    CreatorDataExportResponse,
    ExportTemplateListResponse,
    ExportTemplateSaveRequest,
    ExportTemplateSaveResponse,
    IntentParseRequest,
    IntentParseResponse,
    LibraryExpandRequest,
    LibraryExpandResponse,
    LibraryHistoryResponse,
    LibraryListResponse,
    MatchRetrieveRequest,
    MatchRetrieveResponse,
    NextBatchRecommendRequest,
    NextBatchRecommendResponse,
    PayloadGenerateRequest,
    PayloadGenerateResponse,
    SpuMemoryResponse,
    TaskStatusResponse,
    UserMemoryResponse,
)
from services.asset_service import asset_service
from services.creator_data_service import creator_data_service
from services.intent_parser import intent_parser_service
from services.match_service import match_service
from services.pgy_service import pgy_expansion_service

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Σ.Match Backend Service",
    version="0.5.0",
    description="提供自然语言需求解析、达人匹配、蒲公英扩库、资产提交、SPU 偏好记忆与下一批推荐能力的后端服务。",
)


@app.get("/healthz")
def healthz():
    return {"status": "ok"}


@app.post("/api/v1/intent/parse", response_model=IntentParseResponse)
def parse_intent(payload: IntentParseRequest) -> IntentParseResponse:
    try:
        intent = intent_parser_service.parse(
            payload.raw_text,
            brand_name=payload.brand_name,
            spu_name=payload.spu_name,
        )
        return IntentParseResponse(intent=intent)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # pragma: no cover - 主要用于运行时异常保护
        logger.exception("意图解析接口执行失败")
        raise HTTPException(status_code=500, detail=f"意图解析失败: {exc}") from exc


@app.post("/api/v1/pgy/payload/generate", response_model=PayloadGenerateResponse)
def generate_external_payload(payload: PayloadGenerateRequest) -> PayloadGenerateResponse:
    try:
        intent = payload.intent
        if not isinstance(intent, dict):
            if not payload.raw_text and not payload.data_requirements and not payload.query_plan:
                raise ValueError("raw_text、intent、data_requirements/query_plan 至少提供一种。")
            if payload.raw_text:
                intent = intent_parser_service.parse(payload.raw_text)
            else:
                intent = {
                    "data_requirements": payload.data_requirements,
                    "query_plan": payload.query_plan,
                }
        bundle = pgy_expansion_service.generate_payload(
            {
                "data_requirements": payload.data_requirements or intent.get("data_requirements") or {},
                "query_plan": payload.query_plan or intent.get("query_plan") or {},
                "content_query": payload.content_query,
                "page_size": payload.page_size,
            }
        )
        return PayloadGenerateResponse(payload_bundle=bundle)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # pragma: no cover - 主要用于运行时异常保护
        logger.exception("payload 生成接口执行失败")
        raise HTTPException(status_code=500, detail=f"payload 生成失败: {exc}") from exc


@app.post("/api/v1/library/expand", response_model=LibraryExpandResponse)
def expand_library(payload: LibraryExpandRequest) -> LibraryExpandResponse:
    try:
        intent = payload.intent
        if not isinstance(intent, dict):
            if not payload.raw_text and not payload.data_requirements and not payload.query_plan:
                raise ValueError("raw_text、intent、data_requirements/query_plan 至少提供一种。")
            if payload.raw_text:
                intent = intent_parser_service.parse(payload.raw_text, brand_name=payload.brand_name)
            else:
                intent = {
                    "data_requirements": payload.data_requirements,
                    "query_plan": payload.query_plan,
                }
        result = pgy_expansion_service.expand_library(
            data_requirements=payload.data_requirements or intent.get("data_requirements") or {},
            query_plan=payload.query_plan or intent.get("query_plan") or {},
            needed_count=payload.needed_count,
            brand_name=payload.brand_name,
            page_size=payload.page_size,
        )
        return LibraryExpandResponse(result=result)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # pragma: no cover - 主要用于运行时异常保护
        logger.exception("外部扩库接口执行失败")
        raise HTTPException(status_code=500, detail=f"外部扩库失败: {exc}") from exc


@app.post("/api/v1/match/retrieve", response_model=MatchRetrieveResponse)
def retrieve_match(payload: MatchRetrieveRequest) -> MatchRetrieveResponse:
    try:
        response = match_service.submit_retrieve_task(payload.model_dump())
        return MatchRetrieveResponse(**response)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # pragma: no cover - 主要用于运行时异常保护
        logger.exception("达人检索接口执行失败")
        raise HTTPException(status_code=500, detail=f"达人检索失败: {exc}") from exc


@app.post("/api/v1/match/next-batch", response_model=NextBatchRecommendResponse)
def recommend_next_batch(payload: NextBatchRecommendRequest) -> NextBatchRecommendResponse:
    try:
        result = asset_service.recommend_next_batch(payload.model_dump())
        return NextBatchRecommendResponse(result=result)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # pragma: no cover - 主要用于运行时异常保护
        logger.exception("下一批推荐接口执行失败")
        raise HTTPException(status_code=500, detail=f"下一批推荐失败: {exc}") from exc


@app.post("/api/v1/assets/commit", response_model=AssetsCommitResponse)
def commit_assets(payload: AssetsCommitRequest) -> AssetsCommitResponse:
    try:
        result = asset_service.commit_assets(payload.model_dump())
        return AssetsCommitResponse(result=result)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # pragma: no cover - 主要用于运行时异常保护
        logger.exception("资产提交接口执行失败")
        raise HTTPException(status_code=500, detail=f"资产提交失败: {exc}") from exc


@app.get("/api/v1/spu/memory", response_model=SpuMemoryResponse)
def get_spu_memory(
    brand_name: str = Query(..., min_length=1),
    spu_name: str = Query(..., min_length=1),
) -> SpuMemoryResponse:
    try:
        result = asset_service.get_spu_memory(
            {
                "brand_name": brand_name,
                "spu_name": spu_name,
            }
        )
        return SpuMemoryResponse(result=result)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # pragma: no cover - 主要用于运行时异常保护
        logger.exception("SPU 偏好记忆接口执行失败")
        raise HTTPException(status_code=500, detail=f"SPU 偏好记忆查询失败: {exc}") from exc


@app.get("/api/v1/user/memory", response_model=UserMemoryResponse)
def get_user_memory(
    operator_id: int = Query(..., ge=1),
    brand_name: str = Query(default=""),
    spu_name: str = Query(default=""),
) -> UserMemoryResponse:
    try:
        result = asset_service.get_user_memory(
            {
                "operator_id": operator_id,
                "brand_name": brand_name,
                "spu_name": spu_name,
            }
        )
        return UserMemoryResponse(result=result)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # pragma: no cover - 主要用于运行时异常保护
        logger.exception("用户私有偏好记忆接口执行失败")
        raise HTTPException(status_code=500, detail=f"用户私有偏好记忆查询失败: {exc}") from exc


@app.get("/api/v1/library/list", response_model=LibraryListResponse)
def list_library(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    keyword: str = Query(default=""),
    brand_name: str = Query(default=""),
    spu_name: str = Query(default=""),
    region: str = Query(default=""),
    followers_min: Optional[int] = Query(default=None, ge=0),
    followers_max: Optional[int] = Query(default=None, ge=0),
    gender: str = Query(default=""),
    tags: str = Query(default=""),
    sort_by: str = Query(default="followers"),
    sort_order: str = Query(default="DESC"),
) -> LibraryListResponse:
    try:
        result = asset_service.list_library(
            {
                "page": page,
                "page_size": page_size,
                "keyword": keyword,
                "brand_name": brand_name,
                "spu_name": spu_name,
                "region": region,
                "followers_min": followers_min,
                "followers_max": followers_max,
                "gender": gender,
                "tags": tags,
                "sort_by": sort_by,
                "sort_order": sort_order,
            }
        )
        return LibraryListResponse(result=result)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # pragma: no cover - 主要用于运行时异常保护
        logger.exception("资产库列表接口执行失败")
        raise HTTPException(status_code=500, detail=f"资产库列表查询失败: {exc}") from exc


@app.get("/api/v1/library/history", response_model=LibraryHistoryResponse)
def library_history(
    influencer_id: Optional[int] = Query(default=None),
    campaign_id: Optional[int] = Query(default=None),
    record_id: Optional[int] = Query(default=None),
    brand_name: str = Query(default=""),
    spu_name: str = Query(default=""),
) -> LibraryHistoryResponse:
    try:
        result = asset_service.get_history(
            {
                "influencer_id": influencer_id,
                "campaign_id": campaign_id,
                "record_id": record_id,
                "brand_name": brand_name,
                "spu_name": spu_name,
            }
        )
        return LibraryHistoryResponse(result=result)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # pragma: no cover - 主要用于运行时异常保护
        logger.exception("资产库历史接口执行失败")
        raise HTTPException(status_code=500, detail=f"资产库历史查询失败: {exc}") from exc


@app.get("/api/v1/creator-data/catalog", response_model=CreatorDataCatalogResponse)
def creator_data_catalog() -> CreatorDataCatalogResponse:
    try:
        return CreatorDataCatalogResponse(result=creator_data_service.get_catalog())
    except Exception as exc:  # pragma: no cover - 主要用于运行时异常保护
        logger.exception("全量达人数据字段目录接口执行失败")
        raise HTTPException(status_code=500, detail=f"字段目录查询失败: {exc}") from exc


@app.post("/api/v1/creator-data/enrich", response_model=CreatorDataEnrichResponse)
def enrich_creator_data(payload: CreatorDataEnrichRequest) -> CreatorDataEnrichResponse:
    try:
        result = creator_data_service.enrich_creators(payload.model_dump())
        return CreatorDataEnrichResponse(result=result)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # pragma: no cover - 主要用于运行时异常保护
        logger.exception("全量达人数据补充接口执行失败")
        raise HTTPException(status_code=500, detail=f"达人数据补充失败: {exc}") from exc


@app.get("/api/v1/export/templates", response_model=ExportTemplateListResponse)
def list_export_templates(
    operator_id: Optional[int] = Query(default=None),
    brand_name: str = Query(default=""),
    spu_name: str = Query(default=""),
) -> ExportTemplateListResponse:
    try:
        result = creator_data_service.list_templates(
            {
                "operator_id": operator_id,
                "brand_name": brand_name,
                "spu_name": spu_name,
            }
        )
        return ExportTemplateListResponse(result=result)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # pragma: no cover - 主要用于运行时异常保护
        logger.exception("导出模板列表接口执行失败")
        raise HTTPException(status_code=500, detail=f"导出模板列表查询失败: {exc}") from exc


@app.post("/api/v1/export/templates", response_model=ExportTemplateSaveResponse)
def save_export_template(payload: ExportTemplateSaveRequest) -> ExportTemplateSaveResponse:
    try:
        result = creator_data_service.save_template(payload.model_dump())
        return ExportTemplateSaveResponse(result=result)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # pragma: no cover - 主要用于运行时异常保护
        logger.exception("导出模板保存接口执行失败")
        raise HTTPException(status_code=500, detail=f"导出模板保存失败: {exc}") from exc


@app.post("/api/v1/export/creators", response_model=CreatorDataExportResponse)
def export_creator_data(payload: CreatorDataExportRequest) -> CreatorDataExportResponse:
    try:
        result = creator_data_service.export_creator_data(payload.model_dump())
        return CreatorDataExportResponse(result=result)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # pragma: no cover - 主要用于运行时异常保护
        logger.exception("达人导出接口执行失败")
        raise HTTPException(status_code=500, detail=f"达人导出失败: {exc}") from exc


@app.get("/api/v1/export/download/{file_name}")
def download_export_file(file_name: str) -> FileResponse:
    try:
        file_path = creator_data_service.get_export_file_path(file_name)
        return FileResponse(path=file_path, filename=file_path.name, media_type="text/csv")
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:  # pragma: no cover - 主要用于运行时异常保护
        logger.exception("导出文件下载接口执行失败")
        raise HTTPException(status_code=500, detail=f"导出文件下载失败: {exc}") from exc


@app.get("/api/v1/tasks/{task_id}", response_model=TaskStatusResponse)
def get_task_status(task_id: str) -> TaskStatusResponse:
    task = match_service.get_task_info(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在。")
    return TaskStatusResponse(task=task)
