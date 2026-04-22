\# 完整迁移交接文档（含全部修改代码与参数）



> 可将本文件完整复制到新对话，要求 AI 按文档中的文件内容逐个覆盖。



\## 参数与环境变量



\- Qdrant: `QDRANT\_COLLECTION`, `EMBEDDING\_DIM`

\- PostgreSQL: `POSTGRES\_\*`

\- Redis: `REDIS\_\*`

\- 小红书 OAuth: `XHS\_APP\_ID`, `XHS\_APP\_SECRET`, `XHS\_AUTH\_CODE`, `XHS\_AUTH\_USER\_ID`, `XHS\_TOKEN\_URL`, `XHS\_REFRESH\_URL`, `XHS\_TOKEN\_FILE`, `XHS\_NOTE\_API\_URL`, `XHS\_TIMEOUT\_SECONDS`



\## 文件覆盖清单



\### `backend/config/\_\_init\_\_.py`



```python

"""

Σ.Match 基建层配置模块

从环境变量或 .env 文件加载配置，提供全局统一的连接参数。

"""



import os

from dataclasses import dataclass, field





@dataclass(frozen=True)

class PostgresConfig:

&#x20;   """PostgreSQL 连接配置"""

&#x20;   host: str = field(default\_factory=lambda: os.getenv("POSTGRES\_HOST", "localhost"))

&#x20;   port: int = field(default\_factory=lambda: int(os.getenv("POSTGRES\_PORT", "5432")))

&#x20;   database: str = field(default\_factory=lambda: os.getenv("POSTGRES\_DB", "sigma\_match"))

&#x20;   user: str = field(default\_factory=lambda: os.getenv("POSTGRES\_USER", "sigma"))

&#x20;   password: str = field(default\_factory=lambda: os.getenv("POSTGRES\_PASSWORD", "sigma\_secret\_2026"))



&#x20;   @property

&#x20;   def dsn(self) -> str:

&#x20;       return f"postgresql://{self.user}:{self.password}@{self.host}:{self.port}/{self.database}"



&#x20;   @property

&#x20;   def async\_dsn(self) -> str:

&#x20;       return f"postgresql+asyncpg://{self.user}:{self.password}@{self.host}:{self.port}/{self.database}"





@dataclass(frozen=True)

class RedisConfig:

&#x20;   """Redis 连接配置"""

&#x20;   host: str = field(default\_factory=lambda: os.getenv("REDIS\_HOST", "localhost"))

&#x20;   port: int = field(default\_factory=lambda: int(os.getenv("REDIS\_PORT", "6379")))

&#x20;   password: str = field(default\_factory=lambda: os.getenv("REDIS\_PASSWORD", "sigma\_redis\_2026"))



&#x20;   @property

&#x20;   def url(self) -> str:

&#x20;       return f"redis://:{self.password}@{self.host}:{self.port}/0"



&#x20;   def broker\_url(self, db: int = 0) -> str:

&#x20;       return f"redis://:{self.password}@{self.host}:{self.port}/{db}"





@dataclass(frozen=True)

class MilvusConfig:

&#x20;   """Milvus 连接配置"""

&#x20;   host: str = field(default\_factory=lambda: os.getenv("MILVUS\_HOST", "localhost"))

&#x20;   port: int = field(default\_factory=lambda: int(os.getenv("MILVUS\_PORT", "19530")))

&#x20;   collection\_name: str = field(default\_factory=lambda: os.getenv("QDRANT\_COLLECTION", "influencer\_vectors"))



&#x20;   # 统一 embedding 维度（qwen3-vl embedding）

&#x20;   embedding\_dim: int = field(default\_factory=lambda: int(os.getenv("EMBEDDING\_DIM", "1024")))



&#x20;   # 兼容旧多向量调用方（统一映射到 embedding\_dim）

&#x20;   face\_dim: int = field(default\_factory=lambda: int(os.getenv("EMBEDDING\_DIM", "1024")))

&#x20;   scene\_dim: int = field(default\_factory=lambda: int(os.getenv("EMBEDDING\_DIM", "1024")))

&#x20;   style\_dim: int = field(default\_factory=lambda: int(os.getenv("EMBEDDING\_DIM", "1024")))





\# 全局单例

pg\_config = PostgresConfig()

redis\_config = RedisConfig()

milvus\_config = MilvusConfig()



```



\### `backend/milvus/\_\_init\_\_.py`



```python

"""

Σ.Match 向量数据库管理模块 (Qdrant 单向量版)

对外保持 MilvusManager/milvus\_mgr 接口，底层为 Qdrant。

"""



import logging

from typing import Any, Dict, List, Optional



from qdrant\_client import QdrantClient, models



from config import milvus\_config



logger = logging.getLogger(\_\_name\_\_)



COLLECTION\_NAME = milvus\_config.collection\_name



\# 兼容旧接口暴露常量：统一向量检索后仅保留一个向量字段

DIM\_FACE = milvus\_config.embedding\_dim

DIM\_SCENE = milvus\_config.embedding\_dim

DIM\_STYLE = milvus\_config.embedding\_dim



FIELD\_FACE = "embedding"

FIELD\_SCENE = "embedding"

FIELD\_STYLE = "embedding"

DEFAULT\_TOP\_K = 100





class MilvusManager:

&#x20;   """兼容层：名称沿用 MilvusManager，实际驱动 Qdrant。"""



&#x20;   def \_\_init\_\_(self):

&#x20;       self.\_connected = False

&#x20;       self.client: Optional\[QdrantClient] = None



&#x20;   def connect(self, alias: str = "default") -> str:  # noqa: ARG002

&#x20;       if self.\_connected:

&#x20;           return "Qdrant Ready"



&#x20;       host = getattr(milvus\_config, "host", "localhost")

&#x20;       port = int(getattr(milvus\_config, "port", 6333))

&#x20;       self.client = QdrantClient(host=host, port=port)

&#x20;       self.\_connected = True

&#x20;       logger.info("Qdrant 连接成功: %s:%d", host, port)

&#x20;       return self.server\_version()



&#x20;   def disconnect(self, alias: str = "default") -> None:  # noqa: ARG002

&#x20;       self.client = None

&#x20;       self.\_connected = False



&#x20;   def server\_version(self) -> str:

&#x20;       if not self.\_connected:

&#x20;           self.connect()

&#x20;       assert self.client is not None

&#x20;       return str(self.client.info().version)



&#x20;   def create\_collection(self, drop\_if\_exists: bool = False) -> Any:

&#x20;       if not self.\_connected:

&#x20;           self.connect()

&#x20;       assert self.client is not None



&#x20;       if drop\_if\_exists and self.client.collection\_exists(COLLECTION\_NAME):

&#x20;           self.client.delete\_collection(COLLECTION\_NAME)



&#x20;       if not self.client.collection\_exists(COLLECTION\_NAME):

&#x20;           self.client.create\_collection(

&#x20;               collection\_name=COLLECTION\_NAME,

&#x20;               vectors\_config=models.VectorParams(

&#x20;                   size=milvus\_config.embedding\_dim,

&#x20;                   distance=models.Distance.COSINE,

&#x20;                   on\_disk=True,

&#x20;               ),

&#x20;               hnsw\_config=models.HnswConfigDiff(on\_disk=True),

&#x20;               on\_disk\_payload=True,

&#x20;           )



&#x20;           for field, schema\_type in \[

&#x20;               ("followers", models.PayloadSchemaType.INTEGER),

&#x20;               ("gender", models.PayloadSchemaType.KEYWORD),

&#x20;               ("region", models.PayloadSchemaType.KEYWORD),

&#x20;           ]:

&#x20;               self.client.create\_payload\_index(

&#x20;                   COLLECTION\_NAME,

&#x20;                   field,

&#x20;                   field\_schema=schema\_type,

&#x20;               )



&#x20;       return self.get\_collection()



&#x20;   def get\_collection(self) -> models.CollectionInfo:

&#x20;       if not self.\_connected:

&#x20;           self.connect()

&#x20;       assert self.client is not None

&#x20;       return self.client.get\_collection(COLLECTION\_NAME)



&#x20;   def collection\_stats(self) -> Dict\[str, Any]:

&#x20;       info = self.get\_collection()

&#x20;       return {

&#x20;           "name": COLLECTION\_NAME,

&#x20;           "num\_entities": info.points\_count or 0,

&#x20;           "status": str(info.status),

&#x20;       }



&#x20;   def insert(self, data: List\[Dict\[str, Any]]) -> int:

&#x20;       if not self.\_connected:

&#x20;           self.connect()

&#x20;       assert self.client is not None



&#x20;       points: List\[models.PointStruct] = \[]

&#x20;       for item in data:

&#x20;           vector = (

&#x20;               item.get("embedding")

&#x20;               or item.get(FIELD\_STYLE)

&#x20;               or item.get(FIELD\_FACE)

&#x20;               or item.get(FIELD\_SCENE)

&#x20;           )

&#x20;           if vector is None:

&#x20;               raise ValueError("insert 数据缺少 embedding 向量")



&#x20;           points.append(

&#x20;               models.PointStruct(

&#x20;                   id=int(item\["id"]),

&#x20;                   vector=vector,

&#x20;                   payload={

&#x20;                       "followers": item.get("followers", 0),

&#x20;                       "gender": item.get("gender", ""),

&#x20;                       "region": item.get("region", ""),

&#x20;                   },

&#x20;               )

&#x20;           )



&#x20;       self.client.upsert(collection\_name=COLLECTION\_NAME, points=points)

&#x20;       return len(points)



&#x20;   def upsert(self, data: List\[Dict\[str, Any]]) -> int:

&#x20;       return self.insert(data)



&#x20;   def delete\_by\_ids(self, ids: List\[int]) -> None:

&#x20;       if not self.\_connected:

&#x20;           self.connect()

&#x20;       assert self.client is not None



&#x20;       self.client.delete(

&#x20;           collection\_name=COLLECTION\_NAME,

&#x20;           points\_selector=models.PointIdsList(points=ids),

&#x20;       )



&#x20;   def retrieve\_by\_ids(self, ids: List\[int], with\_vectors: bool = True) -> List\[Any]:

&#x20;       if not self.\_connected:

&#x20;           self.connect()

&#x20;       assert self.client is not None

&#x20;       return self.client.retrieve(

&#x20;           collection\_name=COLLECTION\_NAME,

&#x20;           ids=ids,

&#x20;           with\_vectors=with\_vectors,

&#x20;           with\_payload=True,

&#x20;       )



&#x20;   def load\_collection(self) -> None:

&#x20;       return None



&#x20;   def release\_collection(self) -> None:

&#x20;       return None



&#x20;   def hybrid\_search(

&#x20;       self,

&#x20;       vector\_field: str = FIELD\_STYLE,  # noqa: ARG002

&#x20;       query\_vector: Optional\[List\[float]] = None,

&#x20;       scalar\_filters: Optional\[Dict\[str, Any]] = None,

&#x20;       top\_k: int = DEFAULT\_TOP\_K,

&#x20;       \*\*kwargs: Any,

&#x20;   ) -> List\[Dict\[str, Any]]:

&#x20;       if query\_vector is None:

&#x20;           raise ValueError("query\_vector 不能为空")

&#x20;       if not self.\_connected:

&#x20;           self.connect()

&#x20;       assert self.client is not None



&#x20;       q\_filter = self.\_build\_filter\_expr(scalar\_filters or {})

&#x20;       results = self.client.search(

&#x20;           collection\_name=COLLECTION\_NAME,

&#x20;           query\_vector=query\_vector,

&#x20;           query\_filter=q\_filter,

&#x20;           limit=top\_k,

&#x20;           with\_payload=True,

&#x20;       )



&#x20;       formatted = \[]

&#x20;       for hit in results:

&#x20;           payload = hit.payload or {}

&#x20;           formatted.append(

&#x20;               {

&#x20;                   "id": hit.id,

&#x20;                   "score": float(hit.score),

&#x20;                   "distance": 1.0 - float(hit.score),

&#x20;                   "followers": payload.get("followers"),

&#x20;                   "gender": payload.get("gender"),

&#x20;                   "region": payload.get("region"),

&#x20;               }

&#x20;           )

&#x20;       return formatted



&#x20;   def multi\_vector\_search(

&#x20;       self,

&#x20;       query\_vectors: Dict\[str, List\[float]],

&#x20;       weights: Optional\[Dict\[str, float]] = None,

&#x20;       scalar\_filters: Optional\[Dict\[str, Any]] = None,

&#x20;       top\_k: int = DEFAULT\_TOP\_K,

&#x20;   ) -> List\[Dict\[str, Any]]:

&#x20;       del weights  # 单向量模式下忽略多向量权重

&#x20;       vector = query\_vectors.get("embedding") or query\_vectors.get(FIELD\_STYLE)

&#x20;       if vector is None:

&#x20;           # 兼容历史调用：取第一条 query vector

&#x20;           vector = next(iter(query\_vectors.values()))

&#x20;       return self.hybrid\_search(

&#x20;           query\_vector=vector,

&#x20;           scalar\_filters=scalar\_filters,

&#x20;           top\_k=top\_k,

&#x20;       )



&#x20;   @staticmethod

&#x20;   def \_build\_filter\_expr(filters: Dict\[str, Any]) -> Optional\[models.Filter]:

&#x20;       if not filters:

&#x20;           return None



&#x20;       conditions = \[]

&#x20;       if "region" in filters and filters\["region"]:

&#x20;           regions = filters\["region"]

&#x20;           if isinstance(regions, str):

&#x20;               regions = \[regions]

&#x20;           conditions.append(

&#x20;               models.FieldCondition(

&#x20;                   key="region",

&#x20;                   match=models.MatchAny(any=regions),

&#x20;               )

&#x20;           )



&#x20;       if "gender" in filters and filters\["gender"]:

&#x20;           conditions.append(

&#x20;               models.FieldCondition(

&#x20;                   key="gender",

&#x20;                   match=models.MatchValue(value=filters\["gender"]),

&#x20;               )

&#x20;           )



&#x20;       if "followers\_min" in filters and filters\["followers\_min"] is not None:

&#x20;           conditions.append(

&#x20;               models.FieldCondition(

&#x20;                   key="followers",

&#x20;                   range=models.Range(gte=filters\["followers\_min"]),

&#x20;               )

&#x20;           )



&#x20;       if "followers\_max" in filters and filters\["followers\_max"] is not None:

&#x20;           conditions.append(

&#x20;               models.FieldCondition(

&#x20;                   key="followers",

&#x20;                   range=models.Range(lte=filters\["followers\_max"]),

&#x20;               )

&#x20;           )



&#x20;       return models.Filter(must=conditions) if conditions else None





milvus\_mgr = MilvusManager()



```



