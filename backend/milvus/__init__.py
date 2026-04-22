"""
Σ.Match 向量数据库管理模块 (Qdrant 单向量版)
对外保持 MilvusManager/milvus_mgr 接口，底层为 Qdrant。
"""

import logging
from typing import Any, Dict, List, Optional

from qdrant_client import QdrantClient, models

from config import milvus_config

logger = logging.getLogger(__name__)

COLLECTION_NAME = milvus_config.collection_name

# 兼容旧接口暴露常量：统一向量检索后仅保留一个向量字段
DIM_FACE = milvus_config.embedding_dim
DIM_SCENE = milvus_config.embedding_dim
DIM_STYLE = milvus_config.embedding_dim

FIELD_FACE = "embedding"
FIELD_SCENE = "embedding"
FIELD_STYLE = "embedding"
DEFAULT_TOP_K = 100


class MilvusManager:
    """兼容层：名称沿用 MilvusManager，实际驱动 Qdrant。"""

    def __init__(self):
        self._connected = False
        self.client: Optional[QdrantClient] = None

    def connect(self, alias: str = "default") -> str:  # noqa: ARG002
        if self._connected:
            return "Qdrant Ready"

        host = getattr(milvus_config, "host", "localhost")
        port = int(getattr(milvus_config, "port", 6333))
        self.client = QdrantClient(host=host, port=port)
        self._connected = True
        logger.info("Qdrant 连接成功: %s:%d", host, port)
        return self.server_version()

    def disconnect(self, alias: str = "default") -> None:  # noqa: ARG002
        self.client = None
        self._connected = False

    def server_version(self) -> str:
        if not self._connected:
            self.connect()
        assert self.client is not None
        return str(self.client.info().version)

    def create_collection(self, drop_if_exists: bool = False) -> Any:
        if not self._connected:
            self.connect()
        assert self.client is not None

        if drop_if_exists and self.client.collection_exists(COLLECTION_NAME):
            self.client.delete_collection(COLLECTION_NAME)

        if not self.client.collection_exists(COLLECTION_NAME):
            self.client.create_collection(
                collection_name=COLLECTION_NAME,
                vectors_config=models.VectorParams(
                    size=milvus_config.embedding_dim,
                    distance=models.Distance.COSINE,
                    on_disk=True,
                ),
                hnsw_config=models.HnswConfigDiff(on_disk=True),
                on_disk_payload=True,
            )

            for field, schema_type in [
                ("followers", models.PayloadSchemaType.INTEGER),
                ("gender", models.PayloadSchemaType.KEYWORD),
                ("region", models.PayloadSchemaType.KEYWORD),
            ]:
                self.client.create_payload_index(
                    COLLECTION_NAME,
                    field,
                    field_schema=schema_type,
                )

        return self.get_collection()

    def get_collection(self) -> models.CollectionInfo:
        if not self._connected:
            self.connect()
        assert self.client is not None
        return self.client.get_collection(COLLECTION_NAME)

    def collection_stats(self) -> Dict[str, Any]:
        info = self.get_collection()
        return {
            "name": COLLECTION_NAME,
            "num_entities": info.points_count or 0,
            "status": str(info.status),
        }

    def insert(self, data: List[Dict[str, Any]]) -> int:
        if not self._connected:
            self.connect()
        assert self.client is not None

        points: List[models.PointStruct] = []
        for item in data:
            vector = (
                item.get("embedding")
                or item.get(FIELD_STYLE)
                or item.get(FIELD_FACE)
                or item.get(FIELD_SCENE)
            )
            if vector is None:
                raise ValueError("insert 数据缺少 embedding 向量")

            points.append(
                models.PointStruct(
                    id=int(item["id"]),
                    vector=vector,
                    payload={
                        "followers": item.get("followers", 0),
                        "gender": item.get("gender", ""),
                        "region": item.get("region", ""),
                    },
                )
            )

        self.client.upsert(collection_name=COLLECTION_NAME, points=points)
        return len(points)

    def upsert(self, data: List[Dict[str, Any]]) -> int:
        return self.insert(data)

    def delete_by_ids(self, ids: List[int]) -> None:
        if not self._connected:
            self.connect()
        assert self.client is not None

        self.client.delete(
            collection_name=COLLECTION_NAME,
            points_selector=models.PointIdsList(points=ids),
        )

    def retrieve_by_ids(self, ids: List[int], with_vectors: bool = True) -> List[Any]:
        if not self._connected:
            self.connect()
        assert self.client is not None
        return self.client.retrieve(
            collection_name=COLLECTION_NAME,
            ids=ids,
            with_vectors=with_vectors,
            with_payload=True,
        )

    def load_collection(self) -> None:
        return None

    def release_collection(self) -> None:
        return None

    def hybrid_search(
        self,
        vector_field: str = FIELD_STYLE,  # noqa: ARG002
        query_vector: Optional[List[float]] = None,
        scalar_filters: Optional[Dict[str, Any]] = None,
        top_k: int = DEFAULT_TOP_K,
        **kwargs: Any,
    ) -> List[Dict[str, Any]]:
        if query_vector is None:
            raise ValueError("query_vector 不能为空")
        if not self._connected:
            self.connect()
        assert self.client is not None

        q_filter = self._build_filter_expr(scalar_filters or {})
        results = self.client.search(
            collection_name=COLLECTION_NAME,
            query_vector=query_vector,
            query_filter=q_filter,
            limit=top_k,
            with_payload=True,
        )

        formatted = []
        for hit in results:
            payload = hit.payload or {}
            formatted.append(
                {
                    "id": hit.id,
                    "score": float(hit.score),
                    "distance": 1.0 - float(hit.score),
                    "followers": payload.get("followers"),
                    "gender": payload.get("gender"),
                    "region": payload.get("region"),
                }
            )
        return formatted

    def multi_vector_search(
        self,
        query_vectors: Dict[str, List[float]],
        weights: Optional[Dict[str, float]] = None,
        scalar_filters: Optional[Dict[str, Any]] = None,
        top_k: int = DEFAULT_TOP_K,
    ) -> List[Dict[str, Any]]:
        del weights  # 单向量模式下忽略多向量权重
        vector = query_vectors.get("embedding") or query_vectors.get(FIELD_STYLE)
        if vector is None:
            # 兼容历史调用：取第一条 query vector
            vector = next(iter(query_vectors.values()))
        return self.hybrid_search(
            query_vector=vector,
            scalar_filters=scalar_filters,
            top_k=top_k,
        )

    @staticmethod
    def _build_filter_expr(filters: Dict[str, Any]) -> Optional[models.Filter]:
        if not filters:
            return None

        conditions = []
        if "region" in filters and filters["region"]:
            regions = filters["region"]
            if isinstance(regions, str):
                regions = [regions]
            conditions.append(
                models.FieldCondition(
                    key="region",
                    match=models.MatchAny(any=regions),
                )
            )

        if "gender" in filters and filters["gender"]:
            conditions.append(
                models.FieldCondition(
                    key="gender",
                    match=models.MatchValue(value=filters["gender"]),
                )
            )

        if "followers_min" in filters and filters["followers_min"] is not None:
            conditions.append(
                models.FieldCondition(
                    key="followers",
                    range=models.Range(gte=filters["followers_min"]),
                )
            )

        if "followers_max" in filters and filters["followers_max"] is not None:
            conditions.append(
                models.FieldCondition(
                    key="followers",
                    range=models.Range(lte=filters["followers_max"]),
                )
            )

        return models.Filter(must=conditions) if conditions else None


milvus_mgr = MilvusManager()
