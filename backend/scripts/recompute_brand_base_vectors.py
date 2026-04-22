"""每日增量任务：拉取投后数据并按加权移动平均更新 brand_spus.base_vector。"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timedelta
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple

import numpy as np
import requests

from db import db
from milvus import milvus_mgr

logger = logging.getLogger(__name__)

XHS_API_URL = os.getenv(
    "XHS_NOTE_API_URL",
    "https://adapi.xiaohongshu.com/api/open/pgy/note/post/data",
)
XHS_AUTH_TOKEN = os.getenv("XHS_AUTH_TOKEN", "")
XHS_AUTH_USER_ID = os.getenv("XHS_AUTH_USER_ID", "")
XHS_TIMEOUT_SECONDS = int(os.getenv("XHS_TIMEOUT_SECONDS", "20"))


def _as_int(value: Any) -> Optional[int]:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _extract_embedding(record: Any) -> Optional[List[float]]:
    vector = getattr(record, "vector", None)
    if isinstance(vector, dict):
        return vector.get("embedding")
    return vector


def fetch_xiaohongshu_daily_data(target_date: Optional[datetime] = None) -> List[Dict[str, Any]]:
    """递归拉取昨日全量投后数据，处理分页。"""
    if not XHS_AUTH_TOKEN or not XHS_AUTH_USER_ID:
        raise RuntimeError("缺少 XHS_AUTH_TOKEN 或 XHS_AUTH_USER_ID 环境变量")

    date = target_date or (datetime.utcnow() - timedelta(days=1))
    day = date.strftime("%Y-%m-%d")

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {XHS_AUTH_TOKEN}",
    }
    payload: Dict[str, Any] = {
        "user_id": XHS_AUTH_USER_ID,
        "date_type": 2,
        "start_time": day,
        "end_time": day,
        "page_size": 100,
    }

    notes: List[Dict[str, Any]] = []
    page_num = 1
    total_page = 1

    while page_num <= total_page:
        payload["page_num"] = page_num
        response = requests.post(
            XHS_API_URL,
            json=payload,
            headers=headers,
            timeout=XHS_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        body = response.json()

        if body.get("code") != 0 or not body.get("success"):
            logger.warning("小红书接口返回失败: page=%s body=%s", page_num, body)
            break

        data = body.get("data") or {}
        notes.extend(data.get("datas") or [])
        total_page = int(data.get("total_page") or 1)
        page_num += 1

    logger.info("拉取到 %d 条投后笔记数据 (%s)", len(notes), day)
    return notes


def group_new_kols(notes: Iterable[Dict[str, Any]]) -> Dict[Tuple[str, str], Set[int]]:
    grouped: Dict[Tuple[str, str], Set[int]] = {}
    for note in notes:
        brand_name = (note.get("brand_user_name") or "").strip()
        spu_name = (note.get("spu_name") or "").strip()
        kol_id = _as_int(note.get("kol_id"))
        if not brand_name or not spu_name or kol_id is None:
            continue
        grouped.setdefault((brand_name, spu_name), set()).add(kol_id)
    return grouped


def _normalize(vec: np.ndarray) -> np.ndarray:
    norm = np.linalg.norm(vec)
    if norm > 0:
        return vec / norm
    return vec


def process_and_update_vectors(target_date: Optional[datetime] = None) -> Dict[str, int]:
    """增量更新 base_vector，并维护 kol_count 和 collaborations 去重映射。"""
    raw_notes = fetch_xiaohongshu_daily_data(target_date)
    grouped = group_new_kols(raw_notes)

    db.connect()
    milvus_mgr.connect()

    metrics = {
        "spu_seen": 0,
        "spu_updated": 0,
        "new_collaborations": 0,
        "vectors_used": 0,
    }

    try:
        for (brand_name, spu_name), kol_ids in grouped.items():
            metrics["spu_seen"] += 1
            spu_id = db.ensure_brand_spu(brand_name, spu_name)
            spu_record = db.get_brand_spu_record(spu_id)
            if not spu_record:
                continue

            old_vector_raw = spu_record.get("base_vector")
            old_count = int(spu_record.get("kol_count") or 0)
            old_vector = None
            if old_vector_raw:
                old_vector = np.array(old_vector_raw, dtype=np.float32)

            existing_ids = set(db.get_existing_collaboration_ids(spu_id, list(kol_ids)))
            truly_new_ids = sorted(kol_ids - existing_ids)
            if not truly_new_ids:
                continue

            records = milvus_mgr.retrieve_by_ids(truly_new_ids, with_vectors=True)
            new_vectors = []
            fetched_ids = []
            for record in records:
                vec = _extract_embedding(record)
                if vec:
                    new_vectors.append(np.array(vec, dtype=np.float32))
                    fetched_ids.append(int(record.id))

            if not new_vectors:
                continue

            sum_new = np.sum(np.array(new_vectors, dtype=np.float32), axis=0)
            new_count = len(new_vectors)

            if old_vector is not None and old_count > 0:
                updated_vector = ((old_vector * old_count) + sum_new) / float(old_count + new_count)
            else:
                updated_vector = sum_new / float(new_count)

            updated_vector = _normalize(updated_vector).astype(np.float32)
            final_count = old_count + new_count

            db.update_brand_spu_base_vector(
                spu_id=spu_id,
                vector=updated_vector.tolist(),
                kol_count=final_count,
            )
            db.insert_collaborations(spu_id=spu_id, influencer_ids=fetched_ids)

            metrics["spu_updated"] += 1
            metrics["new_collaborations"] += len(fetched_ids)
            metrics["vectors_used"] += new_count

        logger.info("增量向量更新完成: %s", json.dumps(metrics, ensure_ascii=False))
        return metrics
    finally:
        db.close()


def run() -> None:
    logging.basicConfig(level=logging.INFO)
    metrics = process_and_update_vectors()
    print(f"✅ 投后数据更新及增量向量计算完成: {json.dumps(metrics, ensure_ascii=False)}")


if __name__ == "__main__":
    run()
