"""
Σ.Match Redis 三层缓存封装
Sprint 1 · Task 1.3.1 ~ 1.3.3

三层缓存架构:
  Layer 1 — TaskCache:       异步任务状态管理 (pending/running/done/failed)
  Layer 2 — InfluencerCache: 达人数据缓存 (Cache-Aside 模式)
  Layer 3 — SearchCache:     检索结果缓存 (查询条件哈希)

键命名规范:
  task:{task_id}:status          → 任务状态 (String, TTL=1h)
  task:{task_id}:result          → 任务结果 (String/JSON, TTL=1h)
  task:{task_id}:logs            → 降级日志 (List, TTL=1h)
  influencer:{id}:basic          → 达人基础信息 (String/JSON, TTL=30min)
  influencer:{id}:notes          → 达人笔记列表 (String/JSON, TTL=15min)
  search:{hash}:result           → 检索结果缓存 (String/JSON, TTL=10min)
  ws:{session_id}:channel        → WebSocket 会话通道 (String, 连接期间)
"""

import hashlib
import importlib.machinery
import importlib.util
import json
import logging
import sys
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from config import redis_config


def _load_redis_client_module():
    """显式加载第三方 redis 客户端，避免与当前本地包同名冲突。"""
    project_root = Path(__file__).resolve().parents[1]
    search_paths = [
        path for path in sys.path
        if Path(path or ".").resolve() != project_root
    ]
    spec = importlib.machinery.PathFinder.find_spec("redis", search_paths)
    if spec is None or spec.loader is None:
        raise ImportError("未找到第三方 redis 客户端依赖。")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


redis_client = _load_redis_client_module()

logger = logging.getLogger(__name__)


# ============================================================
# TTL 常量 (秒)
# ============================================================
TTL_TASK = 3600          # 1 小时
TTL_INFLUENCER = 1800    # 30 分钟
TTL_NOTES = 900          # 15 分钟
TTL_SEARCH = 600         # 10 分钟
TTL_WS = 86400           # 24 小时 (WebSocket 会话)


class RedisManager:
    """Redis 连接管理器"""

    def __init__(self):
        self._client: Optional[redis_client.Redis] = None

    def connect(self) -> None:
        """建立 Redis 连接"""
        if self._client is not None:
            return

        self._client = redis_client.Redis(
            host=redis_config.host,
            port=redis_config.port,
            password=redis_config.password,
            db=0,
            decode_responses=True,
            socket_connect_timeout=5,
            socket_timeout=5,
            retry_on_timeout=True,
        )
        # 测试连接
        self._client.ping()
        logger.info("Redis 连接成功: %s:%d", redis_config.host, redis_config.port)

    def close(self) -> None:
        """关闭 Redis 连接"""
        if self._client:
            self._client.close()
            self._client = None
            logger.info("Redis 连接已关闭")

    @property
    def client(self) -> redis_client.Redis:
        """获取 Redis 客户端实例"""
        if self._client is None:
            self.connect()
        return self._client

    def health_check(self) -> Dict[str, Any]:
        """健康检查"""
        try:
            start = time.time()
            self.client.ping()
            latency = (time.time() - start) * 1000
            info = self.client.info("server")
            return {
                "status": "healthy",
                "latency_ms": round(latency, 2),
                "version": info.get("redis_version", "unknown"),
                "used_memory": info.get("used_memory_human", "unknown"),
            }
        except Exception as e:
            return {"status": "unhealthy", "error": str(e)}


# ============================================================
# Layer 1: TaskCache — 异步任务状态管理
# ============================================================

