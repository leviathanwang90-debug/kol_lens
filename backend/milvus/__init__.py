"""
Σ.Match Milvus 向量数据库管理模块
Sprint 1 · Task 1.2.1 ~ 1.2.3

功能:
  - Collection Schema 定义与创建
  - 三向量字段索引管理 (v_face / v_scene / v_overall_style)
  - Hybrid Search 混合检索封装 (标量过滤 + 向量相似度)
  - 数据插入与批量同步
"""

import logging
from typing import Any, Dict, List, Optional, Tuple, Union

from pymilvus import (
    Collection,
    CollectionSchema,
    DataType,
    FieldSchema,
    MilvusException,
    connections,
    utility,
)

from config import milvus_config

logger = logging.getLogger(__name__)


# ============================================================
# Schema 定义常量
# ============================================================

COLLECTION_NAME = milvus_config.collection_name

# 向量维度
DIM_FACE = milvus_config.face_dim       # 512 (InsightFace)
DIM_SCENE = milvus_config.scene_dim     # 768 (CLIP)
DIM_STYLE = milvus_config.style_dim     # 768 (时序融合)

# 向量字段名
FIELD_FACE = "v_face"
FIELD_SCENE = "v_scene"
FIELD_STYLE = "v_overall_style"

# 默认检索参数
DEFAULT_TOP_K = 100
DEFAULT_METRIC = "COSINE"


