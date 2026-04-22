-- ============================================================
-- Σ.Match 基建层 — PostgreSQL Schema 初始化
-- Sprint 1 · Task 1.1.1 ~ 1.1.4
--
-- 四张核心表:
--   1. influencer_basics    — 达人基础信息
--   2. campaign_history     — 寻星任务历史
--   3. export_dictionary    — 智能导出映射字典
--   4. influencer_notes     — 达人笔记明细
--   5. fulfillment_records  — 履约记录
--
-- 执行方式: Docker 容器启动时自动执行
--           或手动: psql -U sigma -d sigma_match -f init.sql
-- ============================================================

-- 启用扩展
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ============================================================
-- 1. influencer_basics — 达人基础信息表
-- ============================================================
CREATE TABLE IF NOT EXISTS influencer_basics (
    internal_id     SERIAL          PRIMARY KEY,
    red_id          VARCHAR(64)     NOT NULL,
    nickname        VARCHAR(128)    NOT NULL,
    avatar_url      TEXT,
    gender          VARCHAR(8)      DEFAULT '未知',
    region          VARCHAR(64),
    followers       INTEGER         DEFAULT 0,
    likes           INTEGER         DEFAULT 0,
    collections     INTEGER         DEFAULT 0,
    notes_count     INTEGER         DEFAULT 0,
    ad_ratio_30d    DECIMAL(5,4)    DEFAULT 0.0000,
    latest_note_time TIMESTAMP,
    tags            JSONB           DEFAULT '[]'::jsonb,
    pricing         JSONB           DEFAULT '{}'::jsonb,
    created_at      TIMESTAMP       DEFAULT NOW(),
    updated_at      TIMESTAMP       DEFAULT NOW()
);

-- 索引
CREATE UNIQUE INDEX IF NOT EXISTS idx_influencer_red_id
    ON influencer_basics (red_id);

CREATE INDEX IF NOT EXISTS idx_influencer_region
    ON influencer_basics (region);

CREATE INDEX IF NOT EXISTS idx_influencer_followers
    ON influencer_basics (followers);

CREATE INDEX IF NOT EXISTS idx_influencer_created_at
    ON influencer_basics (created_at);

CREATE INDEX IF NOT EXISTS idx_influencer_tags
    ON influencer_basics USING GIN (tags);

CREATE INDEX IF NOT EXISTS idx_influencer_ad_ratio
    ON influencer_basics (ad_ratio_30d);

-- updated_at 自动更新触发器
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_influencer_updated_at
    BEFORE UPDATE ON influencer_basics
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

COMMENT ON TABLE influencer_basics IS '达人基础信息表 — 存储每位达人的结构化数据，映射 Milvus 的 id 字段';
COMMENT ON COLUMN influencer_basics.internal_id IS '自增主键，与 Milvus Collection 的 id 字段一一映射';
COMMENT ON COLUMN influencer_basics.red_id IS '小红书号，全局唯一';
COMMENT ON COLUMN influencer_basics.ad_ratio_30d IS '近 30 天商单比例，取值 0.0000 ~ 1.0000';
COMMENT ON COLUMN influencer_basics.tags IS '达人标签数组，JSONB 格式，如 ["穿搭","高冷风"]';
COMMENT ON COLUMN influencer_basics.pricing IS '报价信息，JSONB 格式，含图文CPM、视频CPM等';