class TaskCache:
    """异步任务全生命周期状态管理

    状态流转: pending → running → done / failed
    用于 Celery Worker 与前端轮询之间的桥梁。
    """

    def __init__(self, redis_mgr: RedisManager):
        self._r = redis_mgr

    def _key(self, task_id: str, suffix: str) -> str:
        return f"task:{task_id}:{suffix}"

    def create_task(self, task_id: str, meta: Optional[Dict] = None) -> None:
        """创建任务，状态设为 pending

        Args:
            task_id: 任务唯一标识
            meta: 可选的任务元信息 (如查询条件快照)
        """
        pipe = self._r.client.pipeline()
        pipe.set(
            self._key(task_id, "status"),
            json.dumps({
                "status": "pending",
                "progress": 0.0,
                "created_at": time.time(),
                "meta": meta or {},
            }),
            ex=TTL_TASK,
        )
        # 初始化空日志列表
        pipe.delete(self._key(task_id, "logs"))
        pipe.rpush(self._key(task_id, "logs"), json.dumps({
            "time": time.time(),
            "level": "info",
            "message": "任务已创建，等待调度...",
        }))
        pipe.expire(self._key(task_id, "logs"), TTL_TASK)
        pipe.execute()

        logger.info("任务创建: %s", task_id)

    def update_status(
        self, task_id: str, status: str, progress: float = 0.0,
        message: Optional[str] = None
    ) -> None:
        """更新任务状态和进度

        Args:
            task_id: 任务标识
            status: 状态 (pending/running/done/failed)
            progress: 进度百分比 (0.0 ~ 1.0)
            message: 可选的状态描述
        """
        key = self._key(task_id, "status")
        existing = self._r.client.get(key)
        data = json.loads(existing) if existing else {}

        data.update({
            "status": status,
            "progress": min(max(progress, 0.0), 1.0),
            "updated_at": time.time(),
        })
        if message:
            data["message"] = message

        self._r.client.set(key, json.dumps(data), ex=TTL_TASK)

        # 自动追加日志
        if message:
            self.append_log(task_id, message, level="info")

        logger.debug("任务状态更新: %s → %s (%.0f%%)", task_id, status, progress * 100)

    def append_log(
        self, task_id: str, log_line: str, level: str = "info"
    ) -> None:
        """追加一条降级日志

        Args:
            task_id: 任务标识
            log_line: 日志内容
            level: 日志级别 (info/warn/error)
        """
        key = self._key(task_id, "logs")
        entry = json.dumps({
            "time": time.time(),
            "level": level,
            "message": log_line,
        })
        self._r.client.rpush(key, entry)
        self._r.client.expire(key, TTL_TASK)

    def set_result(self, task_id: str, result: Dict[str, Any]) -> None:
        """设置任务最终结果

        Args:
            task_id: 任务标识
            result: 结果数据 (JSON 可序列化)
        """
        self._r.client.set(
            self._key(task_id, "result"),
            json.dumps(result, ensure_ascii=False),
            ex=TTL_TASK,
        )
        # 同时更新状态为 done
        self.update_status(task_id, "done", progress=1.0, message="任务完成")
        logger.info("任务结果已设置: %s", task_id)

    def set_error(self, task_id: str, error_msg: str) -> None:
        """设置任务失败状态"""
        self.update_status(task_id, "failed", message=f"任务失败: {error_msg}")
        self.append_log(task_id, error_msg, level="error")

    def get_task_info(self, task_id: str) -> Optional[Dict[str, Any]]:
        """获取任务完整信息 (状态 + 进度 + 日志 + 结果)"""
        pipe = self._r.client.pipeline()
        pipe.get(self._key(task_id, "status"))
        pipe.lrange(self._key(task_id, "logs"), 0, -1)
        pipe.get(self._key(task_id, "result"))
        status_raw, logs_raw, result_raw = pipe.execute()

        if not status_raw:
            return None

        info = json.loads(status_raw)
        info["logs"] = [json.loads(l) for l in logs_raw] if logs_raw else []
        info["result"] = json.loads(result_raw) if result_raw else None

        return info

    def get_logs_since(self, task_id: str, start_index: int = 0) -> List[Dict]:
        """获取指定索引之后的增量日志 (前端轮询用)

        Args:
            task_id: 任务标识
            start_index: 起始索引 (0-based)

        Returns:
            增量日志列表
        """
        key = self._key(task_id, "logs")
        raw_logs = self._r.client.lrange(key, start_index, -1)
        return [json.loads(l) for l in raw_logs] if raw_logs else []

    def delete_task(self, task_id: str) -> None:
        """删除任务的全部缓存数据"""
        keys = [
            self._key(task_id, "status"),
            self._key(task_id, "logs"),
            self._key(task_id, "result"),
        ]
        self._r.client.delete(*keys)