\### `backend/db/migrations/init.sql`



```sql

\-- ============================================================

\-- Σ.Match 基建层 — PostgreSQL Schema 初始化

\-- Sprint 1 · Task 1.1.1 \~ 1.1.4

\--

\-- 四张核心表:

\--   1. influencer\_basics    — 达人基础信息

\--   2. campaign\_history     — 寻星任务历史

\--   3. export\_dictionary    — 智能导出映射字典

\--   4. influencer\_notes     — 达人笔记明细

\--   5. fulfillment\_records  — 履约记录

\--

\-- 执行方式: Docker 容器启动时自动执行

\--           或手动: psql -U sigma -d sigma\_match -f init.sql

\-- ============================================================



\-- 启用扩展

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";



\-- ============================================================

\-- 1. influencer\_basics — 达人基础信息表

\-- ============================================================

CREATE TABLE IF NOT EXISTS influencer\_basics (

&#x20;   internal\_id     SERIAL          PRIMARY KEY,

&#x20;   red\_id          VARCHAR(64)     NOT NULL,

&#x20;   nickname        VARCHAR(128)    NOT NULL,

&#x20;   avatar\_url      TEXT,

&#x20;   gender          VARCHAR(8)      DEFAULT '未知',

&#x20;   region          VARCHAR(64),

&#x20;   followers       INTEGER         DEFAULT 0,

&#x20;   likes           INTEGER         DEFAULT 0,

&#x20;   collections     INTEGER         DEFAULT 0,

&#x20;   notes\_count     INTEGER         DEFAULT 0,

&#x20;   ad\_ratio\_30d    DECIMAL(5,4)    DEFAULT 0.0000,

&#x20;   latest\_note\_time TIMESTAMP,

&#x20;   tags            JSONB           DEFAULT '\[]'::jsonb,

&#x20;   pricing         JSONB           DEFAULT '{}'::jsonb,

&#x20;   created\_at      TIMESTAMP       DEFAULT NOW(),

&#x20;   updated\_at      TIMESTAMP       DEFAULT NOW()

);



\-- 索引

CREATE UNIQUE INDEX IF NOT EXISTS idx\_influencer\_red\_id

&#x20;   ON influencer\_basics (red\_id);



CREATE INDEX IF NOT EXISTS idx\_influencer\_region

&#x20;   ON influencer\_basics (region);



CREATE INDEX IF NOT EXISTS idx\_influencer\_followers

&#x20;   ON influencer\_basics (followers);



CREATE INDEX IF NOT EXISTS idx\_influencer\_created\_at

&#x20;   ON influencer\_basics (created\_at);



CREATE INDEX IF NOT EXISTS idx\_influencer\_tags

&#x20;   ON influencer\_basics USING GIN (tags);



CREATE INDEX IF NOT EXISTS idx\_influencer\_ad\_ratio

&#x20;   ON influencer\_basics (ad\_ratio\_30d);



\-- updated\_at 自动更新触发器

CREATE OR REPLACE FUNCTION update\_updated\_at\_column()

RETURNS TRIGGER AS $$

BEGIN

&#x20;   NEW.updated\_at = NOW();

&#x20;   RETURN NEW;

END;

$$ LANGUAGE plpgsql;



CREATE TRIGGER trg\_influencer\_updated\_at

&#x20;   BEFORE UPDATE ON influencer\_basics

&#x20;   FOR EACH ROW

&#x20;   EXECUTE FUNCTION update\_updated\_at\_column();



COMMENT ON TABLE influencer\_basics IS '达人基础信息表 — 存储每位达人的结构化数据，映射 Milvus 的 id 字段';

COMMENT ON COLUMN influencer\_basics.internal\_id IS '自增主键，与 Milvus Collection 的 id 字段一一映射';

COMMENT ON COLUMN influencer\_basics.red\_id IS '小红书号，全局唯一';

COMMENT ON COLUMN influencer\_basics.ad\_ratio\_30d IS '近 30 天商单比例，取值 0.0000 \~ 1.0000';

COMMENT ON COLUMN influencer\_basics.tags IS '达人标签数组，JSONB 格式，如 \["穿搭","高冷风"]';

COMMENT ON COLUMN influencer\_basics.pricing IS '报价信息，JSONB 格式，含图文CPM、视频CPM等';





\-- ============================================================

\-- 2. users / brand\_spus / collaborations

\-- ============================================================

CREATE TABLE IF NOT EXISTS users (

&#x20;   id          SERIAL          PRIMARY KEY,

&#x20;   username    VARCHAR(64)     UNIQUE NOT NULL,

&#x20;   role        VARCHAR(32)     DEFAULT 'operator',

&#x20;   created\_at  TIMESTAMP       DEFAULT NOW()

);



CREATE TABLE IF NOT EXISTS brand\_spus (

&#x20;   spu\_id       SERIAL          PRIMARY KEY,

&#x20;   brand\_name   VARCHAR(128)    NOT NULL,

&#x20;   spu\_name     VARCHAR(256)    NOT NULL,

&#x20;   base\_vector  JSONB,

&#x20;   kol\_count    INTEGER         DEFAULT 0,

&#x20;   created\_at   TIMESTAMP       DEFAULT NOW(),

&#x20;   updated\_at   TIMESTAMP       DEFAULT NOW()

);



CREATE UNIQUE INDEX IF NOT EXISTS idx\_brand\_spu\_name

&#x20;   ON brand\_spus (brand\_name, spu\_name);



ALTER TABLE brand\_spus

&#x20;   ADD COLUMN IF NOT EXISTS kol\_count INTEGER DEFAULT 0;



CREATE TRIGGER trg\_brand\_spus\_updated\_at

&#x20;   BEFORE UPDATE ON brand\_spus

&#x20;   FOR EACH ROW

&#x20;   EXECUTE FUNCTION update\_updated\_at\_column();



CREATE TABLE IF NOT EXISTS collaborations (

&#x20;   id                  SERIAL          PRIMARY KEY,

&#x20;   influencer\_id       INTEGER         REFERENCES influencer\_basics(internal\_id),

&#x20;   spu\_id              INTEGER         REFERENCES brand\_spus(spu\_id),

&#x20;   collaboration\_date  DATE,

&#x20;   performance\_score   DECIMAL(3,2)

);



CREATE INDEX IF NOT EXISTS idx\_collab\_spu\_id

&#x20;   ON collaborations (spu\_id);



CREATE INDEX IF NOT EXISTS idx\_collab\_influencer\_id

&#x20;   ON collaborations (influencer\_id);



CREATE UNIQUE INDEX IF NOT EXISTS idx\_collab\_spu\_influencer\_unique

&#x20;   ON collaborations (spu\_id, influencer\_id);





\-- ============================================================

\-- 3. campaign\_history — 寻星任务历史表

\-- ============================================================

CREATE TABLE IF NOT EXISTS campaign\_history (

&#x20;   campaign\_id             SERIAL          PRIMARY KEY,

&#x20;   brand\_name              VARCHAR(128)    NOT NULL,

&#x20;   spu\_name                VARCHAR(256)    NOT NULL,

&#x20;   operator\_id             INTEGER,

&#x20;   operator\_role           SMALLINT        NOT NULL DEFAULT 2,

&#x20;   selected\_influencer\_ids JSONB           DEFAULT '\[]'::jsonb,

&#x20;   pending\_influencer\_ids  JSONB           DEFAULT '\[]'::jsonb,

&#x20;   rejected\_influencer\_ids JSONB           DEFAULT '\[]'::jsonb,

&#x20;   intent\_snapshot         JSONB,

&#x20;   query\_vector\_snapshot   JSONB,

&#x20;   status                  VARCHAR(16)     DEFAULT 'active',

&#x20;   created\_at              TIMESTAMP       DEFAULT NOW(),

&#x20;   committed\_at            TIMESTAMP

);



\-- 索引

CREATE INDEX IF NOT EXISTS idx\_campaign\_brand\_spu

&#x20;   ON campaign\_history (brand\_name, spu\_name);



CREATE INDEX IF NOT EXISTS idx\_campaign\_operator\_role

&#x20;   ON campaign\_history (operator\_role);



CREATE INDEX IF NOT EXISTS idx\_campaign\_status

&#x20;   ON campaign\_history (status);



CREATE INDEX IF NOT EXISTS idx\_campaign\_created\_at

&#x20;   ON campaign\_history (created\_at DESC);



\-- 约束: operator\_role 只允许 1(采购), 2(策划), 3(客户)

ALTER TABLE campaign\_history

&#x20;   ADD CONSTRAINT chk\_operator\_role

&#x20;   CHECK (operator\_role IN (1, 2, 3));



\-- 约束: status 枚举

ALTER TABLE campaign\_history

&#x20;   ADD CONSTRAINT chk\_campaign\_status

&#x20;   CHECK (status IN ('active', 'committed', 'archived'));



COMMENT ON TABLE campaign\_history IS '寻星任务历史表 — 记录每次检索任务的意图、决策与结果';

COMMENT ON COLUMN campaign\_history.operator\_role IS '操作角色: 1=采购, 2=策划, 3=客户';

COMMENT ON COLUMN campaign\_history.query\_vector\_snapshot IS '最终查询向量的 JSON 序列化，用于品牌偏好沉淀';



\-- campaign\_history 结构演进：动态偏好隔离

ALTER TABLE campaign\_history

&#x20;   ADD COLUMN IF NOT EXISTS user\_id INTEGER REFERENCES users(id),

&#x20;   ADD COLUMN IF NOT EXISTS spu\_id INTEGER REFERENCES brand\_spus(spu\_id),

&#x20;   ADD COLUMN IF NOT EXISTS dynamic\_intent\_vector JSONB;



CREATE INDEX IF NOT EXISTS idx\_campaign\_user\_spu

&#x20;   ON campaign\_history (user\_id, spu\_id, created\_at DESC);





\-- ============================================================

\-- 4. export\_dictionary — 智能导出映射字典表

\-- ============================================================

CREATE TABLE IF NOT EXISTS export\_dictionary (

&#x20;   mapping\_id          SERIAL          PRIMARY KEY,

&#x20;   user\_input\_header   VARCHAR(256)    NOT NULL,

&#x20;   mapped\_standard\_key VARCHAR(256)    NOT NULL,

&#x20;   confidence          DECIMAL(3,2)    DEFAULT 1.00,

&#x20;   source              VARCHAR(16)     DEFAULT 'user',

&#x20;   usage\_count         INTEGER         DEFAULT 1,

&#x20;   created\_at          TIMESTAMP       DEFAULT NOW(),

&#x20;   updated\_at          TIMESTAMP       DEFAULT NOW()

);



\-- 联合唯一约束: 同一个用户输入表头 + 标准字段只能有一条映射

CREATE UNIQUE INDEX IF NOT EXISTS idx\_export\_dict\_mapping

&#x20;   ON export\_dictionary (user\_input\_header, mapped\_standard\_key);



\-- 推荐排序索引: 按使用次数降序

CREATE INDEX IF NOT EXISTS idx\_export\_dict\_usage

&#x20;   ON export\_dictionary (usage\_count DESC);



\-- 模糊搜索索引: 支持 LIKE '%xxx%' 查询

CREATE INDEX IF NOT EXISTS idx\_export\_dict\_header\_trgm

&#x20;   ON export\_dictionary USING GIN (user\_input\_header gin\_trgm\_ops);



\-- 注: gin\_trgm\_ops 需要 pg\_trgm 扩展，如果不可用则使用普通索引

\-- 如果上面的 GIN 索引创建失败，取消注释下面这行:

\-- CREATE INDEX IF NOT EXISTS idx\_export\_dict\_header ON export\_dictionary (user\_input\_header);



CREATE TRIGGER trg\_export\_dict\_updated\_at

&#x20;   BEFORE UPDATE ON export\_dictionary

&#x20;   FOR EACH ROW

&#x20;   EXECUTE FUNCTION update\_updated\_at\_column();



COMMENT ON TABLE export\_dictionary IS '智能导出映射字典 — 存储用户确认的非标准表头到系统标准字段的映射';

COMMENT ON COLUMN export\_dictionary.confidence IS '匹配置信度: AI 推荐为 0.xx，用户确认为 1.00';

COMMENT ON COLUMN export\_dictionary.source IS '来源: user=用户确认, ai=AI推荐';





\-- ============================================================

\-- 5. influencer\_notes — 达人笔记明细表

\-- ============================================================

CREATE TABLE IF NOT EXISTS influencer\_notes (

&#x20;   note\_id                 VARCHAR(64)     PRIMARY KEY,

&#x20;   influencer\_id           INTEGER         NOT NULL REFERENCES influencer\_basics(internal\_id) ON DELETE CASCADE,

&#x20;   note\_type               VARCHAR(16)     DEFAULT '图文',

&#x20;   is\_ad                   BOOLEAN         DEFAULT FALSE,

&#x20;   impressions             INTEGER         DEFAULT 0,

&#x20;   reads                   INTEGER         DEFAULT 0,

&#x20;   likes                   INTEGER         DEFAULT 0,

&#x20;   comments                INTEGER         DEFAULT 0,

&#x20;   collections             INTEGER         DEFAULT 0,

&#x20;   shares                  INTEGER         DEFAULT 0,

&#x20;   video\_completion\_rate   DECIMAL(5,4),

&#x20;   cover\_image\_url         TEXT,

&#x20;   published\_at            TIMESTAMP

);



\-- 索引

CREATE INDEX IF NOT EXISTS idx\_notes\_influencer\_id

&#x20;   ON influencer\_notes (influencer\_id);



CREATE INDEX IF NOT EXISTS idx\_notes\_published\_at

&#x20;   ON influencer\_notes (published\_at DESC);



CREATE INDEX IF NOT EXISTS idx\_notes\_type

&#x20;   ON influencer\_notes (note\_type);



CREATE INDEX IF NOT EXISTS idx\_notes\_is\_ad

&#x20;   ON influencer\_notes (is\_ad);



COMMENT ON TABLE influencer\_notes IS '达人笔记明细表 — 存储每篇笔记的结构化数据，支撑 34 维数据矩阵';

COMMENT ON COLUMN influencer\_notes.video\_completion\_rate IS '视频完播率，仅视频笔记有值，取值 0.0000 \~ 1.0000';





\-- ============================================================

\-- 6. fulfillment\_records — 履约记录表

\-- ============================================================

CREATE TABLE IF NOT EXISTS fulfillment\_records (

&#x20;   record\_id           SERIAL          PRIMARY KEY,

&#x20;   campaign\_id         INTEGER         NOT NULL REFERENCES campaign\_history(campaign\_id) ON DELETE CASCADE,

&#x20;   action\_type         VARCHAR(16)     NOT NULL,

&#x20;   influencer\_ids      JSONB           DEFAULT '\[]'::jsonb,

&#x20;   payload\_snapshot    JSONB,

&#x20;   operator\_id         INTEGER,

&#x20;   created\_at          TIMESTAMP       DEFAULT NOW()

);



\-- 索引

CREATE INDEX IF NOT EXISTS idx\_fulfillment\_campaign

&#x20;   ON fulfillment\_records (campaign\_id);



CREATE INDEX IF NOT EXISTS idx\_fulfillment\_action

&#x20;   ON fulfillment\_records (action\_type);



CREATE INDEX IF NOT EXISTS idx\_fulfillment\_created\_at

&#x20;   ON fulfillment\_records (created\_at DESC);



\-- 约束: action\_type 枚举

ALTER TABLE fulfillment\_records

&#x20;   ADD CONSTRAINT chk\_action\_type

&#x20;   CHECK (action\_type IN ('selected', 'invited', 'ordered', 'delivered', 'settled'));



COMMENT ON TABLE fulfillment\_records IS '履约记录表 — 存储邀约、下单、交付、结算等操作的历史快照';

COMMENT ON COLUMN fulfillment\_records.action\_type IS '操作类型: selected/invited/ordered/delivered/settled';





\-- ============================================================

\-- 创建只读视图: 达人完整画像（JOIN 笔记统计）

\-- ============================================================

CREATE OR REPLACE VIEW v\_influencer\_profile AS

SELECT

&#x20;   ib.internal\_id,

&#x20;   ib.red\_id,

&#x20;   ib.nickname,

&#x20;   ib.avatar\_url,

&#x20;   ib.gender,

&#x20;   ib.region,

&#x20;   ib.followers,

&#x20;   ib.likes AS total\_likes,

&#x20;   ib.collections AS total\_collections,

&#x20;   ib.notes\_count,

&#x20;   ib.ad\_ratio\_30d,

&#x20;   ib.tags,

&#x20;   ib.pricing,

&#x20;   ib.created\_at,

&#x20;   ib.updated\_at,

&#x20;   -- 笔记聚合统计

&#x20;   COALESCE(ns.avg\_likes, 0)           AS avg\_note\_likes,

&#x20;   COALESCE(ns.avg\_comments, 0)        AS avg\_note\_comments,

&#x20;   COALESCE(ns.avg\_collections, 0)     AS avg\_note\_collections,

&#x20;   COALESCE(ns.total\_impressions, 0)   AS total\_impressions,

&#x20;   COALESCE(ns.ad\_notes\_count, 0)      AS ad\_notes\_count,

&#x20;   COALESCE(ns.non\_ad\_notes\_count, 0)  AS non\_ad\_notes\_count

FROM influencer\_basics ib

LEFT JOIN (

&#x20;   SELECT

&#x20;       influencer\_id,

&#x20;       ROUND(AVG(likes), 2)                        AS avg\_likes,

&#x20;       ROUND(AVG(comments), 2)                     AS avg\_comments,

&#x20;       ROUND(AVG(collections), 2)                  AS avg\_collections,

&#x20;       SUM(impressions)                             AS total\_impressions,

&#x20;       COUNT(\*) FILTER (WHERE is\_ad = TRUE)         AS ad\_notes\_count,

&#x20;       COUNT(\*) FILTER (WHERE is\_ad = FALSE)        AS non\_ad\_notes\_count

&#x20;   FROM influencer\_notes

&#x20;   GROUP BY influencer\_id

) ns ON ib.internal\_id = ns.influencer\_id;



COMMENT ON VIEW v\_influencer\_profile IS '达人完整画像视图 — JOIN 笔记统计数据，供资产库查询使用';





\-- ============================================================

\-- 初始化完成标记

\-- ============================================================

DO $$

BEGIN

&#x20;   RAISE NOTICE '✅ Σ.Match PostgreSQL Schema 初始化完成';

&#x20;   RAISE NOTICE '   - influencer\_basics    (达人基础信息)';

&#x20;   RAISE NOTICE '   - users                (操盘手账户)';

&#x20;   RAISE NOTICE '   - brand\_spus           (品牌SPU资产)';

&#x20;   RAISE NOTICE '   - collaborations       (历史合作映射)';

&#x20;   RAISE NOTICE '   - campaign\_history      (寻星任务历史)';

&#x20;   RAISE NOTICE '   - export\_dictionary     (导出映射字典)';

&#x20;   RAISE NOTICE '   - influencer\_notes      (达人笔记明细)';

&#x20;   RAISE NOTICE '   - fulfillment\_records   (履约记录)';

&#x20;   RAISE NOTICE '   - v\_influencer\_profile  (达人画像视图)';

END $$;



```



