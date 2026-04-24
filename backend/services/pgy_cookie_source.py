from __future__ import annotations

import json
import os
import random
from pathlib import Path
from typing import List, Sequence

BASE_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = BASE_DIR / "data"
DEFAULT_TOKEN_FILE = DATA_DIR / "token.txt"

for _path in (DATA_DIR,):
    _path.mkdir(parents=True, exist_ok=True)


def _normalize_cookie_entry(value: str) -> str:
    normalized = str(value or "").strip()
    if not normalized:
        return ""
    if normalized.startswith("{"):
        try:
            data = json.loads(normalized)
            if isinstance(data, dict):
                return "; ".join(f"{key}={item}" for key, item in data.items() if item is not None)
        except Exception:
            return normalized
    return normalized


def _extend_cookie_pool_from_text(pool: List[str], text: str) -> None:
    for line in str(text or "").splitlines():
        cookie = _normalize_cookie_entry(line)
        if cookie and cookie not in pool:
            pool.append(cookie)


def _resolve_cookie_file_path() -> Path:
    explicit_path = os.getenv("PGY_COOKIE_FILE", "").strip()
    if explicit_path:
        candidate = Path(explicit_path)
        if not candidate.is_absolute():
            candidate = BASE_DIR / candidate
        return candidate
    return DEFAULT_TOKEN_FILE


def _download_cookie_file_from_oss(target_path: Path) -> bool:
    access_key_id = os.getenv("PGY_OSS_ACCESS_KEY_ID", "").strip()
    access_key_secret = os.getenv("PGY_OSS_ACCESS_KEY_SECRET", "").strip()
    if not access_key_id or not access_key_secret:
        return False
    try:
        import oss2
    except Exception:
        return False

    endpoint = os.getenv("PGY_OSS_ENDPOINT", "https://oss-cn-beijing.aliyuncs.com").strip() or "https://oss-cn-beijing.aliyuncs.com"
    bucket_name = os.getenv("PGY_OSS_BUCKET", "redmagic").strip() or "redmagic"
    object_key = os.getenv("PGY_OSS_OBJECT_KEY", "KOL/token.txt").strip() or "KOL/token.txt"
    target_path.parent.mkdir(parents=True, exist_ok=True)

    auth = oss2.Auth(access_key_id, access_key_secret)
    bucket = oss2.Bucket(auth, endpoint, bucket_name)
    bucket.get_object_to_file(object_key, str(target_path))
    return target_path.exists()


def load_pgy_cookie_pool() -> List[str]:
    pool: List[str] = []
    direct_keys: Sequence[str] = (
        "PGY_COOKIE",
        "PGY_COOKIE_HEADER",
    )
    for key in direct_keys:
        cookie = _normalize_cookie_entry(os.getenv(key, ""))
        if cookie and cookie not in pool:
            pool.append(cookie)

    multiline = os.getenv("PGY_COOKIE_HEADERS", "").strip()
    if multiline:
        _extend_cookie_pool_from_text(pool, multiline)

    token_path = _resolve_cookie_file_path()
    if not token_path.exists():
        try:
            _download_cookie_file_from_oss(token_path)
        except Exception:
            pass
    if token_path.exists():
        _extend_cookie_pool_from_text(pool, token_path.read_text(encoding="utf-8"))

    return pool


def pick_pgy_cookie_header() -> str:
    cookies = load_pgy_cookie_pool()
    if not cookies:
        return ""
    return random.choice(cookies)


def has_pgy_cookie_source() -> bool:
    if load_pgy_cookie_pool():
        return True
    access_key_id = os.getenv("PGY_OSS_ACCESS_KEY_ID", "").strip()
    access_key_secret = os.getenv("PGY_OSS_ACCESS_KEY_SECRET", "").strip()
    return bool(access_key_id and access_key_secret)
