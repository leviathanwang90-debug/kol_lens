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
    collection_name: str = "influencer_multimodal_vectors"

    # 向量维度定义
    face_dim: int = 512       # InsightFace 人脸向量
    scene_dim: int = 768      # CLIP 场景向量
    style_dim: int = 768      # 时序融合风格向量


# 全局单例
pg_config = PostgresConfig()
redis_config = RedisConfig()
milvus_config = MilvusConfig()