\### `backend/db/\_\_init\_\_.py`



```python

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



from config import pg\_config



logger = logging.getLogger(\_\_name\_\_)





class Database:

&#x20;   """PostgreSQL 连接池管理器"""



&#x20;   def \_\_init\_\_(self, min\_conn: int = 2, max\_conn: int = 10):

&#x20;       self.\_pool: Optional\[ThreadedConnectionPool] = None

&#x20;       self.\_min\_conn = min\_conn

&#x20;       self.\_max\_conn = max\_conn



&#x20;   def connect(self) -> None:

&#x20;       """初始化连接池"""

&#x20;       if self.\_pool is not None:

&#x20;           return

&#x20;       self.\_pool = ThreadedConnectionPool(

&#x20;           minconn=self.\_min\_conn,

&#x20;           maxconn=self.\_max\_conn,

&#x20;           host=pg\_config.host,

&#x20;           port=pg\_config.port,

&#x20;           dbname=pg\_config.database,

&#x20;           user=pg\_config.user,

&#x20;           password=pg\_config.password,

&#x20;       )

&#x20;       logger.info(

&#x20;           "PostgreSQL 连接池已初始化: %s@%s:%d/%s (min=%d, max=%d)",

&#x20;           pg\_config.user, pg\_config.host, pg\_config.port,

&#x20;           pg\_config.database, self.\_min\_conn, self.\_max\_conn,

&#x20;       )



&#x20;   def close(self) -> None:

&#x20;       """关闭连接池"""

&#x20;       if self.\_pool:

&#x20;           self.\_pool.closeall()

&#x20;           self.\_pool = None

&#x20;           logger.info("PostgreSQL 连接池已关闭")



&#x20;   @contextmanager

&#x20;   def get\_conn(self):

&#x20;       """获取数据库连接（上下文管理器）"""

&#x20;       if self.\_pool is None:

&#x20;           self.connect()

&#x20;       conn = self.\_pool.getconn()

&#x20;       try:

&#x20;           yield conn

&#x20;           conn.commit()

&#x20;       except Exception:

&#x20;           conn.rollback()

&#x20;           raise

&#x20;       finally:

&#x20;           self.\_pool.putconn(conn)



&#x20;   @contextmanager

&#x20;   def get\_cursor(self, cursor\_factory=None):

&#x20;       """获取游标（上下文管理器）"""

&#x20;       factory = cursor\_factory or psycopg2.extras.RealDictCursor

&#x20;       with self.get\_conn() as conn:

&#x20;           with conn.cursor(cursor\_factory=factory) as cur:

&#x20;               yield cur



&#x20;   # ================================================================

&#x20;   # influencer\_basics CRUD

&#x20;   # ================================================================



&#x20;   def insert\_influencer(self, data: Dict\[str, Any]) -> int:

&#x20;       """插入达人基础信息，返回 internal\_id"""

&#x20;       sql = """

&#x20;           INSERT INTO influencer\_basics

&#x20;               (red\_id, nickname, avatar\_url, gender, region, followers,

&#x20;                likes, collections, notes\_count, ad\_ratio\_30d,

&#x20;                latest\_note\_time, tags, pricing)

&#x20;           VALUES

&#x20;               (%(red\_id)s, %(nickname)s, %(avatar\_url)s, %(gender)s,

&#x20;                %(region)s, %(followers)s, %(likes)s, %(collections)s,

&#x20;                %(notes\_count)s, %(ad\_ratio\_30d)s, %(latest\_note\_time)s,

&#x20;                %(tags)s::jsonb, %(pricing)s::jsonb)

&#x20;           ON CONFLICT (red\_id) DO UPDATE SET

&#x20;               nickname = EXCLUDED.nickname,

&#x20;               avatar\_url = EXCLUDED.avatar\_url,

&#x20;               followers = EXCLUDED.followers,

&#x20;               likes = EXCLUDED.likes,

&#x20;               collections = EXCLUDED.collections,

&#x20;               notes\_count = EXCLUDED.notes\_count,

&#x20;               ad\_ratio\_30d = EXCLUDED.ad\_ratio\_30d,

&#x20;               latest\_note\_time = EXCLUDED.latest\_note\_time,

&#x20;               tags = EXCLUDED.tags,

&#x20;               pricing = EXCLUDED.pricing

&#x20;           RETURNING internal\_id

&#x20;       """

&#x20;       # 确保 JSONB 字段是字符串

&#x20;       data = dict(data)

&#x20;       if isinstance(data.get("tags"), (list, dict)):

&#x20;           data\["tags"] = json.dumps(data\["tags"], ensure\_ascii=False)

&#x20;       if isinstance(data.get("pricing"), (list, dict)):

&#x20;           data\["pricing"] = json.dumps(data\["pricing"], ensure\_ascii=False)



&#x20;       with self.get\_cursor() as cur:

&#x20;           cur.execute(sql, data)

&#x20;           row = cur.fetchone()

&#x20;           return row\["internal\_id"]



&#x20;   def get\_influencer\_by\_id(self, internal\_id: int) -> Optional\[Dict]:

&#x20;       """通过 internal\_id 查询达人"""

&#x20;       sql = "SELECT \* FROM influencer\_basics WHERE internal\_id = %s"

&#x20;       with self.get\_cursor() as cur:

&#x20;           cur.execute(sql, (internal\_id,))

&#x20;           return cur.fetchone()



&#x20;   def get\_influencer\_by\_red\_id(self, red\_id: str) -> Optional\[Dict]:

&#x20;       """通过小红书号查询达人"""

&#x20;       sql = "SELECT \* FROM influencer\_basics WHERE red\_id = %s"

&#x20;       with self.get\_cursor() as cur:

&#x20;           cur.execute(sql, (red\_id,))

&#x20;           return cur.fetchone()



&#x20;   def search\_influencers(

&#x20;       self,

&#x20;       region: Optional\[str] = None,

&#x20;       followers\_min: Optional\[int] = None,

&#x20;       followers\_max: Optional\[int] = None,

&#x20;       tags: Optional\[List\[str]] = None,

&#x20;       gender: Optional\[str] = None,

&#x20;       limit: int = 20,

&#x20;       offset: int = 0,

&#x20;       sort\_by: str = "followers",

&#x20;       sort\_order: str = "DESC",

&#x20;   ) -> Tuple\[List\[Dict], int]:

&#x20;       """多维度筛选达人列表，返回 (结果列表, 总数)"""

&#x20;       conditions = \[]

&#x20;       params: List\[Any] = \[]



&#x20;       if region:

&#x20;           conditions.append("region = %s")

&#x20;           params.append(region)

&#x20;       if followers\_min is not None:

&#x20;           conditions.append("followers >= %s")

&#x20;           params.append(followers\_min)

&#x20;       if followers\_max is not None:

&#x20;           conditions.append("followers <= %s")

&#x20;           params.append(followers\_max)

&#x20;       if gender:

&#x20;           conditions.append("gender = %s")

&#x20;           params.append(gender)

&#x20;       if tags:

&#x20;           # JSONB 包含查询: tags @> '\["穿搭"]'

&#x20;           conditions.append("tags @> %s::jsonb")

&#x20;           params.append(json.dumps(tags, ensure\_ascii=False))



&#x20;       where\_clause = " AND ".join(conditions) if conditions else "1=1"



&#x20;       # 白名单校验排序字段

&#x20;       allowed\_sort = {"followers", "likes", "collections", "ad\_ratio\_30d", "created\_at"}

&#x20;       if sort\_by not in allowed\_sort:

&#x20;           sort\_by = "followers"

&#x20;       if sort\_order.upper() not in ("ASC", "DESC"):

&#x20;           sort\_order = "DESC"



&#x20;       # 查询总数

&#x20;       count\_sql = f"SELECT COUNT(\*) AS total FROM influencer\_basics WHERE {where\_clause}"

&#x20;       with self.get\_cursor() as cur:

&#x20;           cur.execute(count\_sql, params)

&#x20;           total = cur.fetchone()\["total"]



&#x20;       # 查询数据

&#x20;       data\_sql = f"""

&#x20;           SELECT \* FROM influencer\_basics

&#x20;           WHERE {where\_clause}

&#x20;           ORDER BY {sort\_by} {sort\_order}

&#x20;           LIMIT %s OFFSET %s

&#x20;       """

&#x20;       with self.get\_cursor() as cur:

&#x20;           cur.execute(data\_sql, params + \[limit, offset])

&#x20;           rows = cur.fetchall()



&#x20;       return \[dict(r) for r in rows], total



&#x20;   # ================================================================

&#x20;   # campaign\_history CRUD

&#x20;   # ================================================================



&#x20;   def create\_campaign(self, data: Dict\[str, Any]) -> int:

&#x20;       """创建寻星任务，返回 campaign\_id"""

&#x20;       sql = """

&#x20;           INSERT INTO campaign\_history

&#x20;               (brand\_name, spu\_name, operator\_id, operator\_role,

&#x20;                user\_id, spu\_id, intent\_snapshot, dynamic\_intent\_vector, status)

&#x20;           VALUES

&#x20;               (%(brand\_name)s, %(spu\_name)s, %(operator\_id)s,

&#x20;                %(operator\_role)s, %(user\_id)s, %(spu\_id)s,

&#x20;                %(intent\_snapshot)s::jsonb, %(dynamic\_intent\_vector)s::jsonb, 'active')

&#x20;           RETURNING campaign\_id

&#x20;       """

&#x20;       data = dict(data)

&#x20;       if isinstance(data.get("intent\_snapshot"), (dict, list)):

&#x20;           data\["intent\_snapshot"] = json.dumps(data\["intent\_snapshot"], ensure\_ascii=False)

&#x20;       if isinstance(data.get("dynamic\_intent\_vector"), (dict, list)):

&#x20;           data\["dynamic\_intent\_vector"] = json.dumps(data\["dynamic\_intent\_vector"], ensure\_ascii=False)

&#x20;       data.setdefault("user\_id", None)

&#x20;       data.setdefault("spu\_id", None)

&#x20;       data.setdefault("dynamic\_intent\_vector", None)



&#x20;       with self.get\_cursor() as cur:

&#x20;           cur.execute(sql, data)

&#x20;           return cur.fetchone()\["campaign\_id"]



&#x20;   def commit\_campaign(

&#x20;       self,

&#x20;       campaign\_id: int,

&#x20;       selected\_ids: List\[int],

&#x20;       rejected\_ids: List\[int],

&#x20;       pending\_ids: List\[int],

&#x20;       query\_vector: Optional\[List\[float]] = None,

&#x20;   ) -> None:

&#x20;       """确认入库：更新任务状态为 committed"""

&#x20;       sql = """

&#x20;           UPDATE campaign\_history SET

&#x20;               selected\_influencer\_ids = %s::jsonb,

&#x20;               rejected\_influencer\_ids = %s::jsonb,

&#x20;               pending\_influencer\_ids = %s::jsonb,

&#x20;               query\_vector\_snapshot = %s::jsonb,

&#x20;               dynamic\_intent\_vector = COALESCE(%s::jsonb, dynamic\_intent\_vector),

&#x20;               status = 'committed',

&#x20;               committed\_at = NOW()

&#x20;           WHERE campaign\_id = %s

&#x20;       """

&#x20;       with self.get\_cursor() as cur:

&#x20;           cur.execute(sql, (

&#x20;               json.dumps(selected\_ids),

&#x20;               json.dumps(rejected\_ids),

&#x20;               json.dumps(pending\_ids),

&#x20;               json.dumps(query\_vector) if query\_vector else None,

&#x20;               json.dumps(query\_vector) if query\_vector else None,

&#x20;               campaign\_id,

&#x20;           ))



&#x20;   def get\_brand\_spu\_base\_vector(self, spu\_id: int) -> Optional\[List\[float]]:

&#x20;       sql = "SELECT base\_vector FROM brand\_spus WHERE spu\_id = %s"

&#x20;       with self.get\_cursor() as cur:

&#x20;           cur.execute(sql, (spu\_id,))

&#x20;           row = cur.fetchone()

&#x20;           if not row:

&#x20;               return None

&#x20;           vector = row.get("base\_vector")

&#x20;           if isinstance(vector, str):

&#x20;               try:

&#x20;                   vector = json.loads(vector)

&#x20;               except json.JSONDecodeError:

&#x20;                   return None

&#x20;           return vector



&#x20;   def get\_brand\_spu\_record(self, spu\_id: int) -> Optional\[Dict]:

&#x20;       sql = """

&#x20;           SELECT spu\_id, brand\_name, spu\_name, base\_vector, kol\_count

&#x20;           FROM brand\_spus

&#x20;           WHERE spu\_id = %s

&#x20;       """

&#x20;       with self.get\_cursor() as cur:

&#x20;           cur.execute(sql, (spu\_id,))

&#x20;           row = cur.fetchone()

&#x20;           return dict(row) if row else None



&#x20;   def get\_brand\_spu\_by\_name(self, brand\_name: str, spu\_name: str) -> Optional\[Dict]:

&#x20;       sql = """

&#x20;           SELECT spu\_id, brand\_name, spu\_name, base\_vector, kol\_count

&#x20;           FROM brand\_spus

&#x20;           WHERE brand\_name = %s AND spu\_name = %s

&#x20;       """

&#x20;       with self.get\_cursor() as cur:

&#x20;           cur.execute(sql, (brand\_name, spu\_name))

&#x20;           row = cur.fetchone()

&#x20;           return dict(row) if row else None



&#x20;   def ensure\_brand\_spu(self, brand\_name: str, spu\_name: str) -> int:

&#x20;       sql = """

&#x20;           INSERT INTO brand\_spus (brand\_name, spu\_name, kol\_count)

&#x20;           VALUES (%s, %s, 0)

&#x20;           ON CONFLICT (brand\_name, spu\_name) DO UPDATE

&#x20;           SET updated\_at = NOW()

&#x20;           RETURNING spu\_id

&#x20;       """

&#x20;       with self.get\_cursor() as cur:

&#x20;           cur.execute(sql, (brand\_name, spu\_name))

&#x20;           return int(cur.fetchone()\["spu\_id"])



&#x20;   def create\_campaign\_from\_spu(self, user\_id: int, spu\_id: int, initial\_vector: List\[float]) -> int:

&#x20;       sql = """

&#x20;           INSERT INTO campaign\_history

&#x20;               (brand\_name, spu\_name, operator\_id, operator\_role,

&#x20;                user\_id, spu\_id, dynamic\_intent\_vector, status)

&#x20;           SELECT

&#x20;               bs.brand\_name,

&#x20;               bs.spu\_name,

&#x20;               %s,

&#x20;               2,

&#x20;               %s,

&#x20;               bs.spu\_id,

&#x20;               %s::jsonb,

&#x20;               'active'

&#x20;           FROM brand\_spus bs

&#x20;           WHERE bs.spu\_id = %s

&#x20;           RETURNING campaign\_id

&#x20;       """

&#x20;       with self.get\_cursor() as cur:

&#x20;           cur.execute(sql, (user\_id, user\_id, json.dumps(initial\_vector), spu\_id))

&#x20;           row = cur.fetchone()

&#x20;           if not row:

&#x20;               raise ValueError(f"SPU 不存在: {spu\_id}")

&#x20;           return row\["campaign\_id"]



&#x20;   def get\_campaign\_intent\_vector(self, campaign\_id: int) -> Optional\[List\[float]]:

&#x20;       sql = "SELECT dynamic\_intent\_vector FROM campaign\_history WHERE campaign\_id = %s"

&#x20;       with self.get\_cursor() as cur:

&#x20;           cur.execute(sql, (campaign\_id,))

&#x20;           row = cur.fetchone()

&#x20;           if not row:

&#x20;               return None

&#x20;           vector = row.get("dynamic\_intent\_vector")

&#x20;           if isinstance(vector, str):

&#x20;               try:

&#x20;                   vector = json.loads(vector)

&#x20;               except json.JSONDecodeError:

&#x20;                   return None

&#x20;           return vector



&#x20;   def update\_campaign\_dynamic\_vector(self, campaign\_id: int, vector: List\[float]) -> None:

&#x20;       sql = """

&#x20;           UPDATE campaign\_history

&#x20;           SET dynamic\_intent\_vector = %s::jsonb

&#x20;           WHERE campaign\_id = %s

&#x20;       """

&#x20;       with self.get\_cursor() as cur:

&#x20;           cur.execute(sql, (json.dumps(vector), campaign\_id))



&#x20;   def get\_influencer\_profiles\_by\_ids(self, ids: List\[int]) -> List\[Dict]:

&#x20;       if not ids:

&#x20;           return \[]

&#x20;       sql = """

&#x20;           SELECT \* FROM v\_influencer\_profile

&#x20;           WHERE internal\_id = ANY(%s)

&#x20;       """

&#x20;       with self.get\_cursor() as cur:

&#x20;           cur.execute(sql, (ids,))

&#x20;           return \[dict(row) for row in cur.fetchall()]



&#x20;   def get\_brand\_collaboration\_influencer\_ids(self, spu\_id: int) -> List\[int]:

&#x20;       sql = """

&#x20;           SELECT influencer\_id

&#x20;           FROM collaborations

&#x20;           WHERE spu\_id = %s AND influencer\_id IS NOT NULL

&#x20;           ORDER BY collaboration\_date DESC NULLS LAST

&#x20;       """

&#x20;       with self.get\_cursor() as cur:

&#x20;           cur.execute(sql, (spu\_id,))

&#x20;           return \[int(row\["influencer\_id"]) for row in cur.fetchall()]



&#x20;   def update\_brand\_spu\_base\_vector(self, spu\_id: int, vector: List\[float], kol\_count: Optional\[int] = None) -> None:

&#x20;       sql = """

&#x20;           UPDATE brand\_spus

&#x20;           SET base\_vector = %s::jsonb,

&#x20;               kol\_count = COALESCE(%s, kol\_count),

&#x20;               updated\_at = NOW()

&#x20;           WHERE spu\_id = %s

&#x20;       """

&#x20;       with self.get\_cursor() as cur:

&#x20;           cur.execute(sql, (json.dumps(vector), kol\_count, spu\_id))



&#x20;   def list\_brand\_spus(self) -> List\[Dict]:

&#x20;       sql = "SELECT spu\_id, brand\_name, spu\_name, kol\_count FROM brand\_spus ORDER BY spu\_id ASC"

&#x20;       with self.get\_cursor() as cur:

&#x20;           cur.execute(sql)

&#x20;           return \[dict(row) for row in cur.fetchall()]



&#x20;   def get\_existing\_collaboration\_ids(self, spu\_id: int, influencer\_ids: List\[int]) -> List\[int]:

&#x20;       if not influencer\_ids:

&#x20;           return \[]

&#x20;       sql = """

&#x20;           SELECT influencer\_id

&#x20;           FROM collaborations

&#x20;           WHERE spu\_id = %s

&#x20;             AND influencer\_id = ANY(%s)

&#x20;       """

&#x20;       with self.get\_cursor() as cur:

&#x20;           cur.execute(sql, (spu\_id, influencer\_ids))

&#x20;           return \[int(row\["influencer\_id"]) for row in cur.fetchall()]



&#x20;   def insert\_collaborations(self, spu\_id: int, influencer\_ids: List\[int]) -> int:

&#x20;       if not influencer\_ids:

&#x20;           return 0

&#x20;       sql = """

&#x20;           INSERT INTO collaborations (influencer\_id, spu\_id, collaboration\_date)

&#x20;           SELECT UNNEST(%s::int\[]), %s, CURRENT\_DATE

&#x20;           ON CONFLICT (spu\_id, influencer\_id) DO NOTHING

&#x20;       """

&#x20;       with self.get\_cursor() as cur:

&#x20;           cur.execute(sql, (influencer\_ids, spu\_id))

&#x20;           return cur.rowcount or 0



&#x20;   def get\_campaigns\_by\_brand(

&#x20;       self, brand\_name: str, spu\_name: Optional\[str] = None

&#x20;   ) -> List\[Dict]:

&#x20;       """查询品牌+SPU 的历史任务"""

&#x20;       if spu\_name:

&#x20;           sql = """

&#x20;               SELECT \* FROM campaign\_history

&#x20;               WHERE brand\_name = %s AND spu\_name = %s

&#x20;               ORDER BY created\_at DESC

&#x20;           """

&#x20;           params = (brand\_name, spu\_name)

&#x20;       else:

&#x20;           sql = """

&#x20;               SELECT \* FROM campaign\_history

&#x20;               WHERE brand\_name = %s

&#x20;               ORDER BY created\_at DESC

&#x20;           """

&#x20;           params = (brand\_name,)



&#x20;       with self.get\_cursor() as cur:

&#x20;           cur.execute(sql, params)

&#x20;           return \[dict(r) for r in cur.fetchall()]



&#x20;   # ================================================================

&#x20;   # export\_dictionary CRUD

&#x20;   # ================================================================



&#x20;   def upsert\_mapping(

&#x20;       self, user\_input\_header: str, mapped\_standard\_key: str,

&#x20;       confidence: float = 1.00, source: str = "user"

&#x20;   ) -> int:

&#x20;       """插入或更新映射关系（UPSERT），返回 mapping\_id"""

&#x20;       sql = """

&#x20;           INSERT INTO export\_dictionary

&#x20;               (user\_input\_header, mapped\_standard\_key, confidence, source)

&#x20;           VALUES (%s, %s, %s, %s)

&#x20;           ON CONFLICT (user\_input\_header, mapped\_standard\_key) DO UPDATE SET

&#x20;               usage\_count = export\_dictionary.usage\_count + 1,

&#x20;               confidence = GREATEST(export\_dictionary.confidence, EXCLUDED.confidence),

&#x20;               source = EXCLUDED.source

&#x20;           RETURNING mapping\_id

&#x20;       """

&#x20;       with self.get\_cursor() as cur:

&#x20;           cur.execute(sql, (user\_input\_header, mapped\_standard\_key, confidence, source))

&#x20;           return cur.fetchone()\["mapping\_id"]



&#x20;   def suggest\_mappings(self, user\_input\_header: str, limit: int = 5) -> List\[Dict]:

&#x20;       """根据用户输入表头推荐映射候选"""

&#x20;       sql = """

&#x20;           SELECT \* FROM export\_dictionary

&#x20;           WHERE user\_input\_header ILIKE %s

&#x20;           ORDER BY usage\_count DESC, confidence DESC

&#x20;           LIMIT %s

&#x20;       """

&#x20;       with self.get\_cursor() as cur:

&#x20;           cur.execute(sql, (f"%{user\_input\_header}%", limit))

&#x20;           return \[dict(r) for r in cur.fetchall()]



&#x20;   # ================================================================

&#x20;   # influencer\_notes CRUD

&#x20;   # ================================================================



&#x20;   def insert\_note(self, data: Dict\[str, Any]) -> str:

&#x20;       """插入笔记记录"""

&#x20;       sql = """

&#x20;           INSERT INTO influencer\_notes

&#x20;               (note\_id, influencer\_id, note\_type, is\_ad, impressions,

&#x20;                reads, likes, comments, collections, shares,

&#x20;                video\_completion\_rate, cover\_image\_url, published\_at)

&#x20;           VALUES

&#x20;               (%(note\_id)s, %(influencer\_id)s, %(note\_type)s, %(is\_ad)s,

&#x20;                %(impressions)s, %(reads)s, %(likes)s, %(comments)s,

&#x20;                %(collections)s, %(shares)s, %(video\_completion\_rate)s,

&#x20;                %(cover\_image\_url)s, %(published\_at)s)

&#x20;           ON CONFLICT (note\_id) DO UPDATE SET

&#x20;               impressions = EXCLUDED.impressions,

&#x20;               reads = EXCLUDED.reads,

&#x20;               likes = EXCLUDED.likes,

&#x20;               comments = EXCLUDED.comments,

&#x20;               collections = EXCLUDED.collections,

&#x20;               shares = EXCLUDED.shares

&#x20;           RETURNING note\_id

&#x20;       """

&#x20;       with self.get\_cursor() as cur:

&#x20;           cur.execute(sql, data)

&#x20;           return cur.fetchone()\["note\_id"]



&#x20;   def get\_notes\_by\_influencer(self, influencer\_id: int) -> List\[Dict]:

&#x20;       """获取达人的全部笔记"""

&#x20;       sql = """

&#x20;           SELECT \* FROM influencer\_notes

&#x20;           WHERE influencer\_id = %s

&#x20;           ORDER BY published\_at DESC

&#x20;       """

&#x20;       with self.get\_cursor() as cur:

&#x20;           cur.execute(sql, (influencer\_id,))

&#x20;           return \[dict(r) for r in cur.fetchall()]



&#x20;   # ================================================================

&#x20;   # fulfillment\_records CRUD

&#x20;   # ================================================================



&#x20;   def create\_fulfillment(self, data: Dict\[str, Any]) -> int:

&#x20;       """创建履约记录"""

&#x20;       sql = """

&#x20;           INSERT INTO fulfillment\_records

&#x20;               (campaign\_id, action\_type, influencer\_ids, payload\_snapshot, operator\_id)

&#x20;           VALUES

&#x20;               (%(campaign\_id)s, %(action\_type)s, %(influencer\_ids)s::jsonb,

&#x20;                %(payload\_snapshot)s::jsonb, %(operator\_id)s)

&#x20;           RETURNING record\_id

&#x20;       """

&#x20;       data = dict(data)

&#x20;       if isinstance(data.get("influencer\_ids"), list):

&#x20;           data\["influencer\_ids"] = json.dumps(data\["influencer\_ids"])

&#x20;       if isinstance(data.get("payload\_snapshot"), dict):

&#x20;           data\["payload\_snapshot"] = json.dumps(data\["payload\_snapshot"], ensure\_ascii=False)



&#x20;       with self.get\_cursor() as cur:

&#x20;           cur.execute(sql, data)

&#x20;           return cur.fetchone()\["record\_id"]



&#x20;   def get\_fulfillment\_timeline(self, campaign\_id: int) -> List\[Dict]:

&#x20;       """获取任务的履约时间轴"""

&#x20;       sql = """

&#x20;           SELECT \* FROM fulfillment\_records

&#x20;           WHERE campaign\_id = %s

&#x20;           ORDER BY created\_at ASC

&#x20;       """

&#x20;       with self.get\_cursor() as cur:

&#x20;           cur.execute(sql, (campaign\_id,))

&#x20;           return \[dict(r) for r in cur.fetchall()]



&#x20;   def get\_influencer\_history(self, influencer\_id: int) -> List\[Dict]:

&#x20;       """获取达人的全部履约历史（跨任务）"""

&#x20;       sql = """

&#x20;           SELECT

&#x20;               ch.campaign\_id,

&#x20;               ch.brand\_name,

&#x20;               ch.spu\_name,

&#x20;               ch.operator\_role,

&#x20;               fr.action\_type,

&#x20;               fr.created\_at

&#x20;           FROM fulfillment\_records fr

&#x20;           JOIN campaign\_history ch ON fr.campaign\_id = ch.campaign\_id

&#x20;           WHERE fr.influencer\_ids @> %s::jsonb

&#x20;           ORDER BY fr.created\_at DESC

&#x20;       """

&#x20;       with self.get\_cursor() as cur:

&#x20;           cur.execute(sql, (json.dumps(\[influencer\_id]),))

&#x20;           return \[dict(r) for r in cur.fetchall()]





\# 全局单例

db = Database()



```



