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
                 intent_snapshot, status)
            VALUES
                (%(brand_name)s, %(spu_name)s, %(operator_id)s,
                 %(operator_role)s, %(intent_snapshot)s::jsonb, 'active')
            RETURNING campaign_id
        """
        data = dict(data)
        if isinstance(data.get("intent_snapshot"), (dict, list)):
            data["intent_snapshot"] = json.dumps(data["intent_snapshot"], ensure_ascii=False)

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
                campaign_id,
            ))

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

    def get_campaign_by_id(self, campaign_id: int) -> Optional[Dict]:
        """按 campaign_id 获取单个任务"""
        sql = """
            SELECT * FROM campaign_history
            WHERE campaign_id = %s
            LIMIT 1
        """
        with self.get_cursor() as cur:
            cur.execute(sql, (campaign_id,))
            row = cur.fetchone()
            return dict(row) if row else None

    def get_campaigns_by_operator(
        self,
        operator_id: int,
        brand_name: Optional[str] = None,
        spu_name: Optional[str] = None,
    ) -> List[Dict]:
        """查询某个操作人的历史任务，可按品牌/SPU 进一步过滤。"""
        sql = """
            SELECT * FROM campaign_history
            WHERE operator_id = %s
        """
        params: List[Any] = [operator_id]
        if brand_name:
            sql += " AND brand_name = %s"
            params.append(brand_name)
        if spu_name:
            sql += " AND spu_name = %s"
            params.append(spu_name)
        sql += " ORDER BY created_at DESC"

        with self.get_cursor() as cur:
            cur.execute(sql, tuple(params))
            return [dict(r) for r in cur.fetchall()]

    def get_campaigns_by_role(
        self,
        operator_role: int,
        brand_name: Optional[str] = None,
        spu_name: Optional[str] = None,
    ) -> List[Dict]:
        """查询某个角色的历史任务，可按品牌/SPU 进一步过滤。"""
        sql = """
            SELECT * FROM campaign_history
            WHERE operator_role = %s
        """
        params: List[Any] = [operator_role]
        if brand_name:
            sql += " AND brand_name = %s"
            params.append(brand_name)
        if spu_name:
            sql += " AND spu_name = %s"
            params.append(spu_name)
        sql += " ORDER BY created_at DESC"

        with self.get_cursor() as cur:
            cur.execute(sql, tuple(params))
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

    def get_fulfillment_record(self, record_id: int) -> Optional[Dict]:
        """按 record_id 获取单条履约记录详情"""
        sql = """
            SELECT * FROM fulfillment_records
            WHERE record_id = %s
            LIMIT 1
        """
        with self.get_cursor() as cur:
            cur.execute(sql, (record_id,))
            row = cur.fetchone()
            return dict(row) if row else None

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
