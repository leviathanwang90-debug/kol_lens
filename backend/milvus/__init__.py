"""
Σ.Match 向量数据库管理模块（DashVector 底层）
保留 MilvusManager / milvus_mgr 对外接口，底层切换为阿里云 DashVector。
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Sequence

import dashvector

from config import milvus_config

logger = logging.getLogger(__name__)

COLLECTION_NAME = milvus_config.collection_name
DIM_FACE = milvus_config.embedding_dim
DIM_SCENE = milvus_config.embedding_dim
DIM_STYLE = milvus_config.embedding_dim

FIELD_FACE = "embedding"
FIELD_SCENE = "embedding"
FIELD_STYLE = "embedding"

DEFAULT_TOP_K = 100


class MilvusManager:
    """表面保持 MilvusManager，底层驱动 DashVector。"""

    def __init__(self) -> None:
        self._connected = False
        self.client: Optional[dashvector.Client] = None
        self.collection = None

    def connect(self, alias: str = "default") -> str:
        _ = alias
        if self._connected and self.client is not None:
            return "DashVector Ready"

        api_key = milvus_config.api_key
        endpoint = milvus_config.endpoint
        if not api_key or not endpoint:
            raise ValueError("缺少 DashVector 环境变量配置：DASHVECTOR_API_KEY / DASHVECTOR_ENDPOINT")

        self.client = dashvector.Client(api_key=api_key, endpoint=endpoint)
        self._connected = True
        logger.info("DashVector 连接成功")
        return "DashVector"

    def disconnect(self, alias: str = "default") -> None:
        _ = alias
        self.collection = None
        self.client = None
        self._connected = False

    def server_version(self) -> str:
        return "DashVector"

    def create_collection(self, drop_if_exists: bool = False):
        if not self._connected:
            self.connect()
        if self.client is None:
            raise RuntimeError("DashVector client unavailable")

        if drop_if_exists:
            try:
                self.client.delete(COLLECTION_NAME)
                logger.warning("删除已存在 Collection: %s", COLLECTION_NAME)
            except Exception:
                pass

        collection = self.client.get(COLLECTION_NAME)
        if not collection:
            self.client.create(
                name=COLLECTION_NAME,
                dimension=milvus_config.embedding_dim,
                metric="cosine",
                fields_schema={
                    "followers": int,
                    "region": str,
                    "gender": str,
                    "ad_ratio": float,
                },
            )
            logger.info("DashVector Collection 创建成功: %s", COLLECTION_NAME)
            collection = self.client.get(COLLECTION_NAME)

        self.collection = collection
        return self.collection

    def load_collection(self) -> None:
        return None

    def release_collection(self) -> None:
        return None

    def collection_stats(self) -> Dict[str, Any]:
        if not self.collection:
            self.create_collection(drop_if_exists=False)
        try:
            stats = self.collection.stats() if self.collection else {}
        except Exception:
            stats = {}
        return {
            "name": COLLECTION_NAME,
            "stats": stats,
        }

    @staticmethod
    def _pick_embedding(item: Dict[str, Any]) -> List[float]:
        for key in ("embedding", "v_overall_style", "v_scene", "v_face"):
            value = item.get(key)
            if isinstance(value, list) and value:
                return [float(v) for v in value]
        raise ValueError("missing embedding vector")

    def insert(self, data: List[Dict[str, Any]]) -> int:
        if not data:
            return 0
        if not self.collection:
            self.create_collection(drop_if_exists=False)

        docs = []
        for item in data:
            docs.append(
                dashvector.Doc(
                    id=str(item["id"]),
                    vector=self._pick_embedding(item),
                    fields={
                        "followers": int(item.get("followers") or 0),
                        "region": str(item.get("region") or ""),
                        "gender": str(item.get("gender") or ""),
                        "ad_ratio": float(item.get("ad_ratio") or 0.0),
                    },
                )
            )
        rsp = self.collection.upsert(docs)
        if not rsp:
            logger.error("DashVector upsert 失败")
            return 0
        return len(docs)

    def upsert(self, data: List[Dict[str, Any]]) -> int:
        return self.insert(data)

    def retrieve_by_ids(self, ids: Sequence[int]) -> List[Dict[str, Any]]:
        if not ids:
            return []
        if not self.collection:
            self.create_collection(drop_if_exists=False)

        docs = self.collection.fetch([str(i) for i in ids])
        rows: List[Dict[str, Any]] = []
        for doc in docs or []:
            fields = getattr(doc, "fields", {}) or {}
            rows.append(
                {
                    "id": int(doc.id),
                    "embedding": list(getattr(doc, "vector", []) or []),
                    "followers": fields.get("followers"),
                    "region": fields.get("region"),
                    "gender": fields.get("gender"),
                    "ad_ratio": fields.get("ad_ratio"),
                }
            )
        return rows

    def get_entities_by_ids(self, ids: Sequence[int], output_fields: Optional[Sequence[str]] = None) -> List[Dict[str, Any]]:
        rows = self.retrieve_by_ids(ids)
        if not output_fields:
            return rows
        result: List[Dict[str, Any]] = []
        for row in rows:
            item = {"id": row["id"]}
            for field in output_fields:
                mapped = "embedding" if field in {"v_face", "v_scene", "v_overall_style"} else field
                item[field] = row.get(mapped)
            result.append(item)
        return result

    @staticmethod
    def _build_filter_expr(filters: Dict[str, Any]) -> str:
        if not filters:
            return ""
        conditions: List[str] = []

        regions = filters.get("region")
        if regions:
            if isinstance(regions, str):
                regions = [regions]
            escaped = [f"'{str(r).replace("'", "\\'")}'" for r in regions]
            conditions.append(f"region in ({', '.join(escaped)})")

        gender = filters.get("gender")
        if gender:
            conditions.append(f"gender = '{str(gender).replace("'", "\\'")}'")

        if filters.get("followers_min") is not None:
            conditions.append(f"followers >= {int(filters['followers_min'])}")
        if filters.get("followers_max") is not None:
            conditions.append(f"followers <= {int(filters['followers_max'])}")
        if filters.get("ad_ratio_max") is not None:
            conditions.append(f"ad_ratio < {float(filters['ad_ratio_max'])}")

        excluded = filters.get("id_not_in") or []
        if excluded:
            excluded_str = ", ".join([f"'{int(x)}'" for x in excluded])
            conditions.append(f"id not in ({excluded_str})")

        return " and ".join(conditions)

    def hybrid_search(
        self,
        *,
        vector_field: str = FIELD_STYLE,
        query_vector: List[float],
        scalar_filters: Optional[Dict[str, Any]] = None,
        top_k: int = DEFAULT_TOP_K,
    ) -> List[Dict[str, Any]]:
        _ = vector_field
        if not self.collection:
            self.create_collection(drop_if_exists=False)

        filter_expr = self._build_filter_expr(scalar_filters or {})
        docs = self.collection.query(
            vector=query_vector,
            filter=filter_expr if filter_expr else None,
            topk=int(top_k),
            include_vector=False,
        )

        result: List[Dict[str, Any]] = []
        for doc in docs or []:
            item = {
                "id": int(doc.id),
                "score": float(getattr(doc, "score", 0.0) or 0.0),
                "distance": 1.0 - float(getattr(doc, "score", 0.0) or 0.0),
            }
            fields = getattr(doc, "fields", {}) or {}
            item.update(fields)
            result.append(item)
        return result


milvus_mgr = MilvusManager()