# ============================================================
# Layer 2: InfluencerCache — 达人数据缓存
# ============================================================

class InfluencerCache:
    """达人数据缓存 (Cache-Aside 模式)

    先查 Redis，命中则直接返回；
    未命中则调用 fallback 函数查 PostgreSQL，写入 Redis 后返回。
    """

    def __init__(self, redis_mgr: RedisManager):
        self._r = redis_mgr

    def get_basic(
        self,
        influencer_id: int,
        fallback: Optional[Callable[[int], Optional[Dict]]] = None,
    ) -> Optional[Dict]:
        """获取达人基础信息 (Cache-Aside)

        Args:
            influencer_id: 达人 internal_id
            fallback: 缓存未命中时的回调函数 (查 PostgreSQL)

        Returns:
            达人基础信息字典，或 None
        """
        key = f"influencer:{influencer_id}:basic"

        # 尝试从缓存读取
        cached = self._r.client.get(key)
        if cached:
            logger.debug("缓存命中: %s", key)
            return json.loads(cached)

        # 缓存未命中，调用 fallback
        if fallback is None:
            return None

        data = fallback(influencer_id)
        if data:
            self._set_basic(influencer_id, data)
        return data

    def _set_basic(self, influencer_id: int, data: Dict) -> None:
        """写入达人基础信息缓存"""
        key = f"influencer:{influencer_id}:basic"
        self._r.client.set(
            key,
            json.dumps(data, ensure_ascii=False, default=str),
            ex=TTL_INFLUENCER,
        )

    def get_notes(
        self,
        influencer_id: int,
        fallback: Optional[Callable[[int], List[Dict]]] = None,
    ) -> List[Dict]:
        """获取达人笔记列表 (Cache-Aside)"""
        key = f"influencer:{influencer_id}:notes"

        cached = self._r.client.get(key)
        if cached:
            logger.debug("缓存命中: %s", key)
            return json.loads(cached)

        if fallback is None:
            return []

        data = fallback(influencer_id)
        if data:
            self._r.client.set(
                key,
                json.dumps(data, ensure_ascii=False, default=str),
                ex=TTL_NOTES,
            )
        return data

    def invalidate(self, influencer_id: int) -> None:
        """清除指定达人的全部缓存"""
        keys = [
            f"influencer:{influencer_id}:basic",
            f"influencer:{influencer_id}:notes",
        ]
        self._r.client.delete(*keys)
        logger.info("达人缓存已清除: %d", influencer_id)

    def batch_invalidate(self, influencer_ids: List[int]) -> None:
        """批量清除达人缓存"""
        keys = []
        for iid in influencer_ids:
            keys.append(f"influencer:{iid}:basic")
            keys.append(f"influencer:{iid}:notes")
        if keys:
            self._r.client.delete(*keys)
            logger.info("批量清除 %d 位达人的缓存", len(influencer_ids))

    def warm_up(
        self,
        influencer_ids: List[int],
        basic_loader: Callable[[int], Optional[Dict]],
        notes_loader: Callable[[int], List[Dict]],
    ) -> int:
        """预热缓存: 批量加载达人数据到 Redis

        Args:
            influencer_ids: 需要预热的达人 ID 列表
            basic_loader: 基础信息加载函数
            notes_loader: 笔记列表加载函数

        Returns:
            成功预热的达人数量
        """
        count = 0
        pipe = self._r.client.pipeline()

        for iid in influencer_ids:
            basic = basic_loader(iid)
            if basic:
                pipe.set(
                    f"influencer:{iid}:basic",
                    json.dumps(basic, ensure_ascii=False, default=str),
                    ex=TTL_INFLUENCER,
                )
                notes = notes_loader(iid)
                if notes:
                    pipe.set(
                        f"influencer:{iid}:notes",
                        json.dumps(notes, ensure_ascii=False, default=str),
                        ex=TTL_NOTES,
                    )
                count += 1

        pipe.execute()
        logger.info("缓存预热完成: %d/%d 位达人", count, len(influencer_ids))
        return count