\### `backend/services/match\_service.py`



```python

from \_\_future\_\_ import annotations



import hashlib

import json

import logging

import re

import uuid

from typing import Any, Dict, List, Optional, Sequence, Tuple



import numpy as np



from config import milvus\_config

from db import db

from milvus import FIELD\_STYLE, milvus\_mgr

from services.intent\_parser import IntentParserService, intent\_parser\_service, value\_to\_text



try:  # Redis 基础设施未就绪时允许服务降级到内存缓存

&#x20;   from redis import search\_cache, task\_cache

except Exception:  # pragma: no cover - 依赖外部环境时使用降级路径

&#x20;   search\_cache = None

&#x20;   task\_cache = None



logger = logging.getLogger(\_\_name\_\_)



EXPERIMENT\_MODE\_LONG\_SENTENCE = "long\_sentence"

EXPERIMENT\_MODE\_FIELD\_TAGS = "field\_tags"

EXPERIMENT\_MODE\_FIELD\_TAGS\_WEIGHTED = "field\_tags\_weighted"

EXPERIMENT\_MODE\_FIELD\_TAGS\_EXPLICIT\_WEIGHT\_TEXT = "field\_tags\_explicit\_weight\_text"

EXPERIMENT\_MODE\_CHOICES = {

&#x20;   EXPERIMENT\_MODE\_LONG\_SENTENCE,

&#x20;   EXPERIMENT\_MODE\_FIELD\_TAGS,

&#x20;   EXPERIMENT\_MODE\_FIELD\_TAGS\_WEIGHTED,

&#x20;   EXPERIMENT\_MODE\_FIELD\_TAGS\_EXPLICIT\_WEIGHT\_TEXT,

}

DEFAULT\_VECTOR\_DIM = milvus\_config.embedding\_dim

ROCCHIO\_ALPHA = 1.0

ROCCHIO\_BETA = 0.2



\_LOCAL\_TASK\_STORE: Dict\[str, Dict\[str, Any]] = {}

\_LOCAL\_SEARCH\_CACHE: Dict\[str, List\[Dict\[str, Any]]] = {}





def \_normalize\_vector(vector: Sequence\[float]) -> List\[float]:

&#x20;   array = np.array(vector, dtype=np.float32)

&#x20;   norm = float(np.linalg.norm(array))

&#x20;   if norm == 0.0:

&#x20;       raise ValueError("query 向量不能为空或零向量。")

&#x20;   return (array / norm).astype(np.float32).tolist()







def \_tokenize\_text(text: str) -> List\[str]:

&#x20;   normalized = value\_to\_text(text)

&#x20;   if not normalized:

&#x20;       return \[]

&#x20;   segments = \[segment.strip() for segment in re.split(r"\[，,；;。\\n]+", normalized) if segment and segment.strip()]

&#x20;   tokens = \[]

&#x20;   for segment in segments or \[normalized]:

&#x20;       tokens.append(segment)

&#x20;       if len(segment) <= 8:

&#x20;           continue

&#x20;       bigrams = \[segment\[index:index + 2] for index in range(0, len(segment) - 1)]

&#x20;       tokens.extend(bigrams\[:12])

&#x20;   return list(dict.fromkeys(tokens))







def embed\_text\_to\_style\_vector(text: str, \*, dim: int = DEFAULT\_VECTOR\_DIM) -> List\[float]:

&#x20;   tokens = \_tokenize\_text(text)

&#x20;   if not tokens:

&#x20;       raise ValueError("embedding 输入文本不能为空。")

&#x20;   vector = np.zeros(dim, dtype=np.float32)

&#x20;   for token in tokens:

&#x20;       digest = hashlib.sha256(token.encode("utf-8")).digest()

&#x20;       seed = int.from\_bytes(digest\[:8], "big", signed=False)

&#x20;       rng = np.random.default\_rng(seed)

&#x20;       vector += rng.standard\_normal(dim).astype(np.float32)

&#x20;   return \_normalize\_vector(vector)







def \_normalize\_experiment\_mode(mode: str) -> str:

&#x20;   normalized = value\_to\_text(mode) or EXPERIMENT\_MODE\_LONG\_SENTENCE

&#x20;   if normalized not in EXPERIMENT\_MODE\_CHOICES:

&#x20;       raise ValueError(f"不支持的 experiment\_mode: {normalized}")

&#x20;   return normalized







def \_extract\_formatted\_tags(query\_plan: Dict\[str, Any]) -> List\[Dict\[str, Any]]:

&#x20;   results: List\[Dict\[str, Any]] = \[]

&#x20;   for item in query\_plan.get("formatted\_tags", query\_plan.get("tags", \[])):

&#x20;       tag = value\_to\_text(item.get("tag"))

&#x20;       field\_name = value\_to\_text(item.get("field"))

&#x20;       key = value\_to\_text(item.get("key")) or (f"{field\_name}::{tag}" if field\_name else tag)

&#x20;       if not tag:

&#x20;           continue

&#x20;       try:

&#x20;           default\_weight = float(item.get("default\_weight", 1.0))

&#x20;       except (TypeError, ValueError):

&#x20;           default\_weight = 1.0

&#x20;       results.append(

&#x20;           {

&#x20;               "key": key,

&#x20;               "field": field\_name,

&#x20;               "tag": tag,

&#x20;               "default\_weight": default\_weight,

&#x20;           }

&#x20;       )

&#x20;   return results







def \_build\_explicit\_weight\_text(tag\_entries: Sequence\[Dict\[str, Any]]) -> str:

&#x20;   parts = \[]

&#x20;   for item in tag\_entries:

&#x20;       prefix = f"{item\['field']}:" if item.get("field") else ""

&#x20;       parts.append(f"{prefix}{item\['tag']}({item\['weight']})")

&#x20;   return "，".join(parts)







def \_build\_preview\_lines(tag\_entries: Sequence\[Dict\[str, Any]], \*, include\_weight: bool) -> str:

&#x20;   lines = \[]

&#x20;   for item in tag\_entries:

&#x20;       prefix = f"{item\['field']}:" if item.get("field") else ""

&#x20;       if include\_weight:

&#x20;           lines.append(f"{prefix}{item\['tag']}({item\['weight']})")

&#x20;       else:

&#x20;           lines.append(f"{prefix}{item\['tag']}")

&#x20;   return "\\n".join(lines)





class MatchService:

&#x20;   """封装自然语言检索向量构建与 Milvus 检索流程。"""



&#x20;   def \_\_init\_\_(self, parser: Optional\[IntentParserService] = None):

&#x20;       self.parser = parser or intent\_parser\_service



&#x20;   def build\_query\_context(

&#x20;       self,

&#x20;       query\_plan: Dict\[str, Any],

&#x20;       \*,

&#x20;       experiment\_mode: str,

&#x20;       tag\_weights: Optional\[Dict\[str, Any]] = None,

&#x20;   ) -> Dict\[str, Any]:

&#x20;       mode = \_normalize\_experiment\_mode(experiment\_mode)

&#x20;       long\_sentence\_query = value\_to\_text(query\_plan.get("long\_sentence\_query"))

&#x20;       formatted\_query\_text = value\_to\_text(query\_plan.get("formatted\_query\_text"))

&#x20;       formatted\_tags = \_extract\_formatted\_tags(query\_plan)

&#x20;       normalized\_weights = self.\_normalize\_tag\_weights(tag\_weights)



&#x20;       if mode == EXPERIMENT\_MODE\_LONG\_SENTENCE:

&#x20;           return {

&#x20;               "experiment\_mode": mode,

&#x20;               "query\_vector": embed\_text\_to\_style\_vector(long\_sentence\_query),

&#x20;               "embedding\_input\_preview": long\_sentence\_query,

&#x20;               "formatted\_tags\_used": \[],

&#x20;               "tag\_weights\_used": {},

&#x20;               "long\_sentence\_query": long\_sentence\_query,

&#x20;               "formatted\_query\_text": formatted\_query\_text,

&#x20;           }



&#x20;       if mode == EXPERIMENT\_MODE\_FIELD\_TAGS\_EXPLICIT\_WEIGHT\_TEXT:

&#x20;           weighted\_tags = self.\_resolve\_weighted\_tags(formatted\_tags, normalized\_weights)

&#x20;           if not weighted\_tags:

&#x20;               return {

&#x20;                   "experiment\_mode": mode,

&#x20;                   "query\_vector": embed\_text\_to\_style\_vector(long\_sentence\_query),

&#x20;                   "embedding\_input\_preview": long\_sentence\_query,

&#x20;                   "formatted\_tags\_used": \[],

&#x20;                   "tag\_weights\_used": {},

&#x20;                   "long\_sentence\_query": long\_sentence\_query,

&#x20;                   "formatted\_query\_text": formatted\_query\_text,

&#x20;               }

&#x20;           explicit\_weight\_text = \_build\_explicit\_weight\_text(weighted\_tags)

&#x20;           return {

&#x20;               "experiment\_mode": mode,

&#x20;               "query\_vector": embed\_text\_to\_style\_vector(explicit\_weight\_text),

&#x20;               "embedding\_input\_preview": explicit\_weight\_text,

&#x20;               "formatted\_tags\_used": weighted\_tags,

&#x20;               "tag\_weights\_used": {item\["key"]: item\["weight"] for item in weighted\_tags},

&#x20;               "long\_sentence\_query": long\_sentence\_query,

&#x20;               "formatted\_query\_text": formatted\_query\_text,

&#x20;           }



&#x20;       weighted\_vectors = \[]

&#x20;       weighted\_tags = \[]

&#x20;       for item in formatted\_tags:

&#x20;           weight = 1.0

&#x20;           if mode == EXPERIMENT\_MODE\_FIELD\_TAGS\_WEIGHTED:

&#x20;               weight = normalized\_weights.get(item\["key"], normalized\_weights.get(item\["tag"], item\["default\_weight"]))

&#x20;           if weight <= 0:

&#x20;               continue

&#x20;           tag\_vector = np.array(embed\_text\_to\_style\_vector(item\["tag"]), dtype=np.float32)

&#x20;           weighted\_vectors.append(tag\_vector \* float(weight))

&#x20;           weighted\_tags.append(

&#x20;               {

&#x20;                   "key": item\["key"],

&#x20;                   "field": item\["field"],

&#x20;                   "tag": item\["tag"],

&#x20;                   "weight": float(weight),

&#x20;               }

&#x20;           )



&#x20;       if not weighted\_vectors:

&#x20;           return {

&#x20;               "experiment\_mode": mode,

&#x20;               "query\_vector": embed\_text\_to\_style\_vector(long\_sentence\_query),

&#x20;               "embedding\_input\_preview": long\_sentence\_query,

&#x20;               "formatted\_tags\_used": \[],

&#x20;               "tag\_weights\_used": {},

&#x20;               "long\_sentence\_query": long\_sentence\_query,

&#x20;               "formatted\_query\_text": formatted\_query\_text,

&#x20;           }



&#x20;       combined\_vector = np.sum(np.array(weighted\_vectors, dtype=np.float32), axis=0)

&#x20;       return {

&#x20;           "experiment\_mode": mode,

&#x20;           "query\_vector": \_normalize\_vector(combined\_vector),

&#x20;           "embedding\_input\_preview": \_build\_preview\_lines(

&#x20;               weighted\_tags,

&#x20;               include\_weight=mode == EXPERIMENT\_MODE\_FIELD\_TAGS\_WEIGHTED,

&#x20;           ),

&#x20;           "formatted\_tags\_used": weighted\_tags,

&#x20;           "tag\_weights\_used": {item\["key"]: item\["weight"] for item in weighted\_tags},

&#x20;           "long\_sentence\_query": long\_sentence\_query,

&#x20;           "formatted\_query\_text": formatted\_query\_text,

&#x20;       }



&#x20;   def retrieve(self, payload: Dict\[str, Any]) -> Dict\[str, Any]:

&#x20;       raw\_text = value\_to\_text(payload.get("raw\_text") or payload.get("query"))

&#x20;       intent = payload.get("intent")

&#x20;       if not isinstance(intent, dict):

&#x20;           intent = self.parser.parse(

&#x20;               raw\_text,

&#x20;               brand\_name=value\_to\_text(payload.get("brand\_name")),

&#x20;               spu\_name=value\_to\_text(payload.get("spu\_name")),

&#x20;           )

&#x20;       query\_plan = intent.get("query\_plan", {})

&#x20;       experiment\_mode = \_normalize\_experiment\_mode(value\_to\_text(payload.get("experiment\_mode")))

&#x20;       query\_context = self.build\_query\_context(

&#x20;           query\_plan,

&#x20;           experiment\_mode=experiment\_mode,

&#x20;           tag\_weights=payload.get("tag\_weights"),

&#x20;       )

&#x20;       vector\_field = value\_to\_text(payload.get("vector\_field")) or FIELD\_STYLE

&#x20;       top\_k = int(payload.get("top\_k") or 20)

&#x20;       scalar\_filters = self.\_merge\_scalar\_filters(intent.get("hard\_filters"), payload.get("scalar\_filters"))

&#x20;       cache\_enabled = bool(payload.get("use\_cache", True))

&#x20;       cache\_key = {

&#x20;           "raw\_text": raw\_text,

&#x20;           "query\_plan": query\_plan,

&#x20;           "scalar\_filters": scalar\_filters,

&#x20;           "top\_k": top\_k,

&#x20;           "vector\_field": vector\_field,

&#x20;           "experiment\_mode": experiment\_mode,

&#x20;           "tag\_weights": payload.get("tag\_weights") or {},

&#x20;       }



&#x20;       if cache\_enabled:

&#x20;           cached\_results = self.\_get\_cached\_results(cache\_key)

&#x20;           if cached\_results is not None:

&#x20;               return {

&#x20;                   "raw\_text": raw\_text,

&#x20;                   "intent": intent,

&#x20;                   "scalar\_filters": scalar\_filters,

&#x20;                   "vector\_field": vector\_field,

&#x20;                   "experiment\_mode": experiment\_mode,

&#x20;                   "embedding\_input\_preview": query\_context\["embedding\_input\_preview"],

&#x20;                   "tag\_weights\_used": query\_context\["tag\_weights\_used"],

&#x20;                   "results": cached\_results,

&#x20;                   "result\_count": len(cached\_results),

&#x20;                   "cached": True,

&#x20;               }



&#x20;       milvus\_mgr.connect()

&#x20;       milvus\_mgr.load\_collection()

&#x20;       results = milvus\_mgr.hybrid\_search(

&#x20;           vector\_field=vector\_field,

&#x20;           query\_vector=query\_context\["query\_vector"],

&#x20;           scalar\_filters=scalar\_filters,

&#x20;           top\_k=top\_k,

&#x20;       )

&#x20;       enriched\_results = self.\_enrich\_results(results)



&#x20;       if cache\_enabled:

&#x20;           self.\_set\_cached\_results(cache\_key, enriched\_results)



&#x20;       return {

&#x20;           "raw\_text": raw\_text,

&#x20;           "intent": intent,

&#x20;           "scalar\_filters": scalar\_filters,

&#x20;           "vector\_field": vector\_field,

&#x20;           "experiment\_mode": experiment\_mode,

&#x20;           "embedding\_input\_preview": query\_context\["embedding\_input\_preview"],

&#x20;           "tag\_weights\_used": query\_context\["tag\_weights\_used"],

&#x20;           "results": enriched\_results,

&#x20;           "result\_count": len(enriched\_results),

&#x20;           "cached": False,

&#x20;       }



&#x20;   def create\_campaign(self, user\_id: int, spu\_id: int) -> int:

&#x20;       """工作流 1: 新建项目，冷启动加载品牌 SPU 基因向量。"""

&#x20;       db.connect()

&#x20;       try:

&#x20;           base\_vector = db.get\_brand\_spu\_base\_vector(spu\_id)

&#x20;           if not base\_vector:

&#x20;               raise ValueError(f"SPU\[{spu\_id}] 缺少 base\_vector，请先跑批生成。")

&#x20;           return db.create\_campaign\_from\_spu(user\_id=user\_id, spu\_id=spu\_id, initial\_vector=base\_vector)

&#x20;       finally:

&#x20;           db.close()



&#x20;   def search\_influencers(self, campaign\_id: int, filters: Optional\[Dict\[str, Any]] = None, top\_k: int = 100) -> List\[Dict\[str, Any]]:

&#x20;       """工作流 2: Qdrant 查 ID + PostgreSQL 回表组装详情。"""

&#x20;       db.connect()

&#x20;       try:

&#x20;           intent\_vector = db.get\_campaign\_intent\_vector(campaign\_id)

&#x20;           if not intent\_vector:

&#x20;               raise ValueError(f"campaign\_id={campaign\_id} 未找到 dynamic\_intent\_vector。")

&#x20;           milvus\_mgr.connect()

&#x20;           milvus\_mgr.load\_collection()

&#x20;           qdrant\_results = milvus\_mgr.hybrid\_search(

&#x20;               query\_vector=intent\_vector,

&#x20;               scalar\_filters=filters or {},

&#x20;               top\_k=top\_k,

&#x20;           )

&#x20;           matched\_ids = \[int(hit\["id"]) for hit in qdrant\_results]

&#x20;           profiles = db.get\_influencer\_profiles\_by\_ids(matched\_ids)

&#x20;           profiles\_map = {int(item\["internal\_id"]): item for item in profiles}

&#x20;           ranked = \[]

&#x20;           for hit in qdrant\_results:

&#x20;               internal\_id = int(hit\["id"])

&#x20;               ranked.append(

&#x20;                   {

&#x20;                       "internal\_id": internal\_id,

&#x20;                       "score": float(hit\["score"]),

&#x20;                       "distance": float(hit\["distance"]),

&#x20;                       "profile": profiles\_map.get(internal\_id, {}),

&#x20;                   }

&#x20;               )

&#x20;           return ranked

&#x20;       finally:

&#x20;           db.close()



&#x20;   def update\_campaign\_preference(self, campaign\_id: int, liked\_id: int, \*, alpha: float = ROCCHIO\_ALPHA, beta: float = ROCCHIO\_BETA) -> List\[float]:

&#x20;       """工作流 3: 用户反馈触发 Rocchio 向量平移。"""

&#x20;       milvus\_mgr.connect()

&#x20;       records = milvus\_mgr.retrieve\_by\_ids(\[liked\_id], with\_vectors=True)

&#x20;       if not records:

&#x20;           raise ValueError(f"未找到向量 ID: {liked\_id}")

&#x20;       target\_vector = records\[0].vector

&#x20;       if isinstance(target\_vector, dict):

&#x20;           target\_vector = target\_vector.get("embedding") or target\_vector.get(FIELD\_STYLE)

&#x20;       if target\_vector is None:

&#x20;           raise ValueError(f"向量 ID {liked\_id} 缺少 embedding 数据")



&#x20;       db.connect()

&#x20;       try:

&#x20;           current\_vector = db.get\_campaign\_intent\_vector(campaign\_id)

&#x20;           if not current\_vector:

&#x20;               raise ValueError(f"campaign\_id={campaign\_id} 未找到 dynamic\_intent\_vector")

&#x20;           new\_vector = self.calculate\_rocchio(current\_vector, target\_vector, alpha=alpha, beta=beta)

&#x20;           db.update\_campaign\_dynamic\_vector(campaign\_id, new\_vector)

&#x20;           return new\_vector

&#x20;       finally:

&#x20;           db.close()



&#x20;   def submit\_retrieve\_task(self, payload: Dict\[str, Any]) -> Dict\[str, Any]:

&#x20;       task\_id = value\_to\_text(payload.get("task\_id")) or uuid.uuid4().hex

&#x20;       meta = {

&#x20;           "raw\_text": value\_to\_text(payload.get("raw\_text") or payload.get("query")),

&#x20;           "experiment\_mode": value\_to\_text(payload.get("experiment\_mode")) or EXPERIMENT\_MODE\_LONG\_SENTENCE,

&#x20;       }

&#x20;       self.\_create\_task(task\_id, meta)

&#x20;       self.\_update\_task\_status(task\_id, "running", 0.2, "开始解析意图并执行检索")

&#x20;       try:

&#x20;           result = self.retrieve(payload)

&#x20;           self.\_set\_task\_result(task\_id, result)

&#x20;           return {

&#x20;               "task\_id": task\_id,

&#x20;               "status": "done",

&#x20;               "result": result,

&#x20;           }

&#x20;       except Exception as exc:

&#x20;           self.\_set\_task\_error(task\_id, str(exc))

&#x20;           raise



&#x20;   def get\_task\_info(self, task\_id: str) -> Optional\[Dict\[str, Any]]:

&#x20;       local\_info = \_LOCAL\_TASK\_STORE.get(task\_id)

&#x20;       if task\_cache is None:

&#x20;           return local\_info

&#x20;       try:

&#x20;           cached = task\_cache.get\_task\_info(task\_id)

&#x20;           return cached or local\_info

&#x20;       except Exception:

&#x20;           return local\_info



&#x20;   @staticmethod

&#x20;   def \_normalize\_tag\_weights(tag\_weights: Optional\[Dict\[str, Any]]) -> Dict\[str, float]:

&#x20;       normalized: Dict\[str, float] = {}

&#x20;       for key, value in (tag\_weights or {}).items():

&#x20;           try:

&#x20;               weight = float(value)

&#x20;           except (TypeError, ValueError):

&#x20;               continue

&#x20;           if weight <= 0:

&#x20;               continue

&#x20;           normalized\[value\_to\_text(key)] = weight

&#x20;       return normalized



&#x20;   def \_resolve\_weighted\_tags(

&#x20;       self,

&#x20;       formatted\_tags: Sequence\[Dict\[str, Any]],

&#x20;       normalized\_weights: Dict\[str, float],

&#x20;   ) -> List\[Dict\[str, Any]]:

&#x20;       results: List\[Dict\[str, Any]] = \[]

&#x20;       for item in formatted\_tags:

&#x20;           weight = normalized\_weights.get(item\["key"], normalized\_weights.get(item\["tag"], item\["default\_weight"]))

&#x20;           if weight <= 0:

&#x20;               continue

&#x20;           results.append(

&#x20;               {

&#x20;                   "key": item\["key"],

&#x20;                   "field": item\["field"],

&#x20;                   "tag": item\["tag"],

&#x20;                   "weight": float(weight),

&#x20;               }

&#x20;           )

&#x20;       return results



&#x20;   @staticmethod

&#x20;   def calculate\_rocchio(current\_vector: Sequence\[float], target\_vector: Sequence\[float], \*, alpha: float = ROCCHIO\_ALPHA, beta: float = ROCCHIO\_BETA) -> List\[float]:

&#x20;       current = np.array(current\_vector, dtype=np.float32)

&#x20;       target = np.array(target\_vector, dtype=np.float32)

&#x20;       if current.shape != target.shape:

&#x20;           raise ValueError("Rocchio 计算时向量维度不一致")

&#x20;       updated = alpha \* current + beta \* target

&#x20;       return \_normalize\_vector(updated)



&#x20;   @staticmethod

&#x20;   def \_merge\_scalar\_filters(base\_filters: Optional\[Dict\[str, Any]], extra\_filters: Optional\[Dict\[str, Any]]) -> Dict\[str, Any]:

&#x20;       merged = dict(base\_filters or {})

&#x20;       for key, value in (extra\_filters or {}).items():

&#x20;           if value in (None, "", \[], {}):

&#x20;               continue

&#x20;           merged\[key] = value

&#x20;       return merged



&#x20;   def \_enrich\_results(self, milvus\_results: List\[Dict\[str, Any]]) -> List\[Dict\[str, Any]]:

&#x20;       profiles = self.\_fetch\_profiles\_by\_ids(\[int(item\["id"]) for item in milvus\_results])

&#x20;       output = \[]

&#x20;       for item in milvus\_results:

&#x20;           internal\_id = int(item\["id"])

&#x20;           profile = profiles.get(internal\_id, {})

&#x20;           output.append(

&#x20;               {

&#x20;                   "internal\_id": internal\_id,

&#x20;                   "score": float(item.get("score", 0.0)),

&#x20;                   "distance": float(item.get("distance", 0.0)),

&#x20;                   "region": item.get("region"),

&#x20;                   "gender": item.get("gender"),

&#x20;                   "followers": item.get("followers"),

&#x20;                   "ad\_ratio": item.get("ad\_ratio"),

&#x20;                   "profile": profile,

&#x20;               }

&#x20;           )

&#x20;       return output



&#x20;   @staticmethod

&#x20;   def \_fetch\_profiles\_by\_ids(ids: Sequence\[int]) -> Dict\[int, Dict\[str, Any]]:

&#x20;       profiles: Dict\[int, Dict\[str, Any]] = {}

&#x20;       if not ids:

&#x20;           return profiles

&#x20;       try:

&#x20;           db.connect()

&#x20;           for internal\_id in ids:

&#x20;               row = db.get\_influencer\_by\_id(internal\_id)

&#x20;               if row:

&#x20;                   profiles\[internal\_id] = dict(row)

&#x20;       except Exception as exc:

&#x20;           logger.warning("补充 PostgreSQL 达人信息失败，将仅返回向量检索结果: %s", exc)

&#x20;       finally:

&#x20;           try:

&#x20;               db.close()

&#x20;           except Exception:

&#x20;               pass

&#x20;       return profiles



&#x20;   def \_get\_cached\_results(self, cache\_key: Dict\[str, Any]) -> Optional\[List\[Dict\[str, Any]]]:

&#x20;       local\_key = json.dumps(cache\_key, ensure\_ascii=False, sort\_keys=True)

&#x20;       if local\_key in \_LOCAL\_SEARCH\_CACHE:

&#x20;           return \_LOCAL\_SEARCH\_CACHE\[local\_key]

&#x20;       if search\_cache is None:

&#x20;           return None

&#x20;       try:

&#x20;           return search\_cache.get(cache\_key)

&#x20;       except Exception:

&#x20;           return None



&#x20;   def \_set\_cached\_results(self, cache\_key: Dict\[str, Any], results: List\[Dict\[str, Any]]) -> None:

&#x20;       local\_key = json.dumps(cache\_key, ensure\_ascii=False, sort\_keys=True)

&#x20;       \_LOCAL\_SEARCH\_CACHE\[local\_key] = results

&#x20;       if search\_cache is None:

&#x20;           return

&#x20;       try:

&#x20;           search\_cache.set(cache\_key, results)

&#x20;       except Exception:

&#x20;           pass



&#x20;   def \_create\_task(self, task\_id: str, meta: Dict\[str, Any]) -> None:

&#x20;       \_LOCAL\_TASK\_STORE\[task\_id] = {

&#x20;           "status": "pending",

&#x20;           "progress": 0.0,

&#x20;           "meta": meta,

&#x20;           "logs": \[],

&#x20;           "result": None,

&#x20;       }

&#x20;       if task\_cache is None:

&#x20;           return

&#x20;       try:

&#x20;           task\_cache.create\_task(task\_id, meta)

&#x20;       except Exception:

&#x20;           pass



&#x20;   def \_update\_task\_status(self, task\_id: str, status: str, progress: float, message: str) -> None:

&#x20;       \_LOCAL\_TASK\_STORE.setdefault(task\_id, {"logs": \[], "meta": {}, "result": None}).update(

&#x20;           {

&#x20;               "status": status,

&#x20;               "progress": progress,

&#x20;               "message": message,

&#x20;           }

&#x20;       )

&#x20;       if task\_cache is None:

&#x20;           return

&#x20;       try:

&#x20;           task\_cache.update\_status(task\_id, status, progress, message)

&#x20;       except Exception:

&#x20;           pass



&#x20;   def \_set\_task\_result(self, task\_id: str, result: Dict\[str, Any]) -> None:

&#x20;       \_LOCAL\_TASK\_STORE.setdefault(task\_id, {"logs": \[], "meta": {}}).update(

&#x20;           {

&#x20;               "status": "done",

&#x20;               "progress": 1.0,

&#x20;               "result": result,

&#x20;           }

&#x20;       )

&#x20;       if task\_cache is None:

&#x20;           return

&#x20;       try:

&#x20;           task\_cache.set\_result(task\_id, result)

&#x20;       except Exception:

&#x20;           pass



&#x20;   def \_set\_task\_error(self, task\_id: str, error\_message: str) -> None:

&#x20;       \_LOCAL\_TASK\_STORE.setdefault(task\_id, {"logs": \[], "meta": {}, "result": None}).update(

&#x20;           {

&#x20;               "status": "failed",

&#x20;               "progress": 1.0,

&#x20;               "message": error\_message,

&#x20;           }

&#x20;       )

&#x20;       if task\_cache is None:

&#x20;           return

&#x20;       try:

&#x20;           task\_cache.set\_error(task\_id, error\_message)

&#x20;       except Exception:

&#x20;           pass





match\_service = MatchService()



```



