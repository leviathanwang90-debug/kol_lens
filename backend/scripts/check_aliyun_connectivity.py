"""阿里云三件套联通验收脚本：PostgreSQL + Redis + DashVector。"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, Optional

import psycopg2
import redis

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from config import pg_config, redis_config

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")


@dataclass
class CheckResult:
    name: str
    ok: bool
    latency_ms: float
    detail: str
    extra: Optional[Dict[str, Any]] = None


def _fmt_ms(start: float) -> float:
    return round((time.time() - start) * 1000, 2)


def check_postgres(timeout_sec: int) -> CheckResult:
    start = time.time()
    conn = None
    try:
        conn = psycopg2.connect(
            host=pg_config.host,
            port=pg_config.port,
            dbname=pg_config.database,
            user=pg_config.user,
            password=pg_config.password,
            connect_timeout=max(1, int(timeout_sec)),
        )
        with conn.cursor() as cur:
            cur.execute("SELECT version(), current_database(), current_user")
            version, dbname, dbuser = cur.fetchone()
        return CheckResult(
            name="postgres",
            ok=True,
            latency_ms=_fmt_ms(start),
            detail="connected",
            extra={"database": dbname, "user": dbuser, "version": str(version)},
        )
    except Exception as exc:
        return CheckResult(name="postgres", ok=False, latency_ms=_fmt_ms(start), detail=str(exc))
    finally:
        if conn:
            conn.close()


def check_redis(timeout_sec: int) -> CheckResult:
    start = time.time()
    client = None
    try:
        client = redis.Redis(
            host=redis_config.host,
            port=redis_config.port,
            password=redis_config.password,
            db=0,
            decode_responses=True,
            socket_connect_timeout=max(1, int(timeout_sec)),
            socket_timeout=max(1, int(timeout_sec)),
        )
        client.ping()
        info = client.info("server")
        return CheckResult(
            name="redis",
            ok=True,
            latency_ms=_fmt_ms(start),
            detail="connected",
            extra={"version": info.get("redis_version", "unknown")},
        )
    except Exception as exc:
        return CheckResult(name="redis", ok=False, latency_ms=_fmt_ms(start), detail=str(exc))
    finally:
        if client:
            client.close()


def check_dashvector() -> CheckResult:
    start = time.time()
    try:
        from config import milvus_config
        from milvus import milvus_mgr

        milvus_mgr.connect()
        milvus_mgr.create_collection(drop_if_exists=False)
        stats = milvus_mgr.collection_stats()
        return CheckResult(
            name="dashvector",
            ok=True,
            latency_ms=_fmt_ms(start),
            detail="connected",
            extra={
                "collection": milvus_config.collection_name,
                "stats": stats.get("stats", {}),
            },
        )
    except Exception as exc:
        return CheckResult(name="dashvector", ok=False, latency_ms=_fmt_ms(start), detail=str(exc))
    finally:
        try:
            from milvus import milvus_mgr

            milvus_mgr.disconnect()
        except Exception:
            pass


def required_env_snapshot() -> Dict[str, bool]:
    required = [
        "POSTGRES_HOST",
        "POSTGRES_PORT",
        "POSTGRES_DB",
        "POSTGRES_USER",
        "POSTGRES_PASSWORD",
        "REDIS_HOST",
        "REDIS_PORT",
        "REDIS_PASSWORD",
        "DASHVECTOR_ENDPOINT",
        "DASHVECTOR_API_KEY",
        "DASHVECTOR_COLLECTION",
    ]
    return {key: bool(os.getenv(key)) for key in required}


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate connectivity for Aliyun PG + Redis + DashVector")
    parser.add_argument("--timeout-sec", type=int, default=5)
    parser.add_argument("--json", action="store_true", help="输出 JSON 结果，便于 CI 解析")
    args = parser.parse_args()

    env_state = required_env_snapshot()
    results = [
        check_postgres(args.timeout_sec),
        check_redis(args.timeout_sec),
        check_dashvector(),
    ]
    all_ok = all(r.ok for r in results)

    payload = {
        "all_ok": all_ok,
        "env": env_state,
        "checks": [asdict(r) for r in results],
    }

    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print("=" * 72)
        print("Aliyun 三件套联通验收结果")
        print("=" * 72)
        print("ENV:")
        for k, v in env_state.items():
            print(f"  - {k}: {'SET' if v else 'MISSING'}")
        print("-" * 72)
        for r in results:
            status = "PASS" if r.ok else "FAIL"
            print(f"[{status}] {r.name:<10} {r.latency_ms:>8.2f}ms  {r.detail}")
            if r.extra:
                print(f"        extra={r.extra}")
        print("-" * 72)
        print(f"OVERALL: {'PASS' if all_ok else 'FAIL'}")

    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
