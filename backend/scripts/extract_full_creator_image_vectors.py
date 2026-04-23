"""全量博主图片向量特征提取与入库（并行版，DashVector）。"""

from __future__ import annotations

import argparse
import concurrent.futures as futures
import logging
from typing import Any, Dict, List, Optional, Tuple

from db import db
from services.pgy_service import _embed_multimodal_profile_vector

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")


def _fetch_batch(offset: int, limit: int) -> List[Dict[str, Any]]:
    sql = """
        SELECT
            ib.internal_id,
            ib.gender,
            ib.region,
            ib.followers,
            ib.ad_ratio_30d,
            ib.avatar_url,
            ARRAY(
                SELECT note.cover_image_url
                FROM influencer_notes note
                WHERE note.influencer_id = ib.internal_id
                  AND note.cover_image_url IS NOT NULL
                ORDER BY note.published_at DESC NULLS LAST, note.note_id DESC
                LIMIT 2
            ) AS cover_urls
        FROM influencer_basics ib
        ORDER BY ib.internal_id
        LIMIT %s OFFSET %s
    """
    with db.get_cursor() as cur:
        cur.execute(sql, (limit, offset))
        return [dict(r) for r in cur.fetchall()]


def _embed_one(row: Dict[str, Any], dim: int) -> Optional[Dict[str, Any]]:
    vector = _embed_multimodal_profile_vector(
        avatar_url=row.get("avatar_url") or "",
        cover_urls=row.get("cover_urls") or [],
        dim=dim,
    )
    if not vector:
        return None
    return {
        "id": int(row["internal_id"]),
        "followers": int(row.get("followers") or 0),
        "region": str(row.get("region") or ""),
        "gender": str(row.get("gender") or ""),
        "ad_ratio": float(row.get("ad_ratio_30d") or 0.0),
        "embedding": vector,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Extract full creator image vectors and upsert to DashVector")
    parser.add_argument("--batch-size", type=int, default=500)
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--limit", type=int, default=0, help="0 表示全量")
    parser.add_argument("--dim", type=int, default=1024)
    args = parser.parse_args()

    from milvus import milvus_mgr

    db.connect()
    milvus_mgr.connect()
    milvus_mgr.create_collection(drop_if_exists=False)

    offset = 0
    total = 0
    inserted = 0
    try:
        while True:
            if args.limit > 0 and total >= args.limit:
                break
            current_batch = min(args.batch_size, args.limit - total) if args.limit > 0 else args.batch_size
            rows = _fetch_batch(offset, current_batch)
            if not rows:
                break
            total += len(rows)
            offset += len(rows)

            items: List[Dict[str, Any]] = []
            with futures.ThreadPoolExecutor(max_workers=max(1, args.workers)) as ex:
                for result in ex.map(lambda r: _embed_one(r, args.dim), rows):
                    if result:
                        items.append(result)

            if items:
                inserted += milvus_mgr.upsert(items)
            logger.info("processed=%s embedded=%s", total, inserted)
    finally:
        db.close()

    logger.info("done total=%s embedded=%s", total, inserted)


if __name__ == "__main__":
    main()
