from __future__ import annotations

import argparse
import json
import logging
import os
import time
from collections import defaultdict
from datetime import date, datetime, timedelta
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple

import numpy as np
import requests

from db import db
from milvus import milvus_mgr

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")


class TokenManager:
    def __init__(self) -> None:
        self.app_id = os.getenv("XHS_APP_ID", "")
        self.app_secret = os.getenv("XHS_APP_SECRET", "")
        self.auth_code = os.getenv("XHS_AUTH_CODE", "")
        self.auth_user_id = os.getenv("XHS_AUTH_USER_ID", "")
        self.token_url = os.getenv("XHS_TOKEN_URL", "https://api.xiaohongshu.com/oauth/token")
        self.refresh_url = os.getenv("XHS_REFRESH_URL", self.token_url)
        self.token_file = os.getenv("XHS_TOKEN_FILE", os.path.join(os.path.dirname(__file__), "token_pgy.json"))

    def _load(self) -> Dict[str, Any]:
        if not os.path.exists(self.token_file):
            return {}
        with open(self.token_file, "r", encoding="utf-8") as f:
            return json.load(f)

    def _save(self, payload: Dict[str, Any]) -> None:
        with open(self.token_file, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False)

    def _exchange_auth_code(self) -> Dict[str, Any]:
        resp = requests.post(
            self.token_url,
            json={
                "app_id": self.app_id,
                "app_secret": self.app_secret,
                "auth_code": self.auth_code,
                "user_id": self.auth_user_id,
                "grant_type": "authorization_code",
            },
            timeout=20,
        )
        resp.raise_for_status()
        data = resp.json()
        return {
            "access_token": data["access_token"],
            "refresh_token": data.get("refresh_token"),
            "expires_at": time.time() + int(data.get("expires_in", 7200)),
        }

    def _refresh(self, refresh_token: str) -> Dict[str, Any]:
        resp = requests.post(
            self.refresh_url,
            json={
                "app_id": self.app_id,
                "app_secret": self.app_secret,
                "refresh_token": refresh_token,
                "grant_type": "refresh_token",
            },
            timeout=20,
        )
        resp.raise_for_status()
        data = resp.json()
        return {
            "access_token": data["access_token"],
            "refresh_token": data.get("refresh_token", refresh_token),
            "expires_at": time.time() + int(data.get("expires_in", 7200)),
        }

    def get_access_token(self) -> str:
        token = self._load()
        now = time.time()
        if token.get("access_token") and float(token.get("expires_at", 0)) - now > 60:
            return token["access_token"]
        if token.get("refresh_token"):
            try:
                refreshed = self._refresh(token["refresh_token"])
                self._save(refreshed)
                return refreshed["access_token"]
            except Exception:
                logger.warning("refresh_token 刷新失败，回退 auth_code 重新换取", exc_info=True)
        exchanged = self._exchange_auth_code()
        self._save(exchanged)
        return exchanged["access_token"]


def _normalize(v: Iterable[float]) -> List[float]:
    arr = np.array(list(v), dtype=np.float32)
    if arr.size == 0:
        return []
    n = float(np.linalg.norm(arr))
    if n == 0:
        return arr.tolist()
    return (arr / n).tolist()


def fetch_xiaohongshu_daily_data(run_day: Optional[date], token: str, page_size: int = 100) -> List[Dict[str, Any]]:
    """递归拉取昨日全量投后数据，处理分页。"""
    note_api_url = os.getenv(
        "XHS_NOTE_API_URL",
        "https://adapi.xiaohongshu.com/api/open/pgy/note/post/data",
    )
    day = (run_day or (datetime.now().date() - timedelta(days=1))).strftime("%Y-%m-%d")
    auth_user_id = os.getenv("XHS_AUTH_USER_ID", "")
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {token}"}
    base_payload = {
        "user_id": auth_user_id,
        "date_type": 2,
        "start_time": day,
        "end_time": day,
        "page_size": page_size,
    }

    all_notes: List[Dict[str, Any]] = []
    page_num = 1
    total_page = 1
    while page_num <= total_page:
        payload = dict(base_payload)
        payload["page_num"] = page_num
        resp = requests.post(note_api_url, json=payload, headers=headers, timeout=20)
        resp.raise_for_status()
        body = resp.json()
        if not (body.get("code") == 0 and body.get("success")):
            logger.warning("拉取投后数据失败: page=%s body=%s", page_num, body)
            break
        data = body.get("data") or {}
        all_notes.extend(data.get("datas") or [])
        total_page = int(data.get("total_page") or page_num)
        page_num += 1
    return all_notes


