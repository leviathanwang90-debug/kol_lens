from __future__ import annotations

import logging

from fastapi import FastAPI, HTTPException

from api.schemas import (
    IntentParseRequest,
    IntentParseResponse,
    MatchRetrieveRequest,
    MatchRetrieveResponse,
    TaskStatusResponse,
)
from services.intent_parser import intent_parser_service
from services.match_service import match_service

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Σ.Match Backend Service",
    version="0.2.0",
    description="提供自然语言意图解析与达人向量检索能力的后端服务。",
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


@app.get("/api/v1/tasks/{task_id}", response_model=TaskStatusResponse)
def get_task_status(task_id: str) -> TaskStatusResponse:
    task = match_service.get_task_info(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在。")
    return TaskStatusResponse(task=task)