\### `backend/scripts/recompute\_brand\_base\_vectors.py`



```python

"""每日增量任务：拉取投后数据并按加权移动平均更新 brand\_spus.base\_vector。"""



from \_\_future\_\_ import annotations



import json

import logging

import os

import time

from datetime import datetime, timedelta

from pathlib import Path

from typing import Any, Dict, Iterable, List, Optional, Set, Tuple



import numpy as np

import requests



from db import db

from milvus import milvus\_mgr



logger = logging.getLogger(\_\_name\_\_)



\# OAuth 配置（建议通过环境变量注入）

CONFIG = {

&#x20;   "app\_id": int(os.getenv("XHS\_APP\_ID", "0")),

&#x20;   "secret": os.getenv("XHS\_APP\_SECRET", ""),

&#x20;   "auth\_code": os.getenv("XHS\_AUTH\_CODE", ""),

&#x20;   "token\_url": os.getenv(

&#x20;       "XHS\_TOKEN\_URL",

&#x20;       "https://adapi.xiaohongshu.com/api/open/oauth2/access\_token",

&#x20;   ),

&#x20;   "refresh\_url": os.getenv(

&#x20;       "XHS\_REFRESH\_URL",

&#x20;       "https://adapi.xiaohongshu.com/api/open/oauth2/refresh\_token",

&#x20;   ),

&#x20;   "token\_file": os.getenv(

&#x20;       "XHS\_TOKEN\_FILE",

&#x20;       str(Path(\_\_file\_\_).resolve().parent / "token\_pgy.json"),

&#x20;   ),

}



XHS\_API\_URL = os.getenv(

&#x20;   "XHS\_NOTE\_API\_URL",

&#x20;   "https://adapi.xiaohongshu.com/api/open/pgy/note/post/data",

)

XHS\_AUTH\_USER\_ID = os.getenv("XHS\_AUTH\_USER\_ID", "")

XHS\_TIMEOUT\_SECONDS = int(os.getenv("XHS\_TIMEOUT\_SECONDS", "20"))





def \_as\_int(value: Any) -> Optional\[int]:

&#x20;   try:

&#x20;       return int(value)

&#x20;   except (TypeError, ValueError):

&#x20;       return None





def \_extract\_embedding(record: Any) -> Optional\[List\[float]]:

&#x20;   vector = getattr(record, "vector", None)

&#x20;   if isinstance(vector, dict):

&#x20;       return vector.get("embedding")

&#x20;   return vector





class TokenManager:

&#x20;   """小红书开放平台 access token 管理器。"""



&#x20;   def \_\_init\_\_(self):

&#x20;       self.token\_info = self.\_load\_token\_from\_file()



&#x20;   def get\_token(self) -> str:

&#x20;       if not self.token\_info or self.\_is\_expired():

&#x20;           if self.token\_info.get("refresh\_token"):

&#x20;               try:

&#x20;                   self.\_refresh\_token()

&#x20;               except Exception as exc:

&#x20;                   logger.warning("刷新 token 失败，回退 auth\_code 获取新 token: %s", exc)

&#x20;                   self.\_get\_new\_token()

&#x20;           else:

&#x20;               self.\_get\_new\_token()

&#x20;       token = self.token\_info.get("access\_token")

&#x20;       if not token:

&#x20;           raise RuntimeError("token 获取失败，access\_token 为空")

&#x20;       return token



&#x20;   def \_get\_new\_token(self) -> None:

&#x20;       self.\_validate\_auth\_config(require\_refresh=False)

&#x20;       payload = {

&#x20;           "app\_id": CONFIG\["app\_id"],

&#x20;           "secret": CONFIG\["secret"],

&#x20;           "auth\_code": CONFIG\["auth\_code"],

&#x20;       }

&#x20;       response = requests.post(CONFIG\["token\_url"], json=payload, timeout=10)

&#x20;       response.raise\_for\_status()

&#x20;       result = response.json()

&#x20;       if not result.get("success"):

&#x20;           raise RuntimeError(f"获取 token 失败: {result.get('msg')}")

&#x20;       data = result.get("data") or {}

&#x20;       self.token\_info = {

&#x20;           "access\_token": data.get("access\_token"),

&#x20;           "refresh\_token": data.get("refresh\_token"),

&#x20;           "expires\_at": time.time() + int(data.get("access\_token\_expires\_in") or 0),

&#x20;       }

&#x20;       self.\_save\_token\_to\_file()



&#x20;   def \_refresh\_token(self) -> None:

&#x20;       self.\_validate\_auth\_config(require\_refresh=True)

&#x20;       payload = {

&#x20;           "app\_id": CONFIG\["app\_id"],

&#x20;           "secret": CONFIG\["secret"],

&#x20;           "refresh\_token": self.token\_info.get("refresh\_token"),

&#x20;       }

&#x20;       response = requests.post(CONFIG\["refresh\_url"], json=payload, timeout=10)

&#x20;       response.raise\_for\_status()

&#x20;       result = response.json()

&#x20;       if not result.get("success"):

&#x20;           raise RuntimeError(f"刷新 token 失败: {result.get('msg')}")

&#x20;       data = result.get("data") or {}

&#x20;       self.token\_info = {

&#x20;           "access\_token": data.get("access\_token"),

&#x20;           "refresh\_token": data.get("refresh\_token"),

&#x20;           "expires\_at": time.time() + int(data.get("access\_token\_expires\_in") or 0),

&#x20;       }

&#x20;       self.\_save\_token\_to\_file()



&#x20;   def \_is\_expired(self) -> bool:

&#x20;       # 提前 60 秒刷新，避免边界时间并发失败

&#x20;       return time.time() >= float(self.token\_info.get("expires\_at", 0)) - 60



&#x20;   def \_save\_token\_to\_file(self) -> None:

&#x20;       token\_file = Path(CONFIG\["token\_file"])

&#x20;       token\_file.parent.mkdir(parents=True, exist\_ok=True)

&#x20;       with token\_file.open("w", encoding="utf-8") as f:

&#x20;           json.dump(self.token\_info, f, ensure\_ascii=False)



&#x20;   def \_load\_token\_from\_file(self) -> Dict\[str, Any]:

&#x20;       token\_file = Path(CONFIG\["token\_file"])

&#x20;       if token\_file.exists():

&#x20;           try:

&#x20;               with token\_file.open("r", encoding="utf-8") as f:

&#x20;                   data = json.load(f)

&#x20;                   if isinstance(data, dict):

&#x20;                       return data

&#x20;           except Exception:

&#x20;               logger.warning("token 文件读取失败，将重新申请 token: %s", token\_file)

&#x20;       return {}



&#x20;   @staticmethod

&#x20;   def \_validate\_auth\_config(require\_refresh: bool) -> None:

&#x20;       if not CONFIG\["app\_id"] or not CONFIG\["secret"]:

&#x20;           raise RuntimeError("缺少 XHS\_APP\_ID 或 XHS\_APP\_SECRET")

&#x20;       if not require\_refresh and not CONFIG\["auth\_code"]:

&#x20;           raise RuntimeError("缺少 XHS\_AUTH\_CODE，无法首次换取 token")





def fetch\_xiaohongshu\_daily\_data(target\_date: Optional\[datetime] = None) -> List\[Dict\[str, Any]]:

&#x20;   """递归拉取昨日全量投后数据，处理分页。"""

&#x20;   if not XHS\_AUTH\_USER\_ID:

&#x20;       raise RuntimeError("缺少 XHS\_AUTH\_USER\_ID 环境变量")



&#x20;   date = target\_date or (datetime.utcnow() - timedelta(days=1))

&#x20;   day = date.strftime("%Y-%m-%d")

&#x20;   access\_token = TokenManager().get\_token()



&#x20;   headers = {

&#x20;       "Content-Type": "application/json",

&#x20;       "Authorization": f"Bearer {access\_token}",

&#x20;   }

&#x20;   payload: Dict\[str, Any] = {

&#x20;       "user\_id": XHS\_AUTH\_USER\_ID,

&#x20;       "date\_type": 2,

&#x20;       "start\_time": day,

&#x20;       "end\_time": day,

&#x20;       "page\_size": 100,

&#x20;   }



&#x20;   notes: List\[Dict\[str, Any]] = \[]

&#x20;   page\_num = 1

&#x20;   total\_page = 1



&#x20;   while page\_num <= total\_page:

&#x20;       payload\["page\_num"] = page\_num

&#x20;       response = requests.post(

&#x20;           XHS\_API\_URL,

&#x20;           json=payload,

&#x20;           headers=headers,

&#x20;           timeout=XHS\_TIMEOUT\_SECONDS,

&#x20;       )

&#x20;       response.raise\_for\_status()

&#x20;       body = response.json()



&#x20;       if body.get("code") != 0 or not body.get("success"):

&#x20;           logger.warning("小红书接口返回失败: page=%s body=%s", page\_num, body)

&#x20;           break



&#x20;       data = body.get("data") or {}

&#x20;       notes.extend(data.get("datas") or \[])

&#x20;       total\_page = int(data.get("total\_page") or 1)

&#x20;       page\_num += 1



&#x20;   logger.info("拉取到 %d 条投后笔记数据 (%s)", len(notes), day)

&#x20;   return notes





def group\_new\_kols(notes: Iterable\[Dict\[str, Any]]) -> Dict\[Tuple\[str, str], Set\[int]]:

&#x20;   grouped: Dict\[Tuple\[str, str], Set\[int]] = {}

&#x20;   for note in notes:

&#x20;       brand\_name = (note.get("brand\_user\_name") or "").strip()

&#x20;       spu\_name = (note.get("spu\_name") or "").strip()

&#x20;       kol\_id = \_as\_int(note.get("kol\_id"))

&#x20;       if not brand\_name or not spu\_name or kol\_id is None:

&#x20;           continue

&#x20;       grouped.setdefault((brand\_name, spu\_name), set()).add(kol\_id)

&#x20;   return grouped





def \_normalize(vec: np.ndarray) -> np.ndarray:

&#x20;   norm = np.linalg.norm(vec)

&#x20;   if norm > 0:

&#x20;       return vec / norm

&#x20;   return vec





def process\_and\_update\_vectors(target\_date: Optional\[datetime] = None) -> Dict\[str, int]:

&#x20;   """增量更新 base\_vector，并维护 kol\_count 和 collaborations 去重映射。"""

&#x20;   raw\_notes = fetch\_xiaohongshu\_daily\_data(target\_date)

&#x20;   grouped = group\_new\_kols(raw\_notes)



&#x20;   db.connect()

&#x20;   milvus\_mgr.connect()



&#x20;   metrics = {

&#x20;       "spu\_seen": 0,

&#x20;       "spu\_updated": 0,

&#x20;       "new\_collaborations": 0,

&#x20;       "vectors\_used": 0,

&#x20;   }



&#x20;   try:

&#x20;       for (brand\_name, spu\_name), kol\_ids in grouped.items():

&#x20;           metrics\["spu\_seen"] += 1

&#x20;           spu\_id = db.ensure\_brand\_spu(brand\_name, spu\_name)

&#x20;           spu\_record = db.get\_brand\_spu\_record(spu\_id)

&#x20;           if not spu\_record:

&#x20;               continue



&#x20;           old\_vector\_raw = spu\_record.get("base\_vector")

&#x20;           old\_count = int(spu\_record.get("kol\_count") or 0)

&#x20;           old\_vector = None

&#x20;           if old\_vector\_raw:

&#x20;               old\_vector = np.array(old\_vector\_raw, dtype=np.float32)



&#x20;           existing\_ids = set(db.get\_existing\_collaboration\_ids(spu\_id, list(kol\_ids)))

&#x20;           truly\_new\_ids = sorted(kol\_ids - existing\_ids)

&#x20;           if not truly\_new\_ids:

&#x20;               continue



&#x20;           records = milvus\_mgr.retrieve\_by\_ids(truly\_new\_ids, with\_vectors=True)

&#x20;           new\_vectors = \[]

&#x20;           fetched\_ids = \[]

&#x20;           for record in records:

&#x20;               vec = \_extract\_embedding(record)

&#x20;               if vec:

&#x20;                   new\_vectors.append(np.array(vec, dtype=np.float32))

&#x20;                   fetched\_ids.append(int(record.id))



&#x20;           if not new\_vectors:

&#x20;               continue



&#x20;           sum\_new = np.sum(np.array(new\_vectors, dtype=np.float32), axis=0)

&#x20;           new\_count = len(new\_vectors)



&#x20;           if old\_vector is not None and old\_count > 0:

&#x20;               updated\_vector = ((old\_vector \* old\_count) + sum\_new) / float(old\_count + new\_count)

&#x20;           else:

&#x20;               updated\_vector = sum\_new / float(new\_count)



&#x20;           updated\_vector = \_normalize(updated\_vector).astype(np.float32)

&#x20;           final\_count = old\_count + new\_count



&#x20;           db.update\_brand\_spu\_base\_vector(

&#x20;               spu\_id=spu\_id,

&#x20;               vector=updated\_vector.tolist(),

&#x20;               kol\_count=final\_count,

&#x20;           )

&#x20;           db.insert\_collaborations(spu\_id=spu\_id, influencer\_ids=fetched\_ids)



&#x20;           metrics\["spu\_updated"] += 1

&#x20;           metrics\["new\_collaborations"] += len(fetched\_ids)

&#x20;           metrics\["vectors\_used"] += new\_count



&#x20;       logger.info("增量向量更新完成: %s", json.dumps(metrics, ensure\_ascii=False))

&#x20;       return metrics

&#x20;   finally:

&#x20;       db.close()





def run() -> None:

&#x20;   logging.basicConfig(level=logging.INFO)

&#x20;   metrics = process\_and\_update\_vectors()

&#x20;   print(f"✅ 投后数据更新及增量向量计算完成: {json.dumps(metrics, ensure\_ascii=False)}")





if \_\_name\_\_ == "\_\_main\_\_":

&#x20;   run()



```



