"""Qdrant-backed Milvus compatibility layer."""

from __future__ import annotations

import logging
from typing import Any, Dict, Iterable, List, Optional, Sequence

from qdrant_client import QdrantClient
from qdrant_client.http.models import (
    Distance,
    FieldCondition,
    Filter,
    HasIdCondition,
    HnswConfigDiff,
    MatchAny,
    MatchValue,
    PayloadSchemaType,
    PointStruct,
    Range,
    VectorParams,
)

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
    """Milvus-compatible manager implemented on top of Qdrant."""

    def __init__(self) -> None:
        self._client: Optional[QdrantClient] = None
        self._connected = False

    def connect(self, alias: str = "default") -> str:
        _ = alias
        if self._client is None:
            if milvus_config.url:
                self._client = QdrantClient(url=milvus_config.url, api_key=milvus_config.api_key or None)
            else:
                self._client = QdrantClient(
                    host=milvus_config.host,
                    port=milvus_config.port,
                    api_key=milvus_config.api_key or None,
                )
        self._connected = True
        return self.server_version()

    def disconnect(self, alias: str = "default") -> None:
        _ = alias
        self._client = None
        self._connected = False

    def server_version(self) -> str:
        if self._client is None:
            self.connect()
        info = self._client.info()
        return str(getattr(info, "version", "qdrant"))

    def _client_or_raise(self) -> QdrantClient:
        if self._client is None:
            self.connect()
        if self._client is None:
            raise RuntimeError("Qdrant client unavailable")
        return self._client

    def create_collection(self, drop_if_exists: bool = False):
        client = self._client_or_raise()
        exists = client.collection_exists(COLLECTION_NAME)
        if exists and drop_if_exists:
            client.delete_collection(COLLECTION_NAME)
            exists = False
        if not exists:
            client.create_collection(
                collection_name=COLLECTION_NAME,
                vectors_config=VectorParams(
                    size=milvus_config.embedding_dim,
                    distance=Distance.COSINE,
                    on_disk=True,
                ),
                hnsw_config=HnswConfigDiff(on_disk=True),
                on_disk_payload=True,
            )
            client.create_payload_index(COLLECTION_NAME, "followers", PayloadSchemaType.INTEGER)
            client.create_payload_index(COLLECTION_NAME, "gender", PayloadSchemaType.KEYWORD)
            client.create_payload_index(COLLECTION_NAME, "region", PayloadSchemaType.KEYWORD)
        return client.get_collection(COLLECTION_NAME)

    def load_collection(self) -> None:
        return None

    def release_collection(self) -> None:
        return None

    def collection_stats(self) -> Dict[str, Any]:
        client = self._client_or_raise()
        info = client.get_collection(COLLECTION_NAME)
        return {
            "name": COLLECTION_NAME,
            "num_entities": int(getattr(info, "points_count", 0) or 0),
            "status": str(getattr(info, "status", "unknown")),
        }

    @staticmethod
    def _pick_embedding(item: Dict[str, Any]) -> List[float]:
        for key in ("embedding", "v_overall_style", "v_scene", "v_face"):
            value = item.get(key)
            if isinstance(value, list) and value:
                return [float(v) for v in value]
        raise ValueError("missing embedding vector")

    def _to_point(self, item: Dict[str, Any]) -> PointStruct:
        payload = {
            "followers": int(item.get("followers") or 0),
            "region": item.get("region") or "",
            "gender": item.get("gender") or "",
            "ad_ratio": float(item.get("ad_ratio") or 0.0),
        }
        return PointStruct(id=int(item["id"]), vector=self._pick_embedding(item), payload=payload)

    def insert(self, data: List[Dict[str, Any]]) -> int:
        if not data:
            return 0
        client = self._client_or_raise()
        client.upsert(COLLECTION_NAME, points=[self._to_point(item) for item in data], wait=True)
        return len(data)

    def upsert(self, data: List[Dict[str, Any]]) -> int:
        return self.insert(data)

    def retrieve_by_ids(self, ids: Sequence[int]) -> List[Dict[str, Any]]:
        if not ids:
            return []
        client = self._client_or_raise()
        points = client.retrieve(COLLECTION_NAME, ids=[int(i) for i in ids], with_vectors=True, with_payload=True)
        output: List[Dict[str, Any]] = []
        for point in points:
            vector = point.vector
            if isinstance(vector, dict):
                vector = vector.get("embedding")
            output.append(
                {
                    "id": int(point.id),
                    "embedding": list(vector or []),
                    "followers": (point.payload or {}).get("followers"),
                    "region": (point.payload or {}).get("region"),
                    "gender": (point.payload or {}).get("gender"),
                    "ad_ratio": (point.payload or {}).get("ad_ratio"),
                }
            )
        return output

    def get_entities_by_ids(self, ids: Sequence[int], output_fields: Optional[Sequence[str]] = None) -> List[Dict[str, Any]]:
        rows = self.retrieve_by_ids(ids)
        if not output_fields:
            return rows
        filtered: List[Dict[str, Any]] = []
        for row in rows:
            item = {"id": row["id"]}
            for field in output_fields:
                mapped = "embedding" if field in {"v_face", "v_scene", "v_overall_style"} else field
                item[field] = row.get(mapped)
            filtered.append(item)
        return filtered

    @staticmethod
    def _build_filter(scalar_filters: Optional[Dict[str, Any]]) -> Optional[Filter]:
        if not scalar_filters:
            return None
        must: List[FieldCondition] = []
        must_not: List[Any] = []

        region = scalar_filters.get("region")
        if isinstance(region, list) and region:
            must.append(FieldCondition(key="region", match=MatchAny(any=[str(x) for x in region])))
        elif isinstance(region, str) and region:
            must.append(FieldCondition(key="region", match=MatchValue(value=region)))

        gender = scalar_filters.get("gender")
        if isinstance(gender, str) and gender:
            must.append(FieldCondition(key="gender", match=MatchValue(value=gender)))

        f_min = scalar_filters.get("followers_min")
        f_max = scalar_filters.get("followers_max")
        if f_min is not None or f_max is not None:
            must.append(FieldCondition(key="followers", range=Range(gte=f_min, lte=f_max)))

        excluded = scalar_filters.get("id_not_in")
        if isinstance(excluded, Iterable):
            excluded_ids = [int(v) for v in excluded]
            if excluded_ids:
                must_not.append(HasIdCondition(has_id=excluded_ids))

        if not must and not must_not:
            return None
        return Filter(must=must or None, must_not=must_not or None)

    def hybrid_search(
        self,
        *,
        vector_field: str = FIELD_STYLE,
        query_vector: List[float],
        scalar_filters: Optional[Dict[str, Any]] = None,
        top_k: int = DEFAULT_TOP_K,
    ) -> List[Dict[str, Any]]:
        _ = vector_field
        client = self._client_or_raise()
        query_filter = self._build_filter(scalar_filters)
        points = client.query_points(
            collection_name=COLLECTION_NAME,
            query=query_vector,
            query_filter=query_filter,
            limit=top_k,
            with_payload=True,
            with_vectors=False,
        ).points
        return [
            {
                "id": int(point.id),
                "score": float(point.score),
                "distance": 1.0 - float(point.score),
                "followers": (point.payload or {}).get("followers"),
                "region": (point.payload or {}).get("region"),
                "gender": (point.payload or {}).get("gender"),
                "ad_ratio": (point.payload or {}).get("ad_ratio"),
            }
            for point in points
        ]


milvus_mgr = MilvusManager()