# ============================================================
# Layer 3: SearchCache — 检索结果缓存
# ============================================================

class SearchCache:
    """检索结果缓存

    对相同查询条件的检索结果进行缓存，避免重复计算。
    缓存键通过对查询参数进行 MD5 哈希生成。
    """

    def __init__(self, redis_mgr: RedisManager):
        self._r = redis_mgr

    @staticmethod
    def _hash_query(params: Dict[str, Any]) -> str:
        """对查询参数生成 MD5 哈希"""
        # 排序键以确保相同参数生成相同哈希
        canonical = json.dumps(params, sort_keys=True, ensure_ascii=False)
        return hashlib.md5(canonical.encode()).hexdigest()

    def get(self, query_params: Dict[str, Any]) -> Optional[List[Dict]]:
        """查询缓存

        Args:
            query_params: 查询参数字典

        Returns:
            缓存的检索结果，或 None (未命中)
        """
        query_hash = self._hash_query(query_params)
        key = f"search:{query_hash}:result"

        cached = self._r.client.get(key)
        if cached:
            logger.debug("检索缓存命中: %s", query_hash[:8])
            return json.loads(cached)

        return None

    def set(
        self,
        query_params: Dict[str, Any],
        results: List[Dict],
        ttl: int = TTL_SEARCH,
    ) -> str:
        """写入检索结果缓存

        Args:
            query_params: 查询参数字典
            results: 检索结果列表
            ttl: 缓存过期时间 (秒)

        Returns:
            缓存键的哈希值
        """
        query_hash = self._hash_query(query_params)
        key = f"search:{query_hash}:result"

        self._r.client.set(
            key,
            json.dumps(results, ensure_ascii=False, default=str),
            ex=ttl,
        )
        logger.debug("检索结果已缓存: %s (TTL=%ds, 结果数=%d)",
                      query_hash[:8], ttl, len(results))
        return query_hash

    def invalidate_all(self) -> int:
        """清除全部检索缓存

        Returns:
            清除的键数量
        """
        pattern = "search:*:result"
        keys = list(self._r.client.scan_iter(match=pattern, count=100))
        if keys:
            self._r.client.delete(*keys)
        logger.info("清除 %d 条检索缓存", len(keys))
        return len(keys)


# ============================================================
# WebSocket 会话管理
# ============================================================

class WSSessionStore:
    """WebSocket 会话通道管理"""

    def __init__(self, redis_mgr: RedisManager):
        self._r = redis_mgr

    def register(self, session_id: str, meta: Optional[Dict] = None) -> None:
        """注册 WebSocket 会话"""
        key = f"ws:{session_id}:channel"
        self._r.client.set(
            key,
            json.dumps({
                "connected_at": time.time(),
                "meta": meta or {},
            }),
            ex=TTL_WS,
        )

    def heartbeat(self, session_id: str) -> None:
        """刷新会话 TTL"""
        key = f"ws:{session_id}:channel"
        self._r.client.expire(key, TTL_WS)

    def unregister(self, session_id: str) -> None:
        """注销 WebSocket 会话"""
        self._r.client.delete(f"ws:{session_id}:channel")

    def is_active(self, session_id: str) -> bool:
        """检查会话是否活跃"""
        return self._r.client.exists(f"ws:{session_id}:channel") > 0

    def active_count(self) -> int:
        """获取活跃会话数"""
        keys = list(self._r.client.scan_iter(match="ws:*:channel", count=100))
        return len(keys)


# ============================================================
# 全局单例
# ============================================================

redis_mgr = RedisManager()
task_cache = TaskCache(redis_mgr)
influencer_cache = InfluencerCache(redis_mgr)
search_cache = SearchCache(redis_mgr)
ws_store = WSSessionStore(redis_mgr)
