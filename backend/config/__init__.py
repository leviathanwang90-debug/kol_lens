"""
Σ.Match 基建层配置模块
从环境变量或 .env 文件加载配置，提供全局统一的连接参数。
"""

import os
from dataclasses import dataclass, field


@dataclass(frozen=True)
class PostgresConfig:
    """PostgreSQL 连接配置"""
    host: str = field(default_factory=lambda: os.getenv("POSTGRES_HOST", "localhost"))
    port: int = field(default_factory=lambda: int(os.getenv("POSTGRES_PORT", "5432")))
    database: str = field(default_factory=lambda: os.getenv("POSTGRES_DB", "sigma_match"))
    user: str = field(default_factory=lambda: os.getenv("POSTGRES_USER", "sigma"))
    password: str = field(default_factory=lambda: os.getenv("POSTGRES_PASSWORD", "sigma_secret_2026"))

    @property
    def dsn(self) -> str:
        return f"postgresql://{self.user}:{self.password}@{self.host}:{self.port}/{self.database}"

    @property
    def async_dsn(self) -> str:
        return f"postgresql+asyncpg://{self.user}:{self.password}@{self.host}:{self.port}/{self.database}"


@dataclass(frozen=True)
class RedisConfig:
    """Redis 连接配置"""
    host: str = field(default_factory=lambda: os.getenv("REDIS_HOST", "localhost"))
    port: int = field(default_factory=lambda: int(os.getenv("REDIS_PORT", "6379")))
    password: str = field(default_factory=lambda: os.getenv("REDIS_PASSWORD", "sigma_redis_2026"))

    @property
    def url(self) -> str:
        return f"redis://:{self.password}@{self.host}:{self.port}/0"

    def broker_url(self, db: int = 0) -> str:
        return f"redis://:{self.password}@{self.host}:{self.port}/{db}"


@dataclass(frozen=True)
class MilvusConfig:
    """Milvus 连接配置"""
    host: str = field(default_factory=lambda: os.getenv("MILVUS_HOST", "localhost"))
    port: int = field(default_factory=lambda: int(os.getenv("MILVUS_PORT", "19530")))
    collection_name: str = field(default_factory=lambda: os.getenv("QDRANT_COLLECTION", "influencer_vectors"))

    # 统一 embedding 维度（qwen3-vl embedding）
    embedding_dim: int = field(default_factory=lambda: int(os.getenv("EMBEDDING_DIM", "1024")))

    # 兼容旧多向量调用方（统一映射到 embedding_dim）
    face_dim: int = field(default_factory=lambda: int(os.getenv("EMBEDDING_DIM", "1024")))
    scene_dim: int = field(default_factory=lambda: int(os.getenv("EMBEDDING_DIM", "1024")))
    style_dim: int = field(default_factory=lambda: int(os.getenv("EMBEDDING_DIM", "1024")))


# 全局单例
pg_config = PostgresConfig()
redis_config = RedisConfig()
milvus_config = MilvusConfig()