\### `backend/scripts/token\_pgy.json`



```json

{"access\_token": "93080eadf80c463ab06a8b3dbe07ae8f", "refresh\_token": "61decff71b665cf60d6e25cac0438717", "expires\_at": 1776929724.7289574}



```



\### `backend/requirements.txt`



```text

\# ============================================================

\# Σ.Match Sprint 1 基建层 Python 依赖

\# 安装: pip install -r requirements.txt

\# ============================================================



\# --- PostgreSQL ---

psycopg2-binary>=2.9.9       # PostgreSQL 驱动 (二进制预编译版)



\# --- Qdrant ---

qdrant-client>=1.9.0         # Qdrant Python SDK



\# --- Redis ---

redis>=5.0.0                 # Redis Python 客户端



\# --- Web API ---

fastapi>=0.115.0             # 后端服务框架

uvicorn>=0.30.0              # ASGI 运行器

openai>=1.75.0               # OpenAI 兼容 LLM 客户端（用于意图解析）



\# --- 测试与数值计算 ---

numpy>=1.26.0                # 查询向量拼装与归一化

httpx>=0.28.0                # FastAPI TestClient 依赖

requests>=2.32.0             # 定时任务拉取小红书投后数据



\# --- 工具 ---

python-dotenv>=1.0.0         # .env 文件加载



```