class MilvusManager:
    """Milvus 向量数据库管理器"""

    def __init__(self):
        self._collection: Optional[Collection] = None
        self._connected = False

    # ================================================================
    # 连接管理
    # ================================================================

    def connect(self, alias: str = "default") -> str:
        """连接 Milvus 服务"""
        if self._connected:
            return self.server_version()

        connections.connect(
            alias=alias,
            host=milvus_config.host,
            port=milvus_config.port,
        )
        self._connected = True
        version = self.server_version()
        logger.info("Milvus 连接成功: %s:%d (版本: %s)",
                     milvus_config.host, milvus_config.port, version)
        return version

    def disconnect(self, alias: str = "default") -> None:
        """断开 Milvus 连接"""
        connections.disconnect(alias)
        self._connected = False
        self._collection = None
        logger.info("Milvus 连接已断开")

    def server_version(self) -> str:
        """获取服务器版本"""
        return utility.get_server_version()

    # ================================================================
    # Collection 管理
    # ================================================================

    def _build_schema(self) -> CollectionSchema:
        """构建 Collection Schema

        字段清单:
          - id (INT64, PK)           映射 PostgreSQL influencer_basics.internal_id
          - followers (INT64)         标量索引: 粉丝数
          - region (VARCHAR)          标量索引: 地区
          - gender (VARCHAR)          标量索引: 性别
          - ad_ratio (FLOAT)          标量索引: 商单比例
          - v_face (FLOAT_VECTOR)     InsightFace 人脸向量 (512维)
          - v_scene (FLOAT_VECTOR)    CLIP 场景向量 (768维)
          - v_overall_style (FLOAT_VECTOR)  时序融合风格向量 (768维)
        """
        fields = [
            FieldSchema(
                name="id",
                dtype=DataType.INT64,
                is_primary=True,
                auto_id=False,
                description="映射 PostgreSQL influencer_basics.internal_id",
            ),
            FieldSchema(
                name="followers",
                dtype=DataType.INT64,
                description="粉丝数（标量过滤用）",
            ),
            FieldSchema(
                name="region",
                dtype=DataType.VARCHAR,
                max_length=64,
                description="地区（标量过滤用）",
            ),
            FieldSchema(
                name="gender",
                dtype=DataType.VARCHAR,
                max_length=8,
                description="性别（标量过滤用）",
            ),
            FieldSchema(
                name="ad_ratio",
                dtype=DataType.FLOAT,
                description="商单比例（标量过滤用）",
            ),
            FieldSchema(
                name=FIELD_FACE,
                dtype=DataType.FLOAT_VECTOR,
                dim=DIM_FACE,
                description="InsightFace 人脸特征向量 (512维)",
            ),
            FieldSchema(
                name=FIELD_SCENE,
                dtype=DataType.FLOAT_VECTOR,
                dim=DIM_SCENE,
                description="CLIP 场景特征向量 (768维)",
            ),
            FieldSchema(
                name=FIELD_STYLE,
                dtype=DataType.FLOAT_VECTOR,
                dim=DIM_STYLE,
                description="时序融合风格向量 (768维)",
            ),
        ]

        schema = CollectionSchema(
            fields=fields,
            description="Σ.Match 达人多模态向量 Collection — 支持三维度混合检索",
        )
        return schema

    def create_collection(self, drop_if_exists: bool = False) -> Collection:
        """创建 Collection

        Args:
            drop_if_exists: 如果 Collection 已存在，是否先删除再重建

        Returns:
            Collection 实例
        """
        if not self._connected:
            self.connect()

        if utility.has_collection(COLLECTION_NAME):
            if drop_if_exists:
                logger.warning("删除已存在的 Collection: %s", COLLECTION_NAME)
                utility.drop_collection(COLLECTION_NAME)
            else:
                logger.info("Collection 已存在: %s", COLLECTION_NAME)
                self._collection = Collection(COLLECTION_NAME)
                return self._collection

        schema = self._build_schema()
        self._collection = Collection(
            name=COLLECTION_NAME,
            schema=schema,
            consistency_level="Strong",
        )
        logger.info("Collection 创建成功: %s", COLLECTION_NAME)

        # 创建索引
        self._create_indexes()

        return self._collection

    def _create_indexes(self) -> None:
        """为向量字段和标量字段创建索引

        开发阶段使用 IVF_FLAT（便于调试），
        Sprint 6 优化阶段切换为 HNSW。
        """
        if self._collection is None:
            raise RuntimeError("Collection 未初始化")

        # 向量索引: IVF_FLAT (开发阶段)
        vector_index_params = {
            "index_type": "IVF_FLAT",
            "metric_type": DEFAULT_METRIC,
            "params": {"nlist": 128},
        }

        for field_name in [FIELD_FACE, FIELD_SCENE, FIELD_STYLE]:
            self._collection.create_index(
                field_name=field_name,
                index_params=vector_index_params,
                index_name=f"idx_{field_name}",
            )
            logger.info("向量索引创建成功: %s (IVF_FLAT, nlist=128)", field_name)

        logger.info("全部索引创建完成")

    def upgrade_to_hnsw(self, ef_construction: int = 256, M: int = 16) -> None:
        """将向量索引从 IVF_FLAT 升级为 HNSW（Sprint 6 优化用）"""
        if self._collection is None:
            self.get_collection()

        hnsw_params = {
            "index_type": "HNSW",
            "metric_type": DEFAULT_METRIC,
            "params": {"efConstruction": ef_construction, "M": M},
        }

        for field_name in [FIELD_FACE, FIELD_SCENE, FIELD_STYLE]:
            self._collection.drop_index(index_name=f"idx_{field_name}")
            self._collection.create_index(
                field_name=field_name,
                index_params=hnsw_params,
                index_name=f"idx_{field_name}",
            )
            logger.info("向量索引升级为 HNSW: %s (ef=%d, M=%d)",
                         field_name, ef_construction, M)

    def get_collection(self) -> Collection:
        """获取 Collection 实例（懒加载）"""
        if self._collection is None:
            if not self._connected:
                self.connect()
            if not utility.has_collection(COLLECTION_NAME):
                raise RuntimeError(f"Collection 不存在: {COLLECTION_NAME}")
            self._collection = Collection(COLLECTION_NAME)
        return self._collection

    def load_collection(self) -> None:
        """将 Collection 加载到内存（检索前必须调用）"""
        col = self.get_collection()
        col.load()
        logger.info("Collection 已加载到内存: %s", COLLECTION_NAME)

    def release_collection(self) -> None:
        """从内存释放 Collection"""
        col = self.get_collection()
        col.release()
        logger.info("Collection 已从内存释放: %s", COLLECTION_NAME)

    def collection_stats(self) -> Dict[str, Any]:
        """获取 Collection 统计信息"""
        col = self.get_collection()
        col.flush()
        return {
            "name": COLLECTION_NAME,
            "num_entities": col.num_entities,
            "schema": str(col.schema),
            "indexes": [str(idx) for idx in col.indexes],
        }

    # ================================================================
    # 数据写入
    # ================================================================

    def insert(self, data: List[Dict[str, Any]]) -> int:
        """批量插入数据

        Args:
            data: 字典列表，每个字典包含全部字段

        Returns:
            插入的实体数量
        """
        col = self.get_collection()

        # 转换为列式存储
        ids = [d["id"] for d in data]
        followers = [d["followers"] for d in data]
        regions = [d["region"] for d in data]
        genders = [d["gender"] for d in data]
        ad_ratios = [d["ad_ratio"] for d in data]
        v_faces = [d[FIELD_FACE] for d in data]
        v_scenes = [d[FIELD_SCENE] for d in data]
        v_styles = [d[FIELD_STYLE] for d in data]

        insert_data = [
            ids, followers, regions, genders, ad_ratios,
            v_faces, v_scenes, v_styles,
        ]

        result = col.insert(insert_data)
        col.flush()

        count = result.insert_count
        logger.info("插入 %d 条向量数据到 %s", count, COLLECTION_NAME)
        return count

    def upsert(self, data: List[Dict[str, Any]]) -> int:
        """批量更新或插入数据（Milvus 2.4+ 支持）"""
        col = self.get_collection()

        ids = [d["id"] for d in data]
        followers = [d["followers"] for d in data]
        regions = [d["region"] for d in data]
        genders = [d["gender"] for d in data]
        ad_ratios = [d["ad_ratio"] for d in data]
        v_faces = [d[FIELD_FACE] for d in data]
        v_scenes = [d[FIELD_SCENE] for d in data]
        v_styles = [d[FIELD_STYLE] for d in data]

        upsert_data = [
            ids, followers, regions, genders, ad_ratios,
            v_faces, v_scenes, v_styles,
        ]

        result = col.upsert(upsert_data)
        col.flush()

        count = result.upsert_count
        logger.info("Upsert %d 条向量数据到 %s", count, COLLECTION_NAME)
        return count

    def delete_by_ids(self, ids: List[int]) -> None:
        """按 ID 删除数据"""
        col = self.get_collection()
        expr = f"id in {ids}"
        col.delete(expr)
        col.flush()
        logger.info("删除 %d 条向量数据", len(ids))

    def get_entities_by_ids(
        self,
        ids: List[int],
        output_fields: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        """按 ID 批量读取实体字段，支持向量字段输出。"""
        if not ids:
            return []
        col = self.get_collection()
        fields = output_fields or [
            "id",
            "followers",
            "region",
            "gender",
            "ad_ratio",
            FIELD_FACE,
            FIELD_SCENE,
            FIELD_STYLE,
        ]
        expr = f"id in {list(dict.fromkeys(int(item) for item in ids))}"
        rows = col.query(expr=expr, output_fields=fields, consistency_level="Strong")
        results = [dict(row) for row in rows]
        order_map = {int(value): index for index, value in enumerate(ids)}
        results.sort(key=lambda item: order_map.get(int(item.get("id", -1)), len(order_map)))
        return results

    # ================================================================
    # 混合检索 (Hybrid Search)
    # ================================================================

    def hybrid_search(
        self,
        vector_field: str = FIELD_STYLE,
        query_vector: Optional[List[float]] = None,
        scalar_filters: Optional[Dict[str, Any]] = None,
        top_k: int = DEFAULT_TOP_K,
        metric_type: str = DEFAULT_METRIC,
        search_params: Optional[Dict] = None,
        output_fields: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        """混合检索: 标量过滤 + 向量相似度

        Args:
            vector_field: 使用哪个向量字段检索
                - "v_overall_style" (默认): 综合风格匹配
                - "v_face": 人脸相似度匹配
                - "v_scene": 场景风格匹配
            query_vector: 查询向量
            scalar_filters: 标量过滤条件，支持的键:
                - region: List[str]   地区列表 (IN 查询)
                - gender: str         性别
                - followers_min: int  最小粉丝数
                - followers_max: int  最大粉丝数
                - ad_ratio_max: float 最大商单比例
            top_k: 返回数量
            metric_type: 距离度量 (COSINE / L2 / IP)
            search_params: 自定义检索参数
            output_fields: 需要返回的标量字段列表

        Returns:
            检索结果列表，每个元素包含 id, distance 和请求的标量字段
        """
        col = self.get_collection()

        # 验证向量字段
        valid_fields = {FIELD_FACE, FIELD_SCENE, FIELD_STYLE}
        if vector_field not in valid_fields:
            raise ValueError(f"无效的向量字段: {vector_field}，可选: {valid_fields}")

        # 验证查询向量维度
        expected_dim = {
            FIELD_FACE: DIM_FACE,
            FIELD_SCENE: DIM_SCENE,
            FIELD_STYLE: DIM_STYLE,
        }[vector_field]

        if query_vector and len(query_vector) != expected_dim:
            raise ValueError(
                f"查询向量维度不匹配: 期望 {expected_dim}，实际 {len(query_vector)}"
            )

        # 构建标量过滤表达式
        expr = self._build_filter_expr(scalar_filters or {})

        # 检索参数
        if search_params is None:
            search_params = {"metric_type": metric_type, "params": {"nprobe": 16}}

        # 输出字段
        if output_fields is None:
            output_fields = ["followers", "region", "gender", "ad_ratio"]

        # 执行检索
        results = col.search(
            data=[query_vector],
            anns_field=vector_field,
            param=search_params,
            limit=top_k,
            expr=expr if expr else None,
            output_fields=output_fields,
            consistency_level="Strong",
        )

        # 格式化结果
        formatted = []
        for hits in results:
            for hit in hits:
                item = {
                    "id": hit.id,
                    "distance": hit.distance,
                    "score": 1.0 - hit.distance if metric_type == "COSINE" else hit.distance,
                }
                # 附加标量字段
                for field in output_fields:
                    item[field] = hit.entity.get(field)
                formatted.append(item)

        logger.info(
            "Hybrid Search 完成: field=%s, filters=%s, top_k=%d, 返回 %d 条",
            vector_field, expr or "无", top_k, len(formatted),
        )
        return formatted

    def multi_vector_search(
        self,
        query_vectors: Dict[str, List[float]],
        weights: Optional[Dict[str, float]] = None,
        scalar_filters: Optional[Dict[str, Any]] = None,
        top_k: int = DEFAULT_TOP_K,
    ) -> List[Dict[str, Any]]:
        """多向量加权检索

        同时在多个向量字段上检索，按权重融合得分。
        这是 Sprint 3 Hybrid Ranking 的基础。

        Args:
            query_vectors: {字段名: 查询向量} 字典
            weights: {字段名: 权重} 字典，默认等权
            scalar_filters: 标量过滤条件
            top_k: 最终返回数量

        Returns:
            融合排序后的结果列表
        """
        if weights is None:
            weights = {f: 1.0 / len(query_vectors) for f in query_vectors}

        # 归一化权重
        total_weight = sum(weights.values())
        weights = {f: w / total_weight for f, w in weights.items()}

        # 对每个向量字段分别检索
        all_results: Dict[int, Dict[str, Any]] = {}

        for field_name, query_vec in query_vectors.items():
            w = weights.get(field_name, 0)
            if w <= 0:
                continue

            results = self.hybrid_search(
                vector_field=field_name,
                query_vector=query_vec,
                scalar_filters=scalar_filters,
                top_k=top_k * 2,  # 多取一些用于融合
            )

            for r in results:
                rid = r["id"]
                if rid not in all_results:
                    all_results[rid] = {
                        "id": rid,
                        "weighted_score": 0.0,
                        "scores_detail": {},
                    }
                    # 复制标量字段
                    for k, v in r.items():
                        if k not in ("id", "distance", "score"):
                            all_results[rid][k] = v

                all_results[rid]["scores_detail"][field_name] = r["score"]
                all_results[rid]["weighted_score"] += r["score"] * w

        # 按加权得分排序
        sorted_results = sorted(
            all_results.values(),
            key=lambda x: x["weighted_score"],
            reverse=True,
        )

        return sorted_results[:top_k]

    @staticmethod
    def _build_filter_expr(filters: Dict[str, Any]) -> str:
        """构建 Milvus 标量过滤表达式

        支持的过滤条件:
          - region: List[str]      → region in ["上海", "杭州"]
          - gender: str            → gender == "女"
          - followers_min: int     → followers >= 50000
          - followers_max: int     → followers <= 500000
          - ad_ratio_max: float    → ad_ratio < 0.3
          - id_not_in: List[int]   → id not in [1, 2, 3]
        """
        conditions = []

        if "region" in filters and filters["region"]:
            regions = filters["region"]
            if isinstance(regions, str):
                regions = [regions]
            quoted = ", ".join(f'"{r}"' for r in regions)
            conditions.append(f"region in [{quoted}]")

        if "gender" in filters and filters["gender"]:
            conditions.append(f'gender == "{filters["gender"]}"')

        if "followers_min" in filters and filters["followers_min"] is not None:
            conditions.append(f"followers >= {filters['followers_min']}")

        if "followers_max" in filters and filters["followers_max"] is not None:
            conditions.append(f"followers <= {filters['followers_max']}")

        if "ad_ratio_max" in filters and filters["ad_ratio_max"] is not None:
            conditions.append(f"ad_ratio < {filters['ad_ratio_max']}")

        if "id_not_in" in filters and filters["id_not_in"]:
            conditions.append(f"id not in {filters['id_not_in']}")

        return " and ".join(conditions)


# 全局单例
milvus_mgr = MilvusManager()
