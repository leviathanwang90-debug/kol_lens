"""
Σ.Match 基建层配置模块
从环境变量或 .env 文件加载配置，提供全局统一的连接参数。
"""

import os
from dataclasses import dataclass, field
from urllib.parse import quote


@dataclass(frozen=True)
class PostgresConfig:
    """PostgreSQL 连接配置"""
    host: str = field(default_factory=lambda: os.getenv("POSTGRES_HOST", "localhost"))
    port: int = field(default_factory=lambda: int(os.getenv("POSTGRES_PORT", "5432")))
    database: str = field(default_factory=lambda: os.getenv("POSTGRES_DB", "sigma_match"))
    user: str = field(default_factory=lambda: os.getenv("POSTGRES_USER", "sigma"))
    password: str = field(default_factory=lambda: os.getenv("POSTGRES_PASSWORD", "sigma_secret_2026"))
    sslmode: str = field(default_factory=lambda: os.getenv("POSTGRES_SSLMODE", "prefer"))
    connect_timeout: int = field(default_factory=lambda: int(os.getenv("POSTGRES_CONNECT_TIMEOUT", "5")))
    application_name: str = field(default_factory=lambda: os.getenv("POSTGRES_APPLICATION_NAME", "kol_lens"))

    @property
    def dsn(self) -> str:
        user = quote(self.user, safe="")
        password = quote(self.password, safe="")
        return (
            f"postgresql://{user}:{password}@{self.host}:{self.port}/{self.database}"
            f"?sslmode={self.sslmode}&application_name={quote(self.application_name, safe='')}"
        )

    @property
    def async_dsn(self) -> str:
        user = quote(self.user, safe="")
        password = quote(self.password, safe="")
        return (
            f"postgresql+asyncpg://{user}:{password}@{self.host}:{self.port}/{self.database}"
            f"?ssl={self.sslmode != 'disable'}"
        )


@dataclass(frozen=True)
class RedisConfig:
    """Redis 连接配置"""
    host: str = field(default_factory=lambda: os.getenv("REDIS_HOST", "localhost"))
    port: int = field(default_factory=lambda: int(os.getenv("REDIS_PORT", "6379")))
    password: str = field(default_factory=lambda: os.getenv("REDIS_PASSWORD", "sigma_redis_2026"))
    username: str = field(default_factory=lambda: os.getenv("REDIS_USERNAME", ""))
    db: int = field(default_factory=lambda: int(os.getenv("REDIS_DB", "0")))
    ssl: bool = field(default_factory=lambda: os.getenv("REDIS_SSL", "0").lower() in {"1", "true", "yes", "on"})
    ssl_cert_reqs: str = field(default_factory=lambda: os.getenv("REDIS_SSL_CERT_REQS", "required"))
    socket_timeout: int = field(default_factory=lambda: int(os.getenv("REDIS_SOCKET_TIMEOUT", "5")))

    @property
    def url(self) -> str:
        scheme = "rediss" if self.ssl else "redis"
        password = quote(self.password, safe="")
        if self.username:
            auth = f"{quote(self.username, safe='')}:{password}"
        else:
            auth = f":{password}"
        return f"{scheme}://{auth}@{self.host}:{self.port}/{self.db}"

    def broker_url(self, db: int = 0) -> str:
        scheme = "rediss" if self.ssl else "redis"
        password = quote(self.password, safe="")
        if self.username:
            auth = f"{quote(self.username, safe='')}:{password}"
        else:
            auth = f":{password}"
        return f"{scheme}://{auth}@{self.host}:{self.port}/{db}"


@dataclass(frozen=True)
class MilvusConfig:
    """DashVector 连接配置（兼容旧 MilvusConfig 命名）"""
    endpoint: str = field(default_factory=lambda: os.getenv("DASHVECTOR_ENDPOINT", ""))
    api_key: str = field(default_factory=lambda: os.getenv("DASHVECTOR_API_KEY", ""))
    collection_name: str = field(default_factory=lambda: os.getenv("DASHVECTOR_COLLECTION", "influencer_vectors"))
    embedding_dim: int = field(default_factory=lambda: int(os.getenv("EMBEDDING_DIM", "1024")))

    # 向量维度定义
    face_dim: int = field(default_factory=lambda: int(os.getenv("EMBEDDING_DIM", "1024")))
    scene_dim: int = field(default_factory=lambda: int(os.getenv("EMBEDDING_DIM", "1024")))
    style_dim: int = field(default_factory=lambda: int(os.getenv("EMBEDDING_DIM", "1024")))


# 全局单例
pg_config = PostgresConfig()
redis_config = RedisConfig()
milvus_config = MilvusConfig()