def aggregate_by_brand_spu(rows: List[Dict[str, Any]]) -> Dict[Tuple[str, str], Set[int]]:
    grouped: Dict[Tuple[str, str], Set[int]] = defaultdict(set)
    for row in rows:
        brand = str(row.get("brand_user_name") or row.get("brand_name") or "").strip()
        spu = str(row.get("spu_name") or "").strip()
        influencer_id = row.get("kol_id") or row.get("influencer_id")
        if not brand or not spu or influencer_id is None:
            continue
        grouped[(brand, spu)].add(int(influencer_id))
    return grouped


def recompute_for_day(run_day: date, page_size: int = 200) -> Dict[str, Any]:
    token = TokenManager().get_access_token()
    rows = fetch_xiaohongshu_daily_data(run_day=run_day, token=token, page_size=page_size)
    grouped = aggregate_by_brand_spu(rows)
    db.connect()
    milvus_mgr.connect()
    stats = {"groups": 0, "updated": 0, "new_kols": 0}
    try:
        for (brand_name, spu_name), daily_ids in grouped.items():
            stats["groups"] += 1
            spu_record = db.ensure_brand_spu(brand_name, spu_name)
            spu_id = int(spu_record["spu_id"])

            existing = set(db.get_existing_collaboration_ids(spu_id, list(daily_ids)))
            fresh_ids = sorted(set(daily_ids) - existing)
            if not fresh_ids:
                continue

            vectors = milvus_mgr.retrieve_by_ids(fresh_ids)
            vectors = [row for row in vectors if row.get("embedding")]
            if not vectors:
                continue

            old_vector = spu_record.get("base_vector") or []
            old_count = int(spu_record.get("kol_count") or 0)
            new_vectors = [np.array(v["embedding"], dtype=np.float32) for v in vectors]
            new_count = len(new_vectors)
            stats["new_kols"] += new_count

            if old_vector and old_count > 0:
                old_arr = np.array(old_vector, dtype=np.float32)
                if old_arr.size != new_vectors[0].size:
                    max_dim = max(old_arr.size, new_vectors[0].size)
                    old_arr = np.pad(old_arr, (0, max_dim - old_arr.size))
                    new_vectors = [np.pad(v, (0, max_dim - v.size)) for v in new_vectors]
                merged = ((old_arr * old_count) + np.sum(new_vectors, axis=0)) / (old_count + new_count)
            else:
                merged = np.mean(new_vectors, axis=0)

            total_count = old_count + new_count
            db.update_brand_spu_base_vector(spu_id, _normalize(merged.tolist()), kol_count=total_count)
            db.insert_collaborations(spu_id, [int(v["id"]) for v in vectors], collaboration_date=run_day)
            stats["updated"] += 1
    finally:
        db.close()
        milvus_mgr.disconnect()
    return stats


def main() -> None:
    parser = argparse.ArgumentParser(description="Recompute brand SPU base vectors incrementally")
    parser.add_argument("--day", default=(date.today() - timedelta(days=1)).isoformat(), help="YYYY-MM-DD")
    parser.add_argument("--page-size", type=int, default=200)
    parser.add_argument("--cron-hint", action="store_true", help="打印 Linux crontab 示例")
    args = parser.parse_args()
    if args.cron_hint:
        logger.info("crontab 示例: 0 2 * * * cd /srv/kol_lens && python backend/scripts/recompute_brand_base_vectors.py")
    day = date.fromisoformat(args.day)
    result = recompute_for_day(day, page_size=args.page_size)
    logger.info("done: %s", result)


if __name__ == "__main__":
    main()