\### `backend/docker-compose.yml`



```yaml

\##############################################################################

\# Σ.Match 基建层 Docker Compose — Sprint 1

\# 服务清单: PostgreSQL 15 + Redis 7

\#

\# 启动命令:  docker-compose up -d

\# 停止命令:  docker-compose down

\# 清除数据:  docker-compose down -v

\##############################################################################



version: "3.8"



services:

&#x20; # ============================================================

&#x20; # PostgreSQL 15 — 关系型数据库

&#x20; # ============================================================

&#x20; postgres:

&#x20;   image: postgres:15-alpine

&#x20;   container\_name: sigma\_postgres

&#x20;   restart: unless-stopped

&#x20;   environment:

&#x20;     POSTGRES\_DB: ${POSTGRES\_DB:-sigma\_match}

&#x20;     POSTGRES\_USER: ${POSTGRES\_USER:-sigma}

&#x20;     POSTGRES\_PASSWORD: ${POSTGRES\_PASSWORD:-sigma\_secret\_2026}

&#x20;     PGDATA: /var/lib/postgresql/data/pgdata

&#x20;   ports:

&#x20;     - "${POSTGRES\_PORT:-5432}:5432"

&#x20;   volumes:

&#x20;     - postgres\_data:/var/lib/postgresql/data

&#x20;     - ./db/migrations/init.sql:/docker-entrypoint-initdb.d/01\_init.sql:ro

&#x20;   healthcheck:

&#x20;     test: \["CMD-SHELL", "pg\_isready -U ${POSTGRES\_USER:-sigma} -d ${POSTGRES\_DB:-sigma\_match}"]

&#x20;     interval: 10s

&#x20;     timeout: 5s

&#x20;     retries: 5

&#x20;   networks:

&#x20;     - sigma\_net



&#x20; # ============================================================

&#x20; # Redis 7 — 缓存 + 消息代理 + 任务状态存储

&#x20; # ============================================================

&#x20; redis:

&#x20;   image: redis:7-alpine

&#x20;   container\_name: sigma\_redis

&#x20;   restart: unless-stopped

&#x20;   command: >

&#x20;     redis-server

&#x20;     --appendonly yes

&#x20;     --appendfsync everysec

&#x20;     --save 900 1

&#x20;     --save 300 10

&#x20;     --save 60 10000

&#x20;     --maxmemory 512mb

&#x20;     --maxmemory-policy allkeys-lru

&#x20;     --requirepass ${REDIS\_PASSWORD:-sigma\_redis\_2026}

&#x20;   ports:

&#x20;     - "${REDIS\_PORT:-6379}:6379"

&#x20;   volumes:

&#x20;     - redis\_data:/data

&#x20;   healthcheck:

&#x20;     test: \["CMD", "redis-cli", "-a", "${REDIS\_PASSWORD:-sigma\_redis\_2026}", "ping"]

&#x20;     interval: 10s

&#x20;     timeout: 5s

&#x20;     retries: 5

&#x20;   networks:

&#x20;     - sigma\_net



\# ============================================================

\# 持久化卷

\# ============================================================

volumes:

&#x20; postgres\_data:

&#x20;   driver: local

&#x20; redis\_data:

&#x20;   driver: local



\# ============================================================

\# 网络

\# ============================================================

networks:

&#x20; sigma\_net:

&#x20;   driver: bridge



```