-- ============================================================
-- 2. users / brand_spus / collaborations
-- ============================================================
CREATE TABLE IF NOT EXISTS users (
    id          SERIAL          PRIMARY KEY,
    username    VARCHAR(64)     UNIQUE NOT NULL,
    role        VARCHAR(32)     DEFAULT 'operator',
    created_at  TIMESTAMP       DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS brand_spus (
    spu_id       SERIAL          PRIMARY KEY,
    brand_name   VARCHAR(128)    NOT NULL,
    spu_name     VARCHAR(256)    NOT NULL,
    base_vector  JSONB,
    kol_count    INTEGER         DEFAULT 0,
    created_at   TIMESTAMP       DEFAULT NOW(),
    updated_at   TIMESTAMP       DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_brand_spu_name
    ON brand_spus (brand_name, spu_name);

ALTER TABLE brand_spus
    ADD COLUMN IF NOT EXISTS kol_count INTEGER DEFAULT 0;

CREATE TRIGGER trg_brand_spus_updated_at
    BEFORE UPDATE ON brand_spus
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

CREATE TABLE IF NOT EXISTS collaborations (
    id                  SERIAL          PRIMARY KEY,
    influencer_id       INTEGER         REFERENCES influencer_basics(internal_id),
    spu_id              INTEGER         REFERENCES brand_spus(spu_id),
    collaboration_date  DATE,
    performance_score   DECIMAL(3,2)
);

CREATE INDEX IF NOT EXISTS idx_collab_spu_id
    ON collaborations (spu_id);

CREATE INDEX IF NOT EXISTS idx_collab_influencer_id
    ON collaborations (influencer_id);

CREATE UNIQUE INDEX IF NOT EXISTS idx_collab_spu_influencer_unique
    ON collaborations (spu_id, influencer_id);


-- ============================================================
-- 3. campaign_history — 寻星任务历史表
-- ============================================================
CREATE TABLE IF NOT EXISTS campaign_history (
    campaign_id             SERIAL          PRIMARY KEY,
    brand_name              VARCHAR(128)    NOT NULL,
    spu_name                VARCHAR(256)    NOT NULL,
    operator_id             INTEGER,
    operator_role           SMALLINT        NOT NULL DEFAULT 2,
    selected_influencer_ids JSONB           DEFAULT '[]'::jsonb,
    pending_influencer_ids  JSONB           DEFAULT '[]'::jsonb,
    rejected_influencer_ids JSONB           DEFAULT '[]'::jsonb,
    intent_snapshot         JSONB,
    query_vector_snapshot   JSONB,
    status                  VARCHAR(16)     DEFAULT 'active',
    created_at              TIMESTAMP       DEFAULT NOW(),
    committed_at            TIMESTAMP
);

-- 索引
CREATE INDEX IF NOT EXISTS idx_campaign_brand_spu
    ON campaign_history (brand_name, spu_name);

CREATE INDEX IF NOT EXISTS idx_campaign_operator_role
    ON campaign_history (operator_role);

CREATE INDEX IF NOT EXISTS idx_campaign_status
    ON campaign_history (status);

CREATE INDEX IF NOT EXISTS idx_campaign_created_at
    ON campaign_history (created_at DESC);

-- 约束: operator_role 只允许 1(采购), 2(策划), 3(客户)
ALTER TABLE campaign_history
    ADD CONSTRAINT chk_operator_role
    CHECK (operator_role IN (1, 2, 3));

-- 约束: status 枚举
ALTER TABLE campaign_history
    ADD CONSTRAINT chk_campaign_status
    CHECK (status IN ('active', 'committed', 'archived'));

COMMENT ON TABLE campaign_history IS '寻星任务历史表 — 记录每次检索任务的意图、决策与结果';
COMMENT ON COLUMN campaign_history.operator_role IS '操作角色: 1=采购, 2=策划, 3=客户';
COMMENT ON COLUMN campaign_history.query_vector_snapshot IS '最终查询向量的 JSON 序列化，用于品牌偏好沉淀';

-- campaign_history 结构演进：动态偏好隔离
ALTER TABLE campaign_history
    ADD COLUMN IF NOT EXISTS user_id INTEGER REFERENCES users(id),
    ADD COLUMN IF NOT EXISTS spu_id INTEGER REFERENCES brand_spus(spu_id),
    ADD COLUMN IF NOT EXISTS dynamic_intent_vector JSONB;

CREATE INDEX IF NOT EXISTS idx_campaign_user_spu
    ON campaign_history (user_id, spu_id, created_at DESC);


-- ============================================================
-- 4. export_dictionary — 智能导出映射字典表
-- ============================================================
CREATE TABLE IF NOT EXISTS export_dictionary (
    mapping_id          SERIAL          PRIMARY KEY,
    user_input_header   VARCHAR(256)    NOT NULL,
    mapped_standard_key VARCHAR(256)    NOT NULL,
    confidence          DECIMAL(3,2)    DEFAULT 1.00,
    source              VARCHAR(16)     DEFAULT 'user',
    usage_count         INTEGER         DEFAULT 1,
    created_at          TIMESTAMP       DEFAULT NOW(),
    updated_at          TIMESTAMP       DEFAULT NOW()
);

-- 联合唯一约束: 同一个用户输入表头 + 标准字段只能有一条映射
CREATE UNIQUE INDEX IF NOT EXISTS idx_export_dict_mapping
    ON export_dictionary (user_input_header, mapped_standard_key);

-- 推荐排序索引: 按使用次数降序
CREATE INDEX IF NOT EXISTS idx_export_dict_usage
    ON export_dictionary (usage_count DESC);

-- 模糊搜索索引: 支持 LIKE '%xxx%' 查询
CREATE INDEX IF NOT EXISTS idx_export_dict_header_trgm
    ON export_dictionary USING GIN (user_input_header gin_trgm_ops);

-- 注: gin_trgm_ops 需要 pg_trgm 扩展，如果不可用则使用普通索引
-- 如果上面的 GIN 索引创建失败，取消注释下面这行:
-- CREATE INDEX IF NOT EXISTS idx_export_dict_header ON export_dictionary (user_input_header);

CREATE TRIGGER trg_export_dict_updated_at
    BEFORE UPDATE ON export_dictionary
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

COMMENT ON TABLE export_dictionary IS '智能导出映射字典 — 存储用户确认的非标准表头到系统标准字段的映射';
COMMENT ON COLUMN export_dictionary.confidence IS '匹配置信度: AI 推荐为 0.xx，用户确认为 1.00';
COMMENT ON COLUMN export_dictionary.source IS '来源: user=用户确认, ai=AI推荐';


-- ============================================================
-- 5. influencer_notes — 达人笔记明细表
-- ============================================================
CREATE TABLE IF NOT EXISTS influencer_notes (
    note_id                 VARCHAR(64)     PRIMARY KEY,
    influencer_id           INTEGER         NOT NULL REFERENCES influencer_basics(internal_id) ON DELETE CASCADE,
    note_type               VARCHAR(16)     DEFAULT '图文',
    is_ad                   BOOLEAN         DEFAULT FALSE,
    impressions             INTEGER         DEFAULT 0,
    reads                   INTEGER         DEFAULT 0,
    likes                   INTEGER         DEFAULT 0,
    comments                INTEGER         DEFAULT 0,
    collections             INTEGER         DEFAULT 0,
    shares                  INTEGER         DEFAULT 0,
    video_completion_rate   DECIMAL(5,4),
    cover_image_url         TEXT,
    published_at            TIMESTAMP
);

-- 索引
CREATE INDEX IF NOT EXISTS idx_notes_influencer_id
    ON influencer_notes (influencer_id);

CREATE INDEX IF NOT EXISTS idx_notes_published_at
    ON influencer_notes (published_at DESC);

CREATE INDEX IF NOT EXISTS idx_notes_type
    ON influencer_notes (note_type);

CREATE INDEX IF NOT EXISTS idx_notes_is_ad
    ON influencer_notes (is_ad);

COMMENT ON TABLE influencer_notes IS '达人笔记明细表 — 存储每篇笔记的结构化数据，支撑 34 维数据矩阵';
COMMENT ON COLUMN influencer_notes.video_completion_rate IS '视频完播率，仅视频笔记有值，取值 0.0000 ~ 1.0000';


-- ============================================================
-- 6. fulfillment_records — 履约记录表
-- ============================================================
CREATE TABLE IF NOT EXISTS fulfillment_records (
    record_id           SERIAL          PRIMARY KEY,
    campaign_id         INTEGER         NOT NULL REFERENCES campaign_history(campaign_id) ON DELETE CASCADE,
    action_type         VARCHAR(16)     NOT NULL,
    influencer_ids      JSONB           DEFAULT '[]'::jsonb,
    payload_snapshot    JSONB,
    operator_id         INTEGER,
    created_at          TIMESTAMP       DEFAULT NOW()
);

-- 索引
CREATE INDEX IF NOT EXISTS idx_fulfillment_campaign
    ON fulfillment_records (campaign_id);

CREATE INDEX IF NOT EXISTS idx_fulfillment_action
    ON fulfillment_records (action_type);

CREATE INDEX IF NOT EXISTS idx_fulfillment_created_at
    ON fulfillment_records (created_at DESC);

-- 约束: action_type 枚举
ALTER TABLE fulfillment_records
    ADD CONSTRAINT chk_action_type
    CHECK (action_type IN ('selected', 'invited', 'ordered', 'delivered', 'settled'));

COMMENT ON TABLE fulfillment_records IS '履约记录表 — 存储邀约、下单、交付、结算等操作的历史快照';
COMMENT ON COLUMN fulfillment_records.action_type IS '操作类型: selected/invited/ordered/delivered/settled';


-- ============================================================
-- 创建只读视图: 达人完整画像（JOIN 笔记统计）
-- ============================================================
CREATE OR REPLACE VIEW v_influencer_profile AS
SELECT
    ib.internal_id,
    ib.red_id,
    ib.nickname,
    ib.avatar_url,
    ib.gender,
    ib.region,
    ib.followers,
    ib.likes AS total_likes,
    ib.collections AS total_collections,
    ib.notes_count,
    ib.ad_ratio_30d,
    ib.tags,
    ib.pricing,
    ib.created_at,
    ib.updated_at,
    -- 笔记聚合统计
    COALESCE(ns.avg_likes, 0)           AS avg_note_likes,
    COALESCE(ns.avg_comments, 0)        AS avg_note_comments,
    COALESCE(ns.avg_collections, 0)     AS avg_note_collections,
    COALESCE(ns.total_impressions, 0)   AS total_impressions,
    COALESCE(ns.ad_notes_count, 0)      AS ad_notes_count,
    COALESCE(ns.non_ad_notes_count, 0)  AS non_ad_notes_count
FROM influencer_basics ib
LEFT JOIN (
    SELECT
        influencer_id,
        ROUND(AVG(likes), 2)                        AS avg_likes,
        ROUND(AVG(comments), 2)                     AS avg_comments,
        ROUND(AVG(collections), 2)                  AS avg_collections,
        SUM(impressions)                             AS total_impressions,
        COUNT(*) FILTER (WHERE is_ad = TRUE)         AS ad_notes_count,
        COUNT(*) FILTER (WHERE is_ad = FALSE)        AS non_ad_notes_count
    FROM influencer_notes
    GROUP BY influencer_id
) ns ON ib.internal_id = ns.influencer_id;

COMMENT ON VIEW v_influencer_profile IS '达人完整画像视图 — JOIN 笔记统计数据，供资产库查询使用';


-- ============================================================
-- 初始化完成标记
-- ============================================================
DO $$
BEGIN
    RAISE NOTICE '✅ Σ.Match PostgreSQL Schema 初始化完成';
    RAISE NOTICE '   - influencer_basics    (达人基础信息)';
    RAISE NOTICE '   - users                (操盘手账户)';
    RAISE NOTICE '   - brand_spus           (品牌SPU资产)';
    RAISE NOTICE '   - collaborations       (历史合作映射)';
    RAISE NOTICE '   - campaign_history      (寻星任务历史)';
    RAISE NOTICE '   - export_dictionary     (导出映射字典)';
    RAISE NOTICE '   - influencer_notes      (达人笔记明细)';
    RAISE NOTICE '   - fulfillment_records   (履约记录)';
    RAISE NOTICE '   - v_influencer_profile  (达人画像视图)';
END $$;
