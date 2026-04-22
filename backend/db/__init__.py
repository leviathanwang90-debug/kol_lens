"""
Σ.Match PostgreSQL 数据库连接管理
提供同步连接池和常用 CRUD 操作封装。
"""

import json
import logging
from contextlib import contextmanager
from typing import Any, Dict, List, Optional, Tuple

import psycopg2
import psycopg2.extras
from psycopg2.pool import ThreadedConnectionPool

from config import pg_config

logger = logging.getLogger(__name__)


class Database:
    """PostgreSQL 连接池管理器"""

    def __init__(self, min_conn: int = 2, max_conn: int = 10):
        self._pool: Optional[ThreadedConnectionPool] = None
        self._min_conn = min_conn
        self._max_conn = max_conn

    def connect(self) -> None:
        """初始化连接池"""
        if self._pool is not None:
            return
        self._pool = ThreadedConnectionPool(
            minconn=self._min_conn,
            maxconn=self._max_conn,
            host=pg_config.host,
            port=pg_config.port,
            dbname=pg_config.database,
            user=pg_config.user,
            password=pg_config.password,
        )
        logger.info(
            "PostgreSQL 连接池已初始化: %s@%s:%d/%s (min=%d, max=%d)",
            pg_config.user, pg_config.host, pg_config.port,
            pg_config.database, self._min_conn, self._max_conn,
        )

    def close(self) -> None:
        """关闭连接池"""
        if self._pool:
            self._pool.closeall()
            self._pool = None
            logger.info("PostgreSQL 连接池已关闭")

    @contextmanager
    def get_conn(self):
        """获取数据库连接（上下文管理器）"""
        if self._pool is None:
            self.connect()
        conn = self._pool.getconn()
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            self._pool.putconn(conn)

    @contextmanager
    def get_cursor(self, cursor_factory=None):
        """获取游标（上下文管理器）"""
        factory = cursor_factory or psycopg2.extras.RealDictCursor
        with self.get_conn() as conn:
            with conn.cursor(cursor_factory=factory) as cur:
                yield cur

    # ================================================================
    # influencer_basics CRUD
    # ================================================================

    def insert_influencer(self, data: Dict[str, Any]) -> int:
        """插入达人基础信息，返回 internal_id"""
        sql = """
            INSERT INTO influencer_basics
                (red_id, nickname, avatar_url, gender, region, followers,
                 likes, collections, notes_count, ad_ratio_30d,
                 latest_note_time, tags, pricing)
            VALUES
                (%(red_id)s, %(nickname)s, %(avatar_url)s, %(gender)s,
                 %(region)s, %(followers)s, %(likes)s, %(collections)s,
                 %(notes_count)s, %(ad_ratio_30d)s, %(latest_note_time)s,
                 %(tags)s::jsonb, %(pricing)s::jsonb)
            ON CONFLICT (red_id) DO UPDATE SET
                nickname = EXCLUDED.nickname,
                avatar_url = EXCLUDED.avatar_url,
                followers = EXCLUDED.followers,
                likes = EXCLUDED.likes,
                collections = EXCLUDED.collections,
                notes_count = EXCLUDED.notes_count,
                ad_ratio_30d = EXCLUDED.ad_ratio_30d,
                latest_note_time = EXCLUDED.latest_note_time,
                tags = EXCLUDED.tags,
                pricing = EXCLUDED.pricing
            RETURNING internal_id
        """
        # 确保 JSONB 字段是字符串
        data = dict(data)
        if isinstance(data.get("tags"), (list, dict)):
            data["tags"] = json.dumps(data["tags"], ensure_ascii=False)
        if isinstance(data.get("pricing"), (list, dict)):
            data["pricing"] = json.dumps(data["pricing"], ensure_ascii=False)

        with self.get_cursor() as cur:
            cur.execute(sql, data)
            row = cur.fetchone()
            return row["internal_id"]

    def get_influencer_by_id(self, internal_id: int) -> Optional[Dict]:
        """通过 internal_id 查询达人"""
        sql = "SELECT * FROM influencer_basics WHERE internal_id = %s"
        with self.get_cursor() as cur:
            cur.execute(sql, (internal_id,))
            return cur.fetchone()

    def get_influencer_by_red_id(self, red_id: str) -> Optional[Dict]:
        """通过小红书号查询达人"""
        sql = "SELECT * FROM influencer_basics WHERE red_id = %s"
        with self.get_cursor() as cur:
            cur.execute(sql, (red_id,))
            return cur.fetchone()

    def search_influencers(
        self,
        region: Optional[str] = None,
        followers_min: Optional[int] = None,
        followers_max: Optional[int] = None,
        tags: Optional[List[str]] = None,
        gender: Optional[str] = None,
        limit: int = 20,
        offset: int = 0,
        sort_by: str = "followers",
        sort_order: str = "DESC",
    ) -> Tuple[List[Dict], int]:
        """多维度筛选达人列表，返回 (结果列表, 总数)"""
        conditions = []
        params: List[Any] = []

        if region:
            conditions.append("region = %s")
            params.append(region)
        if followers_min is not None:
            conditions.append("followers >= %s")
            params.append(followers_min)
        if followers_max is not None:
            conditions.append("followers <= %s")
            params.append(followers_max)
        if gender:
            conditions.append("gender = %s")
            params.append(gender)
        if tags:
            # JSONB 包含查询: tags @> '["穿搭"]'
            conditions.append("tags @> %s::jsonb")
            params.append(json.dumps(tags, ensure_ascii=False))

        where_clause = " AND ".join(conditions) if conditions else "1=1"

        # 白名单校验排序字段
        allowed_sort = {"followers", "likes", "collections", "ad_ratio_30d", "created_at"}
        if sort_by not in allowed_sort:
            sort_by = "followers"
        if sort_order.upper() not in ("ASC", "DESC"):
            sort_order = "DESC"

        # 查询总数
        count_sql = f"SELECT COUNT(*) AS total FROM influencer_basics WHERE {where_clause}"
        with self.get_cursor() as cur:
            cur.execute(count_sql, params)
            total = cur.fetchone()["total"]

        # 查询数据
        data_sql = f"""
            SELECT * FROM influencer_basics
            WHERE {where_clause}
            ORDER BY {sort_by} {sort_order}
            LIMIT %s OFFSET %s
        """
        with self.get_cursor() as cur:
            cur.execute(data_sql, params + [limit, offset])
            rows = cur.fetchall()

        return [dict(r) for r in rows], total

    # ================================================================
    # campaign_history CRUD
    # ================================================================

    def create_campaign(self, data: Dict[str, Any]) -> int:
        """创建寻星任务，返回 campaign_id"""
        sql = """
            INSERT INTO campaign_history
                (brand_name, spu_name, operator_id, operator_role,
                 user_id, spu_id, intent_snapshot, dynamic_intent_vector, status)
            VALUES
                (%(brand_name)s, %(spu_name)s, %(operator_id)s,
                 %(operator_role)s, %(user_id)s, %(spu_id)s,
                 %(intent_snapshot)s::jsonb, %(dynamic_intent_vector)s::jsonb, 'active')
            RETURNING campaign_id
        """
        data = dict(data)
        if isinstance(data.get("intent_snapshot"), (dict, list)):
            data["intent_snapshot"] = json.dumps(data["intent_snapshot"], ensure_ascii=False)
        if isinstance(data.get("dynamic_intent_vector"), (dict, list)):
            data["dynamic_intent_vector"] = json.dumps(data["dynamic_intent_vector"], ensure_ascii=False)
        data.setdefault("user_id", None)
        data.setdefault("spu_id", None)
        data.setdefault("dynamic_intent_vector", None)

        with self.get_cursor() as cur:
            cur.execute(sql, data)
            return cur.fetchone()["campaign_id"]

    def commit_campaign(
        self,
        campaign_id: int,
        selected_ids: List[int],
        rejected_ids: List[int],
        pending_ids: List[int],
        query_vector: Optional[List[float]] = None,
    ) -> None:
        """确认入库：更新任务状态为 committed"""
        sql = """
            UPDATE campaign_history SET
                selected_influencer_ids = %s::jsonb,
                rejected_influencer_ids = %s::jsonb,
                pending_influencer_ids = %s::jsonb,
                query_vector_snapshot = %s::jsonb,
                dynamic_intent_vector = COALESCE(%s::jsonb, dynamic_intent_vector),
                status = 'committed',
                committed_at = NOW()
            WHERE campaign_id = %s
        """
        with self.get_cursor() as cur:
            cur.execute(sql, (
                json.dumps(selected_ids),
                json.dumps(rejected_ids),
                json.dumps(pending_ids),
                json.dumps(query_vector) if query_vector else None,
                json.dumps(query_vector) if query_vector else None,
                campaign_id,
            ))

    def get_brand_spu_base_vector(self, spu_id: int) -> Optional[List[float]]:
        sql = "SELECT base_vector FROM brand_spus WHERE spu_id = %s"
        with self.get_cursor() as cur:
            cur.execute(sql, (spu_id,))
            row = cur.fetchone()
            if not row:
                return None
            vector = row.get("base_vector")
            if isinstance(vector, str):
                try:
                    vector = json.loads(vector)
                except json.JSONDecodeError:
                    return None
            return vector

    def get_brand_spu_record(self, spu_id: int) -> Optional[Dict]:
        sql = """
            SELECT spu_id, brand_name, spu_name, base_vector, kol_count
            FROM brand_spus
            WHERE spu_id = %s
        """
        with self.get_cursor() as cur:
            cur.execute(sql, (spu_id,))
            row = cur.fetchone()
            return dict(row) if row else None

    def get_brand_spu_by_name(self, brand_name: str, spu_name: str) -> Optional[Dict]:
        sql = """
            SELECT spu_id, brand_name, spu_name, base_vector, kol_count
            FROM brand_spus
            WHERE brand_name = %s AND spu_name = %s
        """
        with self.get_cursor() as cur:
            cur.execute(sql, (brand_name, spu_name))
            row = cur.fetchone()
            return dict(row) if row else None

    def ensure_brand_spu(self, brand_name: str, spu_name: str) -> int:
        sql = """
            INSERT INTO brand_spus (brand_name, spu_name, kol_count)
            VALUES (%s, %s, 0)
            ON CONFLICT (brand_name, spu_name) DO UPDATE
            SET updated_at = NOW()
            RETURNING spu_id
        """
        with self.get_cursor() as cur:
            cur.execute(sql, (brand_name, spu_name))
            return int(cur.fetchone()["spu_id"])

    def create_campaign_from_spu(self, user_id: int, spu_id: int, initial_vector: List[float]) -> int:
        sql = """
            INSERT INTO campaign_history
                (brand_name, spu_name, operator_id, operator_role,
                 user_id, spu_id, dynamic_intent_vector, status)
            SELECT
                bs.brand_name,
                bs.spu_name,
                %s,
                2,
                %s,
                bs.spu_id,
                %s::jsonb,
                'active'
            FROM brand_spus bs
            WHERE bs.spu_id = %s
            RETURNING campaign_id
        """
        with self.get_cursor() as cur:
            cur.execute(sql, (user_id, user_id, json.dumps(initial_vector), spu_id))
            row = cur.fetchone()
            if not row:
                raise ValueError(f"SPU 不存在: {spu_id}")
            return row["campaign_id"]

    def get_campaign_intent_vector(self, campaign_id: int) -> Optional[List[float]]:
        sql = "SELECT dynamic_intent_vector FROM campaign_history WHERE campaign_id = %s"
        with self.get_cursor() as cur:
            cur.execute(sql, (campaign_id,))
            row = cur.fetchone()
            if not row:
                return None
            vector = row.get("dynamic_intent_vector")
            if isinstance(vector, str):
                try:
                    vector = json.loads(vector)
                except json.JSONDecodeError:
                    return None
            return vector

    def update_campaign_dynamic_vector(self, campaign_id: int, vector: List[float]) -> None:
        sql = """
            UPDATE campaign_history
            SET dynamic_intent_vector = %s::jsonb
            WHERE campaign_id = %s
        """
        with self.get_cursor() as cur:
            cur.execute(sql, (json.dumps(vector), campaign_id))

    def get_influencer_profiles_by_ids(self, ids: List[int]) -> List[Dict]:
        if not ids:
            return []
        sql = """
            SELECT * FROM v_influencer_profile
            WHERE internal_id = ANY(%s)
        """
        with self.get_cursor() as cur:
            cur.execute(sql, (ids,))
            return [dict(row) for row in cur.fetchall()]

    def get_brand_collaboration_influencer_ids(self, spu_id: int) -> List[int]:
        sql = """
            SELECT influencer_id
            FROM collaborations
            WHERE spu_id = %s AND influencer_id IS NOT NULL
            ORDER BY collaboration_date DESC NULLS LAST
        """
        with self.get_cursor() as cur:
            cur.execute(sql, (spu_id,))
            return [int(row["influencer_id"]) for row in cur.fetchall()]

    def update_brand_spu_base_vector(self, spu_id: int, vector: List[float], kol_count: Optional[int] = None) -> None:
        sql = """
            UPDATE brand_spus
            SET base_vector = %s::jsonb,
                kol_count = COALESCE(%s, kol_count),
                updated_at = NOW()
            WHERE spu_id = %s
        """
        with self.get_cursor() as cur:
            cur.execute(sql, (json.dumps(vector), kol_count, spu_id))

    def list_brand_spus(self) -> List[Dict]:
        sql = "SELECT spu_id, brand_name, spu_name, kol_count FROM brand_spus ORDER BY spu_id ASC"
        with self.get_cursor() as cur:
            cur.execute(sql)
            return [dict(row) for row in cur.fetchall()]

    def get_existing_collaboration_ids(self, spu_id: int, influencer_ids: List[int]) -> List[int]:
        if not influencer_ids:
            return []
        sql = """
            SELECT influencer_id
            FROM collaborations
            WHERE spu_id = %s
              AND influencer_id = ANY(%s)
        """
        with self.get_cursor() as cur:
            cur.execute(sql, (spu_id, influencer_ids))
            return [int(row["influencer_id"]) for row in cur.fetchall()]

    def insert_collaborations(self, spu_id: int, influencer_ids: List[int]) -> int:
        if not influencer_ids:
            return 0
        sql = """
            INSERT INTO collaborations (influencer_id, spu_id, collaboration_date)
            SELECT UNNEST(%s::int[]), %s, CURRENT_DATE
            ON CONFLICT (spu_id, influencer_id) DO NOTHING
        """
        with self.get_cursor() as cur:
            cur.execute(sql, (influencer_ids, spu_id))
            return cur.rowcount or 0

    def get_campaigns_by_brand(
        self, brand_name: str, spu_name: Optional[str] = None
    ) -> List[Dict]:
        """查询品牌+SPU 的历史任务"""
        if spu_name:
            sql = """
                SELECT * FROM campaign_history
                WHERE brand_name = %s AND spu_name = %s
                ORDER BY created_at DESC
            """
            params = (brand_name, spu_name)
        else:
            sql = """
                SELECT * FROM campaign_history
                WHERE brand_name = %s
                ORDER BY created_at DESC
            """
            params = (brand_name,)

        with self.get_cursor() as cur:
            cur.execute(sql, params)
            return [dict(r) for r in cur.fetchall()]

    # ================================================================
    # export_dictionary CRUD
    # ================================================================

    def upsert_mapping(
        self, user_input_header: str, mapped_standard_key: str,
        confidence: float = 1.00, source: str = "user"
    ) -> int:
        """插入或更新映射关系（UPSERT），返回 mapping_id"""
        sql = """
            INSERT INTO export_dictionary
                (user_input_header, mapped_standard_key, confidence, source)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (user_input_header, mapped_standard_key) DO UPDATE SET
                usage_count = export_dictionary.usage_count + 1,
                confidence = GREATEST(export_dictionary.confidence, EXCLUDED.confidence),
                source = EXCLUDED.source
            RETURNING mapping_id
        """
        with self.get_cursor() as cur:
            cur.execute(sql, (user_input_header, mapped_standard_key, confidence, source))
            return cur.fetchone()["mapping_id"]

    def suggest_mappings(self, user_input_header: str, limit: int = 5) -> List[Dict]:
        """根据用户输入表头推荐映射候选"""
        sql = """
            SELECT * FROM export_dictionary
            WHERE user_input_header ILIKE %s
            ORDER BY usage_count DESC, confidence DESC
            LIMIT %s
        """
        with self.get_cursor() as cur:
            cur.execute(sql, (f"%{user_input_header}%", limit))
            return [dict(r) for r in cur.fetchall()]

    # ================================================================
    # influencer_notes CRUD
    # ================================================================

    def insert_note(self, data: Dict[str, Any]) -> str:
        """插入笔记记录"""
        sql = """
            INSERT INTO influencer_notes
                (note_id, influencer_id, note_type, is_ad, impressions,
                 reads, likes, comments, collections, shares,
                 video_completion_rate, cover_image_url, published_at)
            VALUES
                (%(note_id)s, %(influencer_id)s, %(note_type)s, %(is_ad)s,
                 %(impressions)s, %(reads)s, %(likes)s, %(comments)s,
                 %(collections)s, %(shares)s, %(video_completion_rate)s,
                 %(cover_image_url)s, %(published_at)s)
            ON CONFLICT (note_id) DO UPDATE SET
                impressions = EXCLUDED.impressions,
                reads = EXCLUDED.reads,
                likes = EXCLUDED.likes,
                comments = EXCLUDED.comments,
                collections = EXCLUDED.collections,
                shares = EXCLUDED.shares
            RETURNING note_id
        """
        with self.get_cursor() as cur:
            cur.execute(sql, data)
            return cur.fetchone()["note_id"]

    def get_notes_by_influencer(self, influencer_id: int) -> List[Dict]:
        """获取达人的全部笔记"""
        sql = """
            SELECT * FROM influencer_notes
            WHERE influencer_id = %s
            ORDER BY published_at DESC
        """
        with self.get_cursor() as cur:
            cur.execute(sql, (influencer_id,))
            return [dict(r) for r in cur.fetchall()]

    # ================================================================
    # fulfillment_records CRUD
    # ================================================================

    def create_fulfillment(self, data: Dict[str, Any]) -> int:
        """创建履约记录"""
        sql = """
            INSERT INTO fulfillment_records
                (campaign_id, action_type, influencer_ids, payload_snapshot, operator_id)
            VALUES
                (%(campaign_id)s, %(action_type)s, %(influencer_ids)s::jsonb,
                 %(payload_snapshot)s::jsonb, %(operator_id)s)
            RETURNING record_id
        """
        data = dict(data)
        if isinstance(data.get("influencer_ids"), list):
            data["influencer_ids"] = json.dumps(data["influencer_ids"])
        if isinstance(data.get("payload_snapshot"), dict):
            data["payload_snapshot"] = json.dumps(data["payload_snapshot"], ensure_ascii=False)

        with self.get_cursor() as cur:
            cur.execute(sql, data)
            return cur.fetchone()["record_id"]

    def get_fulfillment_timeline(self, campaign_id: int) -> List[Dict]:
        """获取任务的履约时间轴"""
        sql = """
            SELECT * FROM fulfillment_records
            WHERE campaign_id = %s
            ORDER BY created_at ASC
        """
        with self.get_cursor() as cur:
            cur.execute(sql, (campaign_id,))
            return [dict(r) for r in cur.fetchall()]

    def get_influencer_history(self, influencer_id: int) -> List[Dict]:
        """获取达人的全部履约历史（跨任务）"""
        sql = """
            SELECT
                ch.campaign_id,
                ch.brand_name,
                ch.spu_name,
                ch.operator_role,
                fr.action_type,
                fr.created_at
            FROM fulfillment_records fr
            JOIN campaign_history ch ON fr.campaign_id = ch.campaign_id
            WHERE fr.influencer_ids @> %s::jsonb
            ORDER BY fr.created_at DESC
        """
        with self.get_cursor() as cur:
            cur.execute(sql, (json.dumps([influencer_id]),))
            return [dict(r) for r in cur.fetchall()]


# 全局单例
db = Database()
