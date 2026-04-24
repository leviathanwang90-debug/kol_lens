/*
 * Design: Dark Constellation (暗夜星图)
 * Page: 智能检索工作台 /workspace
 * Layout: Left chat + Right data panels + Bottom dock
 */

import { Navbar } from "@/components/Navbar";
import { ASSETS, COLUMN_GROUPS, ROLES } from "@/lib/constants";
import {
  buildExportDownloadUrl,
  commitAssets,
  enrichCreatorData,
  exportCreators,
  getCreatorDataCatalog,
  getSpuMemory,
  getUserMemory,
  listExportTemplates,
  nextBatch,
  parseIntent,
  retrieveMatches,
  saveExportTemplate,
  type CreatorDataCatalogResult,
  type CreatorDataFieldDefinition,
  type CreatorDataRow,
  type DecayStrategyConfig,
  type ExportTemplateListResult,
  type ExportTemplateRecord,
  type FeedbackEvidenceExample,
  type NextBatchResult,
  type RocchioMeta,
  type WeightChangeExplanation,
} from "@/lib/api";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { motion, AnimatePresence } from "framer-motion";
import { useEffect, useMemo, useRef, useState } from "react";
import {
  ArrowRight,
  Ban,
  CheckCircle2,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  Clock,
  Eye,
  Radar,
  RefreshCw,
  Save,
  Send,
  Settings2,
  SlidersHorizontal,
  Sparkles,
  Star,
  Terminal,
  User,
  X,
  Zap,
} from "lucide-react";
import { toast } from "sonner";

interface ChatMessage {
  id: string;
  role: "user" | "system" | "assistant";
  content: string;
  component?: "loading" | "grid";
  timestamp: Date;
}

interface ContextState {
  brand: string;
  spu: string;
  role: number;
  operatorId: number;
}

interface IntentTagDraft {
  key: string;
  label: string;
  value: string;
  weight: number;
  source: "parsed" | "spu" | "user";
  kind: "tag" | "hard_filter";
  selected: boolean;
}

interface MetricDraft {
  key: string;
  label: string;
  value: string;
  source: "parsed" | "spu" | "user";
}

interface IntentDraft {
  hardFilters: Record<string, unknown>;
  dataRequirements: Record<string, unknown>;
  tagDrafts: IntentTagDraft[];
  metricDrafts: MetricDraft[];
}

interface Influencer {
  id: number;
  name: string;
  avatar: string;
  platform: string;
  followers: string;
  matchScore: number;
  roiProxy: number;
  tags: string[];
  status: "none" | "selected" | "pending" | "rejected";
  metrics: Record<string, string | number>;
  raw: Record<string, unknown>;
}

interface CreatorFieldGroup {
  group: string;
  fields: CreatorDataFieldDefinition[];
}

interface NotePreview {
  id: string;
  title: string;
  likes: number;
  cover: string;
  url: string;
  publishedAt: string;
}

const DEFAULT_AVATAR = "https://images.unsplash.com/photo-1494790108377-be9c29b29330?w=80&h=80&fit=crop";
const DEFAULT_DECAY_STRATEGY: DecayStrategyConfig = {
  role_time_decay_days: 21,
  role_time_decay_min_factor: 0.35,
  brand_stage_match_factor: 1,
  brand_stage_mismatch_factor: 0.72,
  campaign_freshness_decay_days: 14,
  campaign_freshness_min_factor: 0.6,
  role_decay_overrides: {
    采购: { decay_days: 18, min_factor: 0.4 },
    策划: { decay_days: 24, min_factor: 0.35 },
    客户: { decay_days: 32, min_factor: 0.45 },
  },
};

function normalizeNumber(value: unknown): number {
  if (typeof value === "number" && Number.isFinite(value)) return value;
  if (typeof value === "string") {
    const numeric = Number(String(value).replace(/[^\d.-]/g, ""));
    return Number.isFinite(numeric) ? numeric : 0;
  }
  return 0;
}

function formatFollowers(value: unknown): string {
  const numeric = normalizeNumber(value);
  if (!numeric) return "-";
  if (numeric >= 100000000) return `${(numeric / 100000000).toFixed(1)}亿`;
  if (numeric >= 10000) return `${(numeric / 10000).toFixed(1)}万`;
  return `${numeric}`;
}

function formatCreatorDisplayValue(value: unknown): string {
  if (value === null || value === undefined || value === "") return "-";
  if (Array.isArray(value)) return value.map((item) => formatCreatorDisplayValue(item)).join("、");
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

function groupCreatorFields(fields: CreatorDataFieldDefinition[]): CreatorFieldGroup[] {
  const mapping = fields.reduce<Record<string, CreatorDataFieldDefinition[]>>((acc, field) => {
    const group = field.group || "其他";
    if (!acc[group]) acc[group] = [];
    acc[group].push(field);
    return acc;
  }, {});
  return Object.entries(mapping).map(([group, groupFields]) => ({ group, fields: groupFields }));
}

function formatValue(value: unknown): string {
  if (value === null || value === undefined || value === "") return "-";
  if (typeof value === "number") {
    if (Math.abs(value) >= 10000) return formatFollowers(value);
    if (Number.isInteger(value)) return `${value}`;
    return value.toFixed(2);
  }
  if (Array.isArray(value)) return value.join("、");
  if (typeof value === "object") return JSON.stringify(value, null, 0);
  return String(value);
}

function prettifyKey(key: string): string {
  const alias: Record<string, string> = {
    region: "地区",
    gender: "性别",
    followers_min: "最小粉丝量",
    followers_max: "最大粉丝量",
    minFollowers: "最小粉丝量",
    maxFollowers: "最大粉丝量",
    minPrice: "最低报价",
    maxPrice: "最高报价",
    minCpm: "最低 CPM",
    maxCpm: "最高 CPM",
    requiredCount: "期望数量",
    contentCategory: "内容类目",
    styleSummary: "风格总结",
  };
  return alias[key] || key;
}

function extractFormattedTags(intent: Record<string, unknown>): IntentTagDraft[] {
  const queryPlan = (intent.query_plan as Record<string, unknown>) || {};
  const formattedTags = Array.isArray(queryPlan.formatted_tags)
    ? (queryPlan.formatted_tags as Array<Record<string, unknown>>)
    : [];
  const tags = formattedTags.length
    ? formattedTags
    : Array.isArray(queryPlan.tags)
      ? (queryPlan.tags as Array<Record<string, unknown>>)
      : [];
  return tags
    .map((item) => {
      const key = String(item.key || item.tag || "").trim();
      const label = String(item.tag || item.label || key).trim();
      if (!key && !label) return null;
      return {
        key: key || label,
        label: label || key,
        value: String(item.description || item.tag || item.label || key),
        weight: Math.min(Math.max(Number(item.default_weight || 1), 0), 2),
        source: "parsed" as const,
        kind: "tag" as const,
        selected: true,
      };
    })
    .filter(Boolean) as IntentTagDraft[];
}

function buildDraft(
  intent: Record<string, unknown>,
  spuMemory?: Record<string, unknown> | null,
  userMemory?: Record<string, unknown> | null,
): IntentDraft {
  const hardFilters = ((intent.hard_filters as Record<string, unknown>) || {});
  const dataRequirements = ((intent.data_requirements as Record<string, unknown>) || {});
  const tagDrafts: IntentTagDraft[] = [];

  tagDrafts.push(...extractFormattedTags(intent));

  Object.entries(hardFilters).forEach(([key, value]) => {
    if (value === undefined || value === null || value === "") return;
    tagDrafts.push({
      key,
      label: prettifyKey(key),
      value: formatValue(value),
      weight: 1,
      source: "parsed",
      kind: "hard_filter",
      selected: true,
    });
  });

  const appendMemoryTags = (memory: Record<string, unknown> | null | undefined, source: "spu" | "user") => {
    const preferredTags = Array.isArray(memory?.preferred_tags) ? (memory?.preferred_tags as Array<Record<string, unknown>>) : [];
    preferredTags.slice(0, 8).forEach((item) => {
      const key = String(item.key || "").trim();
      if (!key) return;
      if (tagDrafts.some((draft) => draft.key === key)) return;
      tagDrafts.push({
        key,
        label: key,
        value: key,
        weight: Math.min(Math.max(Number(item.weight || 1), 0), 2),
        source,
        kind: "tag",
        selected: source === "spu",
      });
    });
  };

  appendMemoryTags(spuMemory, "spu");
  appendMemoryTags(userMemory, "user");

  const metricDrafts = Object.entries(dataRequirements).map(([key, value]) => ({
    key,
    label: prettifyKey(key),
    value: typeof value === "string" ? value : JSON.stringify(value),
    source: "parsed" as const,
  }));

  return {
    hardFilters,
    dataRequirements,
    tagDrafts,
    metricDrafts,
  };
}

function parseMetricValue(value: string): unknown {
  const text = value.trim();
  if (!text) return "";
  try {
    return JSON.parse(text);
  } catch {
    const numeric = Number(text);
    if (!Number.isNaN(numeric) && text.match(/^[-+]?\d+(\.\d+)?$/)) {
      return numeric;
    }
    return text;
  }
}

function buildConfirmedIntent(baseIntent: Record<string, unknown>, draft: IntentDraft) {
  const nextHardFilters = { ...draft.hardFilters };
  draft.tagDrafts
    .filter((item) => item.kind === "hard_filter")
    .forEach((item) => {
      if (item.selected) {
        nextHardFilters[item.key] = item.value;
      }
    });

  const nextDataRequirements = draft.metricDrafts.reduce<Record<string, unknown>>((acc, item) => {
    acc[item.key] = parseMetricValue(item.value);
    return acc;
  }, {});

  const queryPlan = { ...((baseIntent.query_plan as Record<string, unknown>) || {}) };
  const formattedTags = draft.tagDrafts
    .filter((item) => item.kind === "tag" && item.selected)
    .map((item) => ({
      key: item.key,
      tag: item.label,
      default_weight: item.weight,
      source: item.source,
    }));
  queryPlan.formatted_tags = formattedTags;

  return {
    ...baseIntent,
    hard_filters: nextHardFilters,
    data_requirements: nextDataRequirements,
    query_plan: queryPlan,
  };
}

function extractTagWeights(draft: IntentDraft): Record<string, number> {
  return draft.tagDrafts
    .filter((item) => item.kind === "tag" && item.selected)
    .reduce<Record<string, number>>((acc, item) => {
      acc[item.key] = Number(item.weight.toFixed(2));
      return acc;
    }, {});
}

function applyWeightChangesToDraft(draft: IntentDraft, weightChanges?: WeightChangeExplanation | null): IntentDraft {
  if (!weightChanges?.after) return draft;
  const afterWeights = weightChanges.after;
  const knownKeys = new Set(draft.tagDrafts.map((item) => item.key));
  const nextTagDrafts = draft.tagDrafts.map((item) => ({
    ...item,
    weight: typeof afterWeights[item.key] === "number" ? Number(afterWeights[item.key]) : item.weight,
  }));
  Object.entries(afterWeights).forEach(([key, value]) => {
    if (knownKeys.has(key) || typeof value !== "number") return;
    nextTagDrafts.push({
      key,
      label: key.includes("::") ? key.split("::").slice(-1)[0] : key,
      value: key,
      weight: Number(value),
      source: "spu",
      kind: "tag",
      selected: true,
    });
  });
  return {
    ...draft,
    tagDrafts: nextTagDrafts,
  };
}

function splitEvidenceByBucket(items: FeedbackEvidenceExample[] = []) {
  return items.reduce(
    (acc, item) => {
      if (item.source_bucket === "history") {
        acc.history.push(item);
      } else {
        acc.current.push(item);
      }
      return acc;
    },
    { current: [] as FeedbackEvidenceExample[], history: [] as FeedbackEvidenceExample[] },
  );
}

function renderEvidenceLine(item: FeedbackEvidenceExample) {
  const tagText = Array.isArray(item.tags) && item.tags.length > 0 ? ` · ${item.tags.slice(0, 2).join(" / ")}` : "";
  const decayText = item.source_bucket === "history" && typeof item.time_decay_factor === "number"
    ? ` · 衰减 ${item.time_decay_factor.toFixed(2)}`
    : "";
  return `${item.display_name || `达人 ${item.internal_id}`}${tagText}${decayText}`;
}

function normalizeNotePreviews(value: unknown): NotePreview[] {
  if (!Array.isArray(value)) return [];
  return value
    .map((item, index) => {
      const row = (item || {}) as Record<string, unknown>;
      return {
        id: String(row.note_id || row.id || index),
        title: String(row.title || row.note_title || row.content_title || row.note_type || `笔记 ${index + 1}`),
        likes: normalizeNumber(row.likes),
        cover: String(row.cover_image_url || row.cover || row.image_url || ""),
        url: String(row.note_url || row.url || ""),
        publishedAt: String(row.published_at || row.created_at || ""),
      };
    })
    .filter((item) => item.title || item.cover || item.url || item.likes > 0);
}

function mapInfluencer(result: Record<string, unknown>): Influencer {
  const profile = (result.profile || {}) as Record<string, unknown>;
  const raw = (result.raw || {}) as Record<string, unknown>;
  const source = { ...profile, ...raw, ...result };
  const metrics: Record<string, string | number> = {
    粉丝数: formatFollowers(source.followers || source.follower_count),
    广告占比: formatValue(source.ad_ratio || source.ad_ratio_30d),
    图文预估CPM: formatValue(source.image_cpm || source.estimated_cpm_image || (source.pricing as Record<string, unknown> | undefined)?.estimate_picture_cpm),
    视频预估CPM: formatValue(source.video_cpm || source.estimated_cpm_video || (source.pricing as Record<string, unknown> | undefined)?.estimate_video_cpm),
    日常阅读中位数: formatValue(source.read_median_daily || source.median_read_daily),
    日常互动中位数: formatValue(source.engagement_median_daily || source.median_engagement_daily),
  };
  Object.entries(source).forEach(([key, value]) => {
    if (["internal_id", "id", "score", "distance", "nickname", "name", "platform", "avatar_url", "tags", "followers", "profile", "raw"].includes(key)) return;
    if (!(key in metrics) && (typeof value === "string" || typeof value === "number")) {
      metrics[prettifyKey(key)] = value;
    }
  });

  const tags = Array.isArray(source.tags)
    ? (source.tags as unknown[]).map((item) => String(item))
    : String(source.style_tags || source.content_tags || "")
        .split(/[,，、]/)
        .map((item) => item.trim())
        .filter(Boolean)
        .slice(0, 6);

  const internalId = normalizeNumber(source.internal_id || source.id);
  return {
    id: internalId,
    name: String(source.nickname || source.name || `达人${internalId || ""}`),
    avatar: String(source.avatar_url || source.avatar || DEFAULT_AVATAR),
    platform: String(source.platform || "小红书"),
    followers: formatFollowers(source.followers || source.follower_count),
    matchScore: Math.round(normalizeNumber(source.score) * 100),
    roiProxy: Number((normalizeNumber(source.roi_proxy || source.roi || source.score) || 0).toFixed(2)),
    tags,
    status: "none",
    metrics,
    raw: source,
  };
}

function ContextInitModal({
  open,
  onConfirm,
}: {
  open: boolean;
  onConfirm: (nextContext: ContextState) => void;
}) {
  const [brand, setBrand] = useState("");
  const [spu, setSpu] = useState("");
  const [role, setRole] = useState(2);
  const [operatorId, setOperatorId] = useState(1001);

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm">
      <motion.div
        initial={{ opacity: 0, scale: 0.95 }}
        animate={{ opacity: 1, scale: 1 }}
        className="glass-panel rounded-2xl p-8 w-full max-w-lg glow-red"
      >
        <div className="flex items-center gap-3 mb-6">
          <Radar className="w-6 h-6 text-primary" />
          <h2 className="font-display text-2xl tracking-wider">新建寻星任务</h2>
        </div>

        <div className="space-y-5">
          <div>
            <label className="text-sm text-muted-foreground font-chinese mb-2 block">
              品牌名称 <span className="text-primary">*</span>
            </label>
            <input
              value={brand}
              onChange={(e) => setBrand(e.target.value)}
              placeholder="输入品牌名称..."
              className="w-full px-4 py-2.5 rounded-lg bg-input border border-border text-foreground placeholder:text-muted-foreground/50 focus:border-primary focus:ring-1 focus:ring-primary/30 outline-none transition-all text-sm"
            />
          </div>

          <div>
            <label className="text-sm text-muted-foreground font-chinese mb-2 block">
              SPU 名称 <span className="text-primary">*</span>
            </label>
            <input
              value={spu}
              onChange={(e) => setSpu(e.target.value)}
              placeholder="输入产品 SPU 名称..."
              className="w-full px-4 py-2.5 rounded-lg bg-input border border-border text-foreground placeholder:text-muted-foreground/50 focus:border-primary focus:ring-1 focus:ring-primary/30 outline-none transition-all text-sm"
            />
          </div>

          <div>
            <label className="text-sm text-muted-foreground font-chinese mb-2 block">操作人 ID</label>
            <input
              value={operatorId}
              onChange={(e) => setOperatorId(Number(e.target.value) || 1001)}
              className="w-full px-4 py-2.5 rounded-lg bg-input border border-border text-foreground placeholder:text-muted-foreground/50 focus:border-primary focus:ring-1 focus:ring-primary/30 outline-none transition-all text-sm"
            />
          </div>

          <div>
            <label className="text-sm text-muted-foreground font-chinese mb-2 block">当前角色</label>
            <div className="flex gap-2">
              {ROLES.map((r) => (
                <button
                  key={r.id}
                  onClick={() => setRole(r.id)}
                  className={`flex-1 px-3 py-2 rounded-lg text-sm font-chinese transition-all border ${
                    role === r.id
                      ? "border-primary bg-primary/10 text-primary"
                      : "border-border bg-input text-muted-foreground hover:border-primary/30"
                  }`}
                >
                  {r.label}
                  <div className="text-xs opacity-60 mt-0.5">{r.weight}</div>
                </button>
              ))}
            </div>
          </div>
        </div>

        <Button
          onClick={() => {
            if (!brand.trim() || !spu.trim()) {
              toast.error("请填写品牌名称和 SPU 名称");
              return;
            }
            onConfirm({ brand, spu, role, operatorId });
          }}
          className="w-full mt-6 glow-red"
          size="lg"
        >
          <Zap className="w-4 h-4 mr-2" />
          进入工作台
        </Button>
      </motion.div>
    </div>
  );
}

function LoadingTerminal({ logs }: { logs: string[] }) {
  return (
    <div className="glass-panel rounded-xl p-4 mt-3 font-mono text-xs">
      <div className="flex items-center gap-2 mb-3 text-primary">
        <Terminal className="w-4 h-4" />
        <span>Elastic Loading Terminal</span>
      </div>
      <div className="space-y-1 text-muted-foreground">
        {logs.map((log, index) => (
          <div key={`${log}-${index}`}>› {log}</div>
        ))}
      </div>
    </div>
  );
}

function IntentReviewModal({
  open,
  brand,
  spu,
  draft,
  spuMemory,
  userMemory,
  weightChanges,
  onDraftChange,
  onClose,
  onConfirm,
}: {
  open: boolean;
  brand: string;
  spu: string;
  draft: IntentDraft | null;
  spuMemory: Record<string, unknown> | null;
  userMemory: Record<string, unknown> | null;
  weightChanges?: WeightChangeExplanation | null;
  onDraftChange: (draft: IntentDraft) => void;
  onClose: () => void;
  onConfirm: () => void;
}) {
  if (!open || !draft) return null;

  const updateTag = (index: number, patch: Partial<IntentTagDraft>) => {
    const nextDraft: IntentDraft = {
      ...draft,
      tagDrafts: draft.tagDrafts.map((item, itemIndex) => (itemIndex === index ? { ...item, ...patch } : item)),
    };
    onDraftChange(nextDraft);
  };

  const updateMetric = (index: number, value: string) => {
    const nextDraft: IntentDraft = {
      ...draft,
      metricDrafts: draft.metricDrafts.map((item, itemIndex) => (itemIndex === index ? { ...item, value } : item)),
    };
    onDraftChange(nextDraft);
  };

  const spuTags = draft.tagDrafts.filter((item) => item.source === "spu");
  const userTags = draft.tagDrafts.filter((item) => item.source === "user");
  const parsedTags = draft.tagDrafts.filter((item) => item.source === "parsed");

  return (
    <div className="fixed inset-0 z-50 bg-black/75 backdrop-blur-sm flex items-center justify-center p-6">
      <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} className="glass-panel rounded-2xl w-full max-w-6xl max-h-[88vh] overflow-hidden">
        <div className="px-6 py-5 border-b border-border/50 flex items-center justify-between">
          <div>
            <div className="text-xs uppercase tracking-[0.2em] text-primary font-display">Intent Review</div>
            <h2 className="text-2xl font-display mt-1">{brand} / {spu} 意图确认面板</h2>
            <p className="text-sm text-muted-foreground mt-1 font-chinese">
              系统已完成初次语义理解。你可以调整风格化标签权重、编辑数据指标区间，并决定是否启用 SPU 推荐特征与用户私有标签。
            </p>
          </div>
          <button onClick={onClose} className="p-2 rounded-lg hover:bg-muted transition-colors">
            <X className="w-5 h-5" />
          </button>
        </div>

        <ScrollArea className="h-[calc(88vh-148px)]">
          <div className="grid lg:grid-cols-[1.3fr_0.9fr] gap-6 p-6">
            <div className="space-y-6">
              {weightChanges?.deltas && weightChanges.deltas.length > 0 && (
                <section className="glass-panel rounded-xl p-5 border border-primary/20 bg-primary/5">
                  <div className="flex items-center gap-2 mb-2">
                    <Zap className="w-4 h-4 text-primary" />
                    <span className="font-chinese font-semibold">最近一次 Fission 的权重变化</span>
                  </div>
                  <p className="text-xs text-muted-foreground font-chinese mb-3">{weightChanges.summary || "系统已根据 selected / rejected 反馈自动调整部分标签权重。"}</p>
                  <div className="grid md:grid-cols-2 gap-3">
                    {weightChanges.deltas.slice(0, 6).map((item) => {
                      const evidence = splitEvidenceByBucket(item.direction === "up" ? (item.positive_examples || []) : (item.negative_examples || []));
                      return (
                        <div key={`delta-${item.key}`} className={`px-3 py-3 rounded-lg border text-xs ${item.direction === "up" ? "border-primary/30 bg-primary/10 text-primary" : "border-amber-400/30 bg-amber-400/10 text-amber-200"}`}>
                          <div className="flex items-center justify-between gap-3">
                            <div className="font-chinese">{item.display_name}</div>
                            <div className="font-data">{item.before.toFixed(1)} → {item.after.toFixed(1)}</div>
                          </div>
                          <div className="mt-2 text-[11px] text-muted-foreground font-chinese">{item.reason}</div>
                          <div className="mt-2 space-y-1 text-[11px]">
                            <div>本轮反馈：{evidence.current.length > 0 ? renderEvidenceLine(evidence.current[0]) : "无"}</div>
                            <div>历史反馈：{evidence.history.length > 0 ? renderEvidenceLine(evidence.history[0]) : "无"}</div>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                </section>
              )}
              <section className="glass-panel rounded-xl p-5">
                <div className="flex items-center gap-2 mb-4">
                  <SlidersHorizontal className="w-4 h-4 text-primary" />
                  <span className="font-chinese font-semibold">视觉/标签项</span>
                  <span className="text-xs text-muted-foreground ml-auto">权重范围 0 - 2，默认 1</span>
                </div>
                <div className="space-y-3">
                  {parsedTags.map((item, index) => {
                    const actualIndex = draft.tagDrafts.findIndex((draftItem) => draftItem.key === item.key && draftItem.source === item.source);
                    return (
                      <div key={`${item.source}-${item.key}`} className="rounded-xl border border-border/50 p-3">
                        <div className="flex items-center gap-3">
                          <input type="checkbox" checked={item.selected} onChange={(e) => updateTag(actualIndex, { selected: e.target.checked })} />
                          <span className="px-2 py-1 rounded-md text-xs bg-primary/15 text-primary border border-primary/20">{item.label}</span>
                          <span className="text-sm text-foreground font-chinese">{item.value}</span>
                          <span className="text-[10px] px-1.5 py-0.5 rounded bg-muted text-muted-foreground ml-auto">解析标签</span>
                        </div>
                        <div className="mt-3 flex items-center gap-3">
                          <input
                            type="range"
                            min={0}
                            max={2}
                            step={0.1}
                            value={item.weight}
                            onChange={(e) => updateTag(actualIndex, { weight: Number(e.target.value) })}
                            className="flex-1 h-1 accent-[#D4001A] bg-border rounded-full appearance-none cursor-pointer"
                          />
                          <span className="w-10 text-right font-data text-primary">{item.weight.toFixed(1)}</span>
                        </div>
                      </div>
                    );
                  })}
                </div>
              </section>

              <section className="glass-panel rounded-xl p-5">
                <div className="flex items-center gap-2 mb-4">
                  <CheckCircle2 className="w-4 h-4 text-primary" />
                  <span className="font-chinese font-semibold">数据指标要求</span>
                </div>
                <div className="space-y-3">
                  {draft.metricDrafts.length === 0 && <div className="text-sm text-muted-foreground font-chinese">当前未解析出显式数据指标，可直接继续检索。</div>}
                  {draft.metricDrafts.map((item, index) => (
                    <div key={item.key} className="grid grid-cols-[180px_1fr] gap-3 items-center rounded-xl border border-border/50 p-3">
                      <div>
                        <div className="text-sm font-chinese text-foreground">{item.label}</div>
                        <div className="text-[11px] text-muted-foreground">{item.key}</div>
                      </div>
                      <input
                        value={item.value}
                        onChange={(e) => updateMetric(index, e.target.value)}
                        className="w-full px-3 py-2 rounded-lg bg-input border border-border text-sm text-foreground outline-none focus:border-primary"
                      />
                    </div>
                  ))}
                </div>
              </section>
            </div>

            <div className="space-y-6">
              <section className="glass-panel rounded-xl p-5">
                <div className="text-sm font-semibold font-chinese mb-3">SPU 推荐特征</div>
                <p className="text-xs text-muted-foreground font-chinese mb-3">
                  基于当前 SPU 历史入库反馈沉淀出的高频命中特征，可决定是否带入下一轮检索。
                </p>
                <div className="space-y-3">
                  {spuTags.length === 0 && <div className="text-sm text-muted-foreground">暂无 SPU 推荐特征。</div>}
                  {spuTags.map((item) => {
                    const actualIndex = draft.tagDrafts.findIndex((draftItem) => draftItem.key === item.key && draftItem.source === item.source);
                    return (
                      <div key={`spu-${item.key}`} className="rounded-xl border border-primary/20 bg-primary/5 p-3">
                        <div className="flex items-center gap-2">
                          <input type="checkbox" checked={item.selected} onChange={(e) => updateTag(actualIndex, { selected: e.target.checked })} />
                          <span className="px-2 py-1 rounded-md text-xs bg-primary/15 text-primary border border-primary/20">SPU</span>
                          <span className="text-sm font-chinese">{item.label}</span>
                          <span className="ml-auto font-data text-primary">{item.weight.toFixed(1)}</span>
                        </div>
                        <input
                          type="range"
                          min={0}
                          max={2}
                          step={0.1}
                          value={item.weight}
                          onChange={(e) => updateTag(actualIndex, { weight: Number(e.target.value) })}
                          className="mt-3 w-full h-1 accent-[#D4001A] bg-border rounded-full appearance-none cursor-pointer"
                        />
                      </div>
                    );
                  })}
                </div>
              </section>

              <section className="glass-panel rounded-xl p-5">
                <div className="text-sm font-semibold font-chinese mb-3">用户私有标签</div>
                <p className="text-xs text-muted-foreground font-chinese mb-3">
                  基于当前操作人过往 selected / rejected 历史自动生成。建议作为偏好补充，而非强约束。
                </p>
                <div className="space-y-3">
                  {userTags.length === 0 && <div className="text-sm text-muted-foreground">暂无用户私有标签。</div>}
                  {userTags.map((item) => {
                    const actualIndex = draft.tagDrafts.findIndex((draftItem) => draftItem.key === item.key && draftItem.source === item.source);
                    return (
                      <div key={`user-${item.key}`} className="rounded-xl border border-border/50 bg-card/60 p-3">
                        <div className="flex items-center gap-2">
                          <input type="checkbox" checked={item.selected} onChange={(e) => updateTag(actualIndex, { selected: e.target.checked })} />
                          <span className="px-2 py-1 rounded-md text-xs bg-muted text-muted-foreground border border-border">用户</span>
                          <span className="text-sm font-chinese">{item.label}</span>
                          <span className="ml-auto font-data text-primary">{item.weight.toFixed(1)}</span>
                        </div>
                        <input
                          type="range"
                          min={0}
                          max={2}
                          step={0.1}
                          value={item.weight}
                          onChange={(e) => updateTag(actualIndex, { weight: Number(e.target.value) })}
                          className="mt-3 w-full h-1 accent-[#D4001A] bg-border rounded-full appearance-none cursor-pointer"
                        />
                      </div>
                    );
                  })}
                </div>
              </section>

              <section className="glass-panel rounded-xl p-5">
                <div className="text-sm font-semibold font-chinese mb-3">记忆摘要</div>
                <div className="grid grid-cols-2 gap-3 text-sm">
                  <div className="rounded-xl border border-border/50 p-3">
                    <div className="text-muted-foreground">SPU 历史任务</div>
                    <div className="font-data text-primary text-xl mt-1">{Number(spuMemory?.campaign_count || 0)}</div>
                  </div>
                  <div className="rounded-xl border border-border/50 p-3">
                    <div className="text-muted-foreground">用户历史任务</div>
                    <div className="font-data text-primary text-xl mt-1">{Number(userMemory?.campaign_count || 0)}</div>
                  </div>
                </div>
              </section>
            </div>
          </div>
        </ScrollArea>

        <div className="px-6 py-4 border-t border-border/50 flex items-center justify-between gap-3">
          <div className="text-xs text-muted-foreground font-chinese">
            确认后将基于当前意图面板执行真实检索，后续“获取更多”会改走下一批推荐接口。
          </div>
          <div className="flex items-center gap-3">
            <Button variant="outline" onClick={onClose}>稍后再说</Button>
            <Button onClick={onConfirm} className="glow-red">
              <ArrowRight className="w-4 h-4 mr-2" />
              确认并开始检索
            </Button>
          </div>
        </div>
      </motion.div>
    </div>
  );
}

function DataGridList({
  influencers,
  onRowClick,
  activeGroup,
}: {
  influencers: Influencer[];
  onRowClick: (influencer: Influencer) => void;
  activeGroup: string;
}) {
  const columns = (((COLUMN_GROUPS as Record<string, { columns?: readonly string[] }>)[activeGroup] || {}).columns || []).slice(0, 6);
  return (
    <div className="overflow-x-auto rounded-xl border border-border/50 bg-card/40">
      <table className="min-w-full text-sm">
        <thead className="bg-card/80 text-xs uppercase tracking-wide text-muted-foreground">
          <tr>
            <th className="text-left px-4 py-3 sticky left-0 bg-card/95">博主信息</th>
            <th className="text-right px-4 py-3">匹配度</th>
            <th className="text-right px-4 py-3">性价比</th>
            {columns.map((column) => (
              <th key={column} className="text-left px-4 py-3 whitespace-nowrap">{column}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {influencers.map((influencer) => (
            <tr key={influencer.id} onClick={() => onRowClick(influencer)} className="border-t border-border/40 hover:bg-primary/5 cursor-pointer transition-colors">
              <td className="px-4 py-3 sticky left-0 bg-card/95">
                <div className="flex items-center gap-3">
                  <img src={influencer.avatar} alt={influencer.name} className="w-12 h-12 rounded-full object-cover border border-primary/20" />
                  <div>
                    <div className="font-semibold font-chinese flex items-center gap-2">
                      {influencer.name}
                      {influencer.status === "selected" && <Star className="w-3.5 h-3.5 text-primary" />}
                      {influencer.status === "pending" && <Clock className="w-3.5 h-3.5 text-brand-gold" />}
                      {influencer.status === "rejected" && <Ban className="w-3.5 h-3.5 text-muted-foreground" />}
                    </div>
                    <div className="text-xs text-muted-foreground mt-1">{influencer.platform} · {influencer.followers} 粉丝</div>
                    <div className="mt-2 flex flex-wrap gap-1">
                      {influencer.tags.slice(0, 4).map((tag) => (
                        <span key={tag} className="px-2 py-0.5 rounded text-[11px] bg-primary/10 text-primary border border-primary/20">{tag}</span>
                      ))}
                    </div>
                  </div>
                </div>
              </td>
              <td className="px-4 py-3 text-right font-data text-primary">{influencer.matchScore}</td>
              <td className="px-4 py-3 text-right font-data text-brand-gold">{influencer.roiProxy}</td>
              {columns.map((column) => (
                <td key={`${influencer.id}-${column}`} className="px-4 py-3 whitespace-nowrap">{influencer.metrics[column] ?? "-"}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function ReviewModal({
  influencer,
  onAction,
  onClose,
  onNext,
  onPrev,
  hasNext,
  hasPrev,
}: {
  influencer: Influencer;
  onAction: (id: number, status: "selected" | "pending" | "rejected") => void;
  onClose: () => void;
  onNext: () => void;
  onPrev: () => void;
  hasNext: boolean;
  hasPrev: boolean;
}) {
  const notes = normalizeNotePreviews(influencer.raw.note_previews || influencer.raw.notes);

  return (
    <motion.div className="fixed inset-0 z-50 bg-black/75 backdrop-blur-md flex items-center justify-center p-6" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}>
      <motion.div initial={{ y: 24, opacity: 0 }} animate={{ y: 0, opacity: 1 }} exit={{ y: 24, opacity: 0 }} className="glass-panel rounded-2xl w-full max-w-6xl h-[88vh] flex flex-col overflow-hidden">
        <div className="px-6 py-5 border-b border-border/50 flex items-center justify-between">
          <div className="flex items-center gap-4">
            <img src={influencer.avatar} alt={influencer.name} className="w-16 h-16 rounded-full object-cover border border-primary/20" />
            <div>
              <div className="text-2xl font-display tracking-wide">{influencer.name}</div>
              <div className="text-sm text-muted-foreground font-chinese mt-1">{influencer.platform} · {influencer.followers} 粉丝</div>
              <div className="mt-2 flex flex-wrap gap-1">
                {influencer.tags.map((tag) => (
                  <span key={tag} className="px-2 py-0.5 rounded text-xs bg-primary/10 text-primary border border-primary/20">{tag}</span>
                ))}
              </div>
            </div>
          </div>
          <div className="flex items-center gap-4">
            <div className="text-right">
              <div className="text-xs text-muted-foreground font-chinese">匹配度</div>
              <div className="font-data text-2xl font-bold text-primary">{influencer.matchScore}</div>
            </div>
            <div className="text-right">
              <div className="text-xs text-muted-foreground font-chinese">性价比</div>
              <div className="font-data text-2xl font-bold text-brand-gold">{influencer.roiProxy}</div>
            </div>
            <button onClick={onClose} className="p-2 rounded-lg hover:bg-muted transition-colors"><X className="w-5 h-5" /></button>
          </div>
        </div>

        <div className="flex-1 flex overflow-hidden">
          <div className="w-80 border-r border-border/50 p-5 overflow-y-auto">
            <h4 className="text-xs text-muted-foreground font-chinese mb-4 uppercase tracking-wider">核心指标</h4>
            <div className="space-y-3">
              {Object.entries(influencer.metrics).map(([key, val]) => (
                <div key={key} className="flex justify-between items-center gap-4">
                  <span className="text-xs text-muted-foreground font-chinese">{key}</span>
                  <span className="font-data text-xs text-foreground text-right">{String(val)}</span>
                </div>
              ))}
            </div>
          </div>

          <div className="flex-1 p-5 overflow-y-auto">
            <h4 className="text-xs text-muted-foreground font-chinese mb-4 uppercase tracking-wider">近期笔记</h4>
            {notes.length === 0 ? (
              <div className="rounded-xl border border-dashed border-border/50 p-6 text-sm text-muted-foreground font-chinese">
                后端暂未返回该达人的笔记预览。
              </div>
            ) : (
              <div className="columns-2 md:columns-3 gap-4 space-y-4">
                {notes.map((note) => (
                <a
                  key={note.id}
                  href={note.url || undefined}
                  target={note.url ? "_blank" : undefined}
                  rel={note.url ? "noreferrer" : undefined}
                  className="block break-inside-avoid rounded-xl overflow-hidden border border-border/30 hover:border-primary/30 transition-all group bg-card/50"
                >
                  <div className="aspect-[3/4] bg-muted flex items-center justify-center overflow-hidden">
                    {note.cover ? (
                      <img src={note.cover} alt={note.title} className="w-full h-full object-cover" />
                    ) : (
                      <Eye className="w-8 h-8 text-muted-foreground/30" />
                    )}
                  </div>
                  <div className="p-3">
                    <p className="text-xs text-foreground font-chinese truncate">{note.title}</p>
                    <p className="text-[10px] text-muted-foreground mt-1">
                      {note.likes > 0 ? `♥ ${note.likes.toLocaleString()}` : note.publishedAt || "-"}
                    </p>
                  </div>
                </a>
                ))}
              </div>
            )}
          </div>
        </div>

        <div className="border-t border-border/50 px-6 py-4 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <button onClick={onPrev} disabled={!hasPrev} className="p-2 rounded-lg border border-border hover:border-primary/30 disabled:opacity-30 transition-all"><ChevronLeft className="w-4 h-4" /></button>
            <button onClick={onNext} disabled={!hasNext} className="p-2 rounded-lg border border-border hover:border-primary/30 disabled:opacity-30 transition-all"><ChevronRight className="w-4 h-4" /></button>
          </div>
          <div className="flex items-center gap-3">
            <Button variant="outline" onClick={() => onAction(influencer.id, "rejected")} className="border-border hover:border-muted-foreground/50 text-muted-foreground"><Ban className="w-4 h-4 mr-2" />未选中</Button>
            <Button variant="outline" onClick={() => onAction(influencer.id, "pending")} className="border-brand-gold/30 hover:border-brand-gold/60 text-brand-gold"><Clock className="w-4 h-4 mr-2" />待定</Button>
            <Button onClick={() => onAction(influencer.id, "selected")} className="glow-red"><Star className="w-4 h-4 mr-2" />选中</Button>
          </div>
        </div>
      </motion.div>
    </motion.div>
  );
}

function FissionInsightBanner({
  weightChanges,
  rocchio,
}: {
  weightChanges: WeightChangeExplanation | null;
  rocchio: RocchioMeta | null;
}) {
  if (!weightChanges && !rocchio) return null;
  const promoted = (weightChanges?.promoted || []).slice(0, 4);
  const demoted = (weightChanges?.demoted || []).slice(0, 4);
  const currentPositive = Number(rocchio?.breakdown?.current_positive?.count || 0);
  const historyPositive = Number(rocchio?.breakdown?.history_positive?.count || 0);
  const currentNegative = Number(rocchio?.breakdown?.current_negative?.count || 0);
  const historyNegative = Number(rocchio?.breakdown?.history_negative?.count || 0);
  const focusDelta = promoted[0] || demoted[0] || null;
  const focusEvidence = focusDelta
    ? splitEvidenceByBucket(focusDelta.direction === "up" ? (focusDelta.positive_examples || []) : (focusDelta.negative_examples || []))
    : { current: [], history: [] };

  return (
    <div className="max-w-5xl mx-auto mb-4 grid lg:grid-cols-[1.15fr_0.85fr] gap-4">
      <div className="glass-panel rounded-xl p-4 border border-primary/20 bg-primary/5">
        <div className="flex items-center gap-2 mb-2">
          <Zap className="w-4 h-4 text-primary" />
          <div className="text-xs uppercase tracking-wide text-primary font-display">Fission 权重回显</div>
        </div>
        <p className="text-sm font-chinese text-foreground">{weightChanges?.summary || "本轮未出现明显的 tag 权重变化。"}</p>
        <div className="mt-3 grid md:grid-cols-2 gap-3">
          <div className="rounded-xl border border-primary/20 bg-card/50 p-3">
            <div className="text-xs text-primary font-chinese mb-2">升权标签</div>
            <div className="space-y-2">
              {promoted.length === 0 ? <div className="text-xs text-muted-foreground font-chinese">本轮没有明显升权项。</div> : promoted.map((item) => (
                <div key={`up-${item.key}`} className="rounded-lg border border-primary/15 bg-primary/5 p-2 text-xs">
                  <div className="flex items-center justify-between gap-3">
                    <span className="font-chinese text-foreground">{item.display_name}</span>
                    <span className="font-data text-primary">{item.before.toFixed(1)} → {item.after.toFixed(1)}</span>
                  </div>
                  <div className="text-[11px] text-muted-foreground mt-1">{item.reason}</div>
                </div>
              ))}
            </div>
          </div>
          <div className="rounded-xl border border-amber-400/20 bg-amber-400/5 p-3">
            <div className="text-xs text-amber-200 font-chinese mb-2">降权标签</div>
            <div className="space-y-2">
              {demoted.length === 0 ? <div className="text-xs text-muted-foreground font-chinese">本轮没有明显降权项。</div> : demoted.map((item) => (
                <div key={`down-${item.key}`} className="rounded-lg border border-amber-400/15 bg-amber-400/5 p-2 text-xs">
                  <div className="flex items-center justify-between gap-3">
                    <span className="font-chinese text-foreground">{item.display_name}</span>
                    <span className="font-data text-amber-200">{item.before.toFixed(1)} → {item.after.toFixed(1)}</span>
                  </div>
                  <div className="text-[11px] text-muted-foreground mt-1">{item.reason}</div>
                </div>
              ))}
            </div>
          </div>
        </div>
        {focusDelta && (
          <div className="mt-3 rounded-xl border border-border/50 bg-card/40 p-3">
            <div className="text-xs uppercase tracking-wide text-primary font-display">触发证据</div>
            <div className="mt-1 text-sm font-chinese text-foreground">{focusDelta.display_name} 的变化由哪些达人反馈驱动</div>
            <div className="mt-3 grid md:grid-cols-2 gap-3 text-xs">
              <div className="rounded-lg border border-primary/15 bg-primary/5 p-3">
                <div className="text-primary font-chinese mb-2">本轮反馈驱动</div>
                <div className="space-y-1 text-muted-foreground">
                  {focusEvidence.current.length === 0 ? <div>暂无本轮证据。</div> : focusEvidence.current.slice(0, 3).map((item) => <div key={`current-${focusDelta.key}-${item.internal_id}`}>{renderEvidenceLine(item)}</div>)}
                </div>
              </div>
              <div className="rounded-lg border border-border/50 p-3">
                <div className="text-foreground font-chinese mb-2">历史反馈驱动</div>
                <div className="space-y-1 text-muted-foreground">
                  {focusEvidence.history.length === 0 ? <div>暂无历史证据。</div> : focusEvidence.history.slice(0, 3).map((item) => <div key={`history-${focusDelta.key}-${item.internal_id}`}>{renderEvidenceLine(item)}</div>)}
                </div>
              </div>
            </div>
          </div>
        )}
      </div>
      <div className="glass-panel rounded-xl p-4">
        <div className="flex items-center gap-2 mb-2">
          <Radar className="w-4 h-4 text-primary" />
          <div className="text-xs uppercase tracking-wide text-primary font-display">Rocchio 反馈进化</div>
        </div>
        <p className="text-xs text-muted-foreground font-chinese">{rocchio?.message || "当前沿用基础查询向量。"}</p>
        <div className="mt-2 text-[11px] text-muted-foreground font-chinese">
          系统会区分本轮 feedback 与历史 feedback，并对较早历史引入时间衰减，避免旧决策长期主导推荐方向。
        </div>
        <div className="grid grid-cols-2 gap-3 mt-3 text-sm">
          <div className="rounded-xl border border-border/50 p-3">
            <div className="text-muted-foreground text-xs font-chinese">本轮正反馈</div>
            <div className="font-data text-primary text-lg mt-1">{currentPositive}</div>
          </div>
          <div className="rounded-xl border border-border/50 p-3">
            <div className="text-muted-foreground text-xs font-chinese">历史正反馈</div>
            <div className="font-data text-primary text-lg mt-1">{historyPositive}</div>
          </div>
          <div className="rounded-xl border border-border/50 p-3">
            <div className="text-muted-foreground text-xs font-chinese">本轮负反馈</div>
            <div className="font-data text-amber-200 text-lg mt-1">{currentNegative}</div>
          </div>
          <div className="rounded-xl border border-border/50 p-3">
            <div className="text-muted-foreground text-xs font-chinese">历史负反馈</div>
            <div className="font-data text-amber-200 text-lg mt-1">{historyNegative}</div>
          </div>
        </div>
      </div>
    </div>
  );
}

function FissionDock({
  selected,
  spuTags,
  onFission,
  onCommit,
  busy,
}: {
  selected: Influencer[];
  spuTags: string[];
  onFission: () => void;
  onCommit: () => void;
  busy: boolean;
}) {
  if (selected.length === 0) return null;

  return (
    <motion.div initial={{ y: 100, opacity: 0 }} animate={{ y: 0, opacity: 1 }} exit={{ y: 100, opacity: 0 }} className="fixed bottom-0 left-0 right-0 z-40 border-t border-primary/20" style={{ background: "oklch(0.1 0.008 25 / 95%)", backdropFilter: "blur(20px)" }}>
      <div className="container py-4 flex items-center gap-4">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 text-xs text-muted-foreground font-chinese mb-2">
            <span>已选 {selected.length} 人</span>
            <span>·</span>
            <span>当前会话已激活 SPU 推荐特征</span>
          </div>
          <div className="flex items-center gap-2 overflow-x-auto">
            {selected.map((inf) => (
              <img key={inf.id} src={inf.avatar} alt={inf.name} className="w-8 h-8 rounded-full border-2 border-primary/30 shrink-0" title={inf.name} />
            ))}
            {spuTags.slice(0, 4).map((tag) => (
              <span key={tag} className="px-2 py-1 rounded-md text-[11px] bg-primary/10 text-primary border border-primary/20 shrink-0">{tag}</span>
            ))}
          </div>
        </div>
        <div className="flex items-center gap-3 shrink-0">
          <Button variant="outline" onClick={onFission} disabled={busy} className="border-primary/30 text-primary hover:bg-primary/10">
            <RefreshCw className={`w-4 h-4 mr-2 ${busy ? "animate-spin" : ""}`} />获取更多
          </Button>
          <Button onClick={onCommit} disabled={busy} className="glow-red">
            <Save className="w-4 h-4 mr-2" />确认入库
          </Button>
        </div>
      </div>
    </motion.div>
  );
}

export default function Workspace() {
  const [showInit, setShowInit] = useState(true);
  const [context, setContext] = useState<ContextState>({ brand: "", spu: "", role: 2, operatorId: 1001 });
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [influencers, setInfluencers] = useState<Influencer[]>([]);
  const [reviewIndex, setReviewIndex] = useState<number | null>(null);
  const [activeGroup, setActiveGroup] = useState("basic");
  const [expectedCount, setExpectedCount] = useState(10);
  const [showSettings, setShowSettings] = useState(false);
  const [decayStrategy, setDecayStrategy] = useState<DecayStrategyConfig>(DEFAULT_DECAY_STRATEGY);
  const [loadingLogs, setLoadingLogs] = useState<string[]>([]);
  const [loading, setLoading] = useState(false);
  const [showIntentModal, setShowIntentModal] = useState(false);
  const [parsedIntent, setParsedIntent] = useState<Record<string, unknown> | null>(null);
  const [intentDraft, setIntentDraft] = useState<IntentDraft | null>(null);
  const [spuMemory, setSpuMemory] = useState<Record<string, unknown> | null>(null);
  const [userMemory, setUserMemory] = useState<Record<string, unknown> | null>(null);
  const [latestResult, setLatestResult] = useState<Record<string, unknown> | null>(null);
  const [lastWeightChanges, setLastWeightChanges] = useState<WeightChangeExplanation | null>(null);
  const [lastRocchioMeta, setLastRocchioMeta] = useState<RocchioMeta | null>(null);
  const [creatorFieldCatalog, setCreatorFieldCatalog] = useState<CreatorDataFieldDefinition[]>([]);
  const [selectedCreatorFields, setSelectedCreatorFields] = useState<string[]>([]);
  const [creatorDataRows, setCreatorDataRows] = useState<CreatorDataRow[]>([]);
  const [exportTemplates, setExportTemplates] = useState<ExportTemplateRecord[]>([]);
  const [selectedTemplateId, setSelectedTemplateId] = useState("");
  const [templateName, setTemplateName] = useState("");
  const [creatorDataLoading, setCreatorDataLoading] = useState(false);
  const [busyAction, setBusyAction] = useState(false);
  const chatEndRef = useRef<HTMLDivElement>(null);

  const selectedInfluencers = useMemo(() => influencers.filter((item) => item.status === "selected"), [influencers]);
  const rejectedInfluencers = useMemo(() => influencers.filter((item) => item.status === "rejected"), [influencers]);
  const pendingInfluencers = useMemo(() => influencers.filter((item) => item.status === "pending"), [influencers]);

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, loading]);

  const currentTagWeights = useMemo(() => (intentDraft ? extractTagWeights(intentDraft) : {}), [intentDraft]);
  const spuMemoryTags = useMemo(() => {
    const preferredTags = Array.isArray(spuMemory?.preferred_tags) ? (spuMemory?.preferred_tags as Array<Record<string, unknown>>) : [];
    return preferredTags.slice(0, 4).map((item) => String(item.key || "")).filter(Boolean);
  }, [spuMemory]);
  const creatorFieldGroups = useMemo(() => groupCreatorFields(creatorFieldCatalog), [creatorFieldCatalog]);
  const selectedCreatorPayload = useMemo(
    () =>
      selectedInfluencers.map((item) => ({
        creator_id: item.id,
        creator_uid: String(item.raw.creator_uid || item.raw.uid || item.raw.redbook_id || item.id),
        nickname: item.name,
        redbook_id: String(item.raw.redbook_id || item.raw.xiaohongshu_id || ""),
        region: String(item.raw.region || item.raw.location || ""),
        followers: normalizeNumber(item.raw.followers || item.raw.follower_count || item.metrics.粉丝数),
        tags: item.tags,
        raw: item.raw,
      })),
    [selectedInfluencers],
  );

  useEffect(() => {
    if (showInit) return;
    void (async () => {
      try {
        const [catalogRes, templateRes] = await Promise.all([
          getCreatorDataCatalog().catch(() => ({ success: true, result: {} })),
          listExportTemplates({ operator_id: context.operatorId, brand_name: context.brand, spu_name: context.spu }).catch(() => ({ success: true, result: {} })),
        ]);
        const catalogResult = (catalogRes.result || {}) as CreatorDataCatalogResult;
        const templateResult = (templateRes.result || {}) as ExportTemplateListResult;
        const catalogFields = (catalogResult.fields || []) as CreatorDataFieldDefinition[];
        const defaultFieldKeys = (catalogResult.default_field_keys || []) as string[];
        const templates = (templateResult.templates || []) as ExportTemplateRecord[];
        setCreatorFieldCatalog(catalogFields);
        setSelectedCreatorFields((prev) => (prev.length > 0 ? prev : defaultFieldKeys));
        setExportTemplates(templates);
      } catch (error) {
        console.warn(error);
      }
    })();
  }, [context.brand, context.operatorId, context.spu, showInit]);

  const handleContextConfirm = (nextContext: ContextState) => {
    setContext(nextContext);
    setLastWeightChanges(null);
    setLastRocchioMeta(null);
    setShowInit(false);
    setMessages([
      {
        id: `sys_${Date.now()}`,
        role: "system",
        content: `寻星任务已创建。品牌：${nextContext.brand}，SPU：${nextContext.spu}，角色：${ROLES.find((r) => r.id === nextContext.role)?.label}，操作人 ID：${nextContext.operatorId}。请描述您的达人需求。`,
        timestamp: new Date(),
      },
    ]);
  };

  const pushAssistantGridMessage = (text: string) => {
    setMessages((prev) => [
      ...prev,
      {
        id: `grid_${Date.now()}`,
        role: "assistant",
        content: text,
        component: "grid",
        timestamp: new Date(),
      },
    ]);
  };

  const handleApplyTemplate = (templateId: string) => {
    setSelectedTemplateId(templateId);
    const template = exportTemplates.find((item) => item.template_id === templateId);
    if (!template) return;
    setSelectedCreatorFields(template.field_keys || []);
    setTemplateName(template.template_name || "");
    toast.success(`已应用模板：${template.template_name}`);
  };

  const handleEnrichCreatorData = async () => {
    if (selectedCreatorPayload.length === 0) {
      toast.error("请先选中至少一位达人后再补充数据。");
      return;
    }
    const fieldKeys = selectedCreatorFields.length > 0 ? selectedCreatorFields : creatorFieldCatalog.filter((item) => item.default).map((item) => item.key);
    if (fieldKeys.length === 0) {
      toast.error("请至少勾选一个字段后再补充数据。");
      return;
    }
    setCreatorDataLoading(true);
    try {
      const response = await enrichCreatorData({
        brand_name: context.brand,
        spu_name: context.spu,
        creators: selectedCreatorPayload,
        field_keys: fieldKeys,
        template_id: selectedTemplateId,
      });
      const result = response.result || {};
      setCreatorDataRows((result.rows || []) as CreatorDataRow[]);
      if (Array.isArray(result.field_keys) && result.field_keys.length > 0) {
        setSelectedCreatorFields(result.field_keys as string[]);
      }
      toast.success(`已补充 ${Number((result.rows || []).length)} 位达人数据。`);
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "补充达人数据失败");
    } finally {
      setCreatorDataLoading(false);
    }
  };

  const handleSaveTemplate = async () => {
    const fieldKeys = selectedCreatorFields.length > 0 ? selectedCreatorFields : creatorFieldCatalog.filter((item) => item.default).map((item) => item.key);
    if (!templateName.trim()) {
      toast.error("请先输入模板名称。");
      return;
    }
    if (fieldKeys.length === 0) {
      toast.error("请至少选择一个导出字段后再保存模板。");
      return;
    }
    try {
      const response = await saveExportTemplate({
        template_id: selectedTemplateId,
        template_name: templateName.trim(),
        brand_name: context.brand,
        spu_name: context.spu,
        operator_id: context.operatorId,
        field_keys: fieldKeys,
      });
      const template = response.result?.template as ExportTemplateRecord | undefined;
      if (!template) {
        toast.error("模板保存失败。");
        return;
      }
      const templateResponse = await listExportTemplates({ operator_id: context.operatorId, brand_name: context.brand, spu_name: context.spu });
      setExportTemplates((templateResponse.result?.templates || []) as ExportTemplateRecord[]);
      setSelectedTemplateId(template.template_id);
      setTemplateName(template.template_name);
      toast.success(`已保存模板：${template.template_name}`);
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "保存模板失败");
    }
  };

  const handleExportCreatorData = async () => {
    if (selectedCreatorPayload.length === 0) {
      toast.error("请先选中至少一位达人后再导出。");
      return;
    }
    const fieldKeys = selectedCreatorFields.length > 0 ? selectedCreatorFields : creatorFieldCatalog.filter((item) => item.default).map((item) => item.key);
    if (fieldKeys.length === 0) {
      toast.error("请先选择导出字段。");
      return;
    }
    try {
      const response = await exportCreators({
        brand_name: context.brand,
        spu_name: context.spu,
        creators: selectedCreatorPayload,
        rows: creatorDataRows,
        field_keys: fieldKeys,
        template_id: selectedTemplateId,
      });
      const downloadUrl = buildExportDownloadUrl(response.result?.download_url);
      if (downloadUrl) {
        window.open(downloadUrl, "_blank", "noopener,noreferrer");
      }
      toast.success(`导出成功，共 ${Number(response.result?.row_count || creatorDataRows.length || selectedCreatorPayload.length)} 位达人。`);
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "导出失败");
    }
  };

  const executeRetrieve = async (intent: Record<string, unknown>, rawText: string) => {
    setLoading(true);
    setLoadingLogs(["开始解析意图并构造查询向量...", "准备执行库内检索..."]);
    setMessages((prev) => [
      ...prev,
      {
        id: `loading_${Date.now()}`,
        role: "assistant",
        content: "正在执行弹性检索，请稍候。",
        component: "loading",
        timestamp: new Date(),
      },
    ]);

    const response = await retrieveMatches({
      raw_text: rawText,
      brand_name: context.brand,
      spu_name: context.spu,
      intent,
      top_k: expectedCount,
      tag_weights: currentTagWeights,
      enable_external_expansion: true,
      enable_greedy_degrade: true,
      external_page_size: Math.max(expectedCount, 20),
    });

    const result = response.result || {};
    setLatestResult(result);
    setLoadingLogs((result.logs as string[]) || ["检索完成。"]);
    const rows = Array.isArray(result.results) ? (result.results as Array<Record<string, unknown>>) : [];
    setInfluencers(rows.map(mapInfluencer));
    pushAssistantGridMessage(`已为你寻回 ${rows.length} 位匹配达人。你现在可以进入评审，或在底部继续获取下一批。`);
    setLoading(false);
  };

  const handleSend = async () => {
    if (!input.trim() || loading || busyAction) return;
    const rawText = input.trim();
    const userMsg: ChatMessage = {
      id: `user_${Date.now()}`,
      role: "user",
      content: rawText,
      timestamp: new Date(),
    };
    setMessages((prev) => [...prev, userMsg]);
    setInput("");
    setBusyAction(true);
    setLastWeightChanges(null);
    setLastRocchioMeta(null);

    try {
      const [intentRes, spuRes, userRes] = await Promise.all([
        parseIntent({ raw_text: rawText, brand_name: context.brand, spu_name: context.spu }),
        getSpuMemory({ brand_name: context.brand, spu_name: context.spu }).catch(() => ({ success: true, result: {} })),
        getUserMemory({ operator_id: context.operatorId, brand_name: context.brand, spu_name: context.spu }).catch(() => ({ success: true, result: {} })),
      ]);
      const nextIntent = (intentRes.intent || {}) as Record<string, unknown>;
      const nextSpuMemory = (spuRes.result || {}) as Record<string, unknown>;
      const nextUserMemory = (userRes.result || {}) as Record<string, unknown>;
      setParsedIntent(nextIntent);
      setSpuMemory(nextSpuMemory);
      setUserMemory(nextUserMemory);
      setIntentDraft(buildDraft(nextIntent, nextSpuMemory, nextUserMemory));
      setMessages((prev) => [
        ...prev,
        {
          id: `assistant_${Date.now()}`,
          role: "assistant",
          content: "已完成初次语义理解，并为你拉取了当前 SPU 推荐特征与用户私有标签。请先确认意图面板。",
          timestamp: new Date(),
        },
      ]);
      setShowIntentModal(true);
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "语义理解失败");
    } finally {
      setBusyAction(false);
    }
  };

  const handleConfirmIntent = async () => {
    if (!parsedIntent || !intentDraft) return;
    const confirmedIntent = buildConfirmedIntent(parsedIntent, intentDraft);
    setParsedIntent(confirmedIntent);
    setLastWeightChanges(null);
    setLastRocchioMeta(null);
    setShowIntentModal(false);
    try {
      await executeRetrieve(confirmedIntent, String(parsedIntent.raw_text || ""));
    } catch (error) {
      setLoading(false);
      toast.error(error instanceof Error ? error.message : "检索失败");
    }
  };

  const handleRowClick = (inf: Influencer) => {
    const idx = influencers.findIndex((i) => i.id === inf.id);
    setReviewIndex(idx >= 0 ? idx : null);
  };

  const handleReviewAction = (id: number, status: "selected" | "pending" | "rejected") => {
    setInfluencers((prev) => prev.map((item) => (item.id === id ? { ...item, status } : item)));
    if (reviewIndex !== null && reviewIndex < influencers.length - 1) {
      setReviewIndex(reviewIndex + 1);
    } else {
      setReviewIndex(null);
      toast.success("当前评审批次已处理完毕。你可以直接获取更多或确认入库。", { duration: 2200 });
    }
  };

  const handleFission = async () => {
    if (!parsedIntent || !intentDraft || selectedInfluencers.length === 0) {
      toast.error("请至少先选中一位达人，再获取更多。");
      return;
    }
    setBusyAction(true);
    setLoading(true);
    setLoadingLogs(["正在基于 selected/rejected 反馈执行 Rocchio 向量进化...", "准备请求下一批推荐..."]);
    try {
      const response = await nextBatch({
        brand_name: context.brand,
        spu_name: context.spu,
        operator_id: context.operatorId,
        operator_role: context.role,
        intent: buildConfirmedIntent(parsedIntent, intentDraft),
        raw_text: String(parsedIntent.raw_text || ""),
        top_k: expectedCount,
        tag_weights: currentTagWeights,
        selected_ids: selectedInfluencers.map((item) => item.id),
        rejected_ids: rejectedInfluencers.map((item) => item.id),
        pending_ids: pendingInfluencers.map((item) => item.id),
        exclude_history: true,
        use_memory_feedback: true,
        role_time_decay_days: decayStrategy.role_time_decay_days,
        role_time_decay_min_factor: decayStrategy.role_time_decay_min_factor,
        brand_stage_match_factor: decayStrategy.brand_stage_match_factor,
        brand_stage_mismatch_factor: decayStrategy.brand_stage_mismatch_factor,
        campaign_freshness_decay_days: decayStrategy.campaign_freshness_decay_days,
        campaign_freshness_min_factor: decayStrategy.campaign_freshness_min_factor,
        role_decay_overrides: decayStrategy.role_decay_overrides,
        enable_external_expansion: true,
        enable_greedy_degrade: true,
      });
      const nextBatchResult = (response.result || {}) as NextBatchResult;
      const recommendationTask = nextBatchResult.recommendation_task || {};
      const result = (recommendationTask.result || {}) as Record<string, unknown>;
      const weightChanges = nextBatchResult.effective_request?.weight_changes || null;
      const rocchio = nextBatchResult.effective_request?.rocchio || null;
      setLastWeightChanges(weightChanges);
      setLastRocchioMeta(rocchio);
      setLatestResult(result);
      setLoadingLogs((result.logs as string[]) || ["下一批推荐完成。"]);
      const rows = Array.isArray(result.results) ? (result.results as Array<Record<string, unknown>>) : [];
      setInfluencers(rows.map(mapInfluencer));
      if (intentDraft) {
        setIntentDraft(applyWeightChangesToDraft(intentDraft, weightChanges));
      }
      pushAssistantGridMessage(`已基于当前 selected / rejected 反馈生成下一批推荐。${weightChanges?.summary ? ` ${weightChanges.summary}` : ""}${rocchio?.message ? ` ${rocchio.message}` : ""}`);
      toast.success(weightChanges?.summary || "下一批推荐已生成。");
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "下一批推荐失败");
    } finally {
      setLoading(false);
      setBusyAction(false);
    }
  };

  const handleCommit = async () => {
    if (!parsedIntent || !intentDraft || selectedInfluencers.length === 0) {
      toast.error("请至少选中一位达人后再确认入库。");
      return;
    }
    setBusyAction(true);
    try {
      const confirmedIntent = buildConfirmedIntent(parsedIntent, intentDraft);
      const queryVectorMeta = (latestResult?.query_vector_meta as Record<string, unknown>) || {};
      const queryVector = Array.isArray(queryVectorMeta.query_vector) ? (queryVectorMeta.query_vector as number[]) : [];
      const response = await commitAssets({
        brand_name: context.brand,
        spu_name: context.spu,
        operator_id: context.operatorId,
        operator_role: context.role,
        raw_text: String(parsedIntent.raw_text || ""),
        intent: confirmedIntent,
        query_vector: queryVector,
        tag_weights: currentTagWeights,
        data_requirements: confirmedIntent.data_requirements || {},
        selected_ids: selectedInfluencers.map((item) => item.id),
        rejected_ids: rejectedInfluencers.map((item) => item.id),
        pending_ids: pendingInfluencers.map((item) => item.id),
        evolution_snapshot: {
          weight_changes: lastWeightChanges,
          rocchio: lastRocchioMeta,
          strategy: decayStrategy,
        },
        content_summary: `为 ${context.brand} / ${context.spu} 确认 ${selectedInfluencers.length} 位达人合作候选`,
        collaboration_note: `selected=${selectedInfluencers.map((item) => item.name).slice(0, 5).join("、")}${selectedInfluencers.length > 5 ? " 等" : ""}`,
      });
      const result = response.result || {};
      toast.success(`已确认入库 ${Number(result.selected_count || selectedInfluencers.length)} 位达人。`);
      setMessages((prev) => [
        ...prev,
        {
          id: `commit_${Date.now()}`,
          role: "assistant",
          content: `已完成入库提交。当前 SPU 和记忆层已更新，可直接继续发起新的检索或下一批推荐。`,
          timestamp: new Date(),
        },
      ]);
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "确认入库失败");
    } finally {
      setBusyAction(false);
    }
  };

  return (
    <div className="min-h-screen bg-background text-foreground">
      <Navbar />
      <div className="fixed inset-0 z-0">
        <img src={ASSETS.workspaceBg} alt="" className="w-full h-full object-cover opacity-20" />
        <div className="absolute inset-0 bg-background/80" />
      </div>

      <ContextInitModal open={showInit} onConfirm={handleContextConfirm} />
      <IntentReviewModal
        open={showIntentModal}
        brand={context.brand}
        spu={context.spu}
        draft={intentDraft}
        spuMemory={spuMemory}
        userMemory={userMemory}
        weightChanges={lastWeightChanges}
        onDraftChange={setIntentDraft}
        onClose={() => setShowIntentModal(false)}
        onConfirm={handleConfirmIntent}
      />

      <div className="relative z-10 pt-16 pb-20 min-h-screen flex flex-col">
        {!showInit && (
          <div className="border-b border-border/30 bg-card/50 backdrop-blur-sm">
            <div className="container flex items-center gap-4 py-2 text-xs">
              <span className="text-muted-foreground font-chinese">品牌: <span className="text-foreground">{context.brand}</span></span>
              <span className="text-border">|</span>
              <span className="text-muted-foreground font-chinese">SPU: <span className="text-foreground">{context.spu}</span></span>
              <span className="text-border">|</span>
              <span className="text-muted-foreground font-chinese">角色: <span className="text-primary">{ROLES.find((r) => r.id === context.role)?.label}</span></span>
              <span className="text-border">|</span>
              <span className="text-muted-foreground font-chinese">用户: <span className="text-foreground">#{context.operatorId}</span></span>
              <div className="ml-auto flex items-center gap-2 relative">
                <button onClick={() => setShowSettings(!showSettings)} className="flex items-center gap-1 text-muted-foreground hover:text-foreground transition-colors">
                  <Settings2 className="w-3.5 h-3.5" />
                  <span className="font-chinese">期望寻回: {expectedCount}</span>
                  <ChevronDown className="w-3 h-3" />
                </button>
                {showSettings && (
                  <div className="absolute top-full right-0 mt-1 glass-panel rounded-lg p-4 z-50 w-[360px] space-y-4">
                    <div>
                      <label className="text-xs text-muted-foreground font-chinese block mb-2">期望寻回数量</label>
                      <input type="number" value={expectedCount} onChange={(e) => setExpectedCount(Number(e.target.value) || 10)} min={1} max={50} className="w-24 px-2 py-1 rounded bg-input border border-border text-sm text-foreground" />
                    </div>
                    <div className="space-y-3">
                      <div>
                        <div className="text-xs uppercase tracking-wide text-primary font-display mb-2">Decay Strategy</div>
                        <div className="text-[11px] text-muted-foreground font-chinese">按角色、品牌阶段与批次新鲜度细调历史反馈影响，下一次 Fission 将直接使用这里的策略。</div>
                      </div>
                      <div className="grid grid-cols-2 gap-3 text-xs">
                        <label className="space-y-1">
                          <span className="text-muted-foreground font-chinese">统一半衰期天数</span>
                          <input type="number" value={decayStrategy.role_time_decay_days} onChange={(e) => setDecayStrategy((prev) => ({ ...prev, role_time_decay_days: Number(e.target.value) || prev.role_time_decay_days }))} className="w-full px-2 py-1 rounded bg-input border border-border text-sm text-foreground" />
                        </label>
                        <label className="space-y-1">
                          <span className="text-muted-foreground font-chinese">统一最小系数</span>
                          <input type="number" step="0.05" value={decayStrategy.role_time_decay_min_factor} onChange={(e) => setDecayStrategy((prev) => ({ ...prev, role_time_decay_min_factor: Number(e.target.value) || prev.role_time_decay_min_factor }))} className="w-full px-2 py-1 rounded bg-input border border-border text-sm text-foreground" />
                        </label>
                        <label className="space-y-1">
                          <span className="text-muted-foreground font-chinese">阶段匹配系数</span>
                          <input type="number" step="0.05" value={decayStrategy.brand_stage_match_factor} onChange={(e) => setDecayStrategy((prev) => ({ ...prev, brand_stage_match_factor: Number(e.target.value) || prev.brand_stage_match_factor }))} className="w-full px-2 py-1 rounded bg-input border border-border text-sm text-foreground" />
                        </label>
                        <label className="space-y-1">
                          <span className="text-muted-foreground font-chinese">阶段不匹配系数</span>
                          <input type="number" step="0.05" value={decayStrategy.brand_stage_mismatch_factor} onChange={(e) => setDecayStrategy((prev) => ({ ...prev, brand_stage_mismatch_factor: Number(e.target.value) || prev.brand_stage_mismatch_factor }))} className="w-full px-2 py-1 rounded bg-input border border-border text-sm text-foreground" />
                        </label>
                        <label className="space-y-1">
                          <span className="text-muted-foreground font-chinese">新鲜度衰减天数</span>
                          <input type="number" value={decayStrategy.campaign_freshness_decay_days} onChange={(e) => setDecayStrategy((prev) => ({ ...prev, campaign_freshness_decay_days: Number(e.target.value) || prev.campaign_freshness_decay_days }))} className="w-full px-2 py-1 rounded bg-input border border-border text-sm text-foreground" />
                        </label>
                        <label className="space-y-1">
                          <span className="text-muted-foreground font-chinese">新鲜度最小系数</span>
                          <input type="number" step="0.05" value={decayStrategy.campaign_freshness_min_factor} onChange={(e) => setDecayStrategy((prev) => ({ ...prev, campaign_freshness_min_factor: Number(e.target.value) || prev.campaign_freshness_min_factor }))} className="w-full px-2 py-1 rounded bg-input border border-border text-sm text-foreground" />
                        </label>
                      </div>
                      <div className="space-y-2">
                        <div className="text-xs uppercase tracking-wide text-primary font-display">Role Overrides</div>
                        {(["采购", "策划", "客户"] as const).map((roleName) => (
                          <div key={roleName} className="grid grid-cols-[64px_1fr_1fr] gap-2 items-center text-xs">
                            <span className="font-chinese text-muted-foreground">{roleName}</span>
                            <input
                              type="number"
                              value={decayStrategy.role_decay_overrides[roleName]?.decay_days ?? ""}
                              onChange={(e) => setDecayStrategy((prev) => ({
                                ...prev,
                                role_decay_overrides: {
                                  ...prev.role_decay_overrides,
                                  [roleName]: {
                                    decay_days: Number(e.target.value) || prev.role_decay_overrides[roleName]?.decay_days || 0,
                                    min_factor: prev.role_decay_overrides[roleName]?.min_factor || 0.3,
                                  },
                                },
                              }))}
                              className="w-full px-2 py-1 rounded bg-input border border-border text-sm text-foreground"
                            />
                            <input
                              type="number"
                              step="0.05"
                              value={decayStrategy.role_decay_overrides[roleName]?.min_factor ?? ""}
                              onChange={(e) => setDecayStrategy((prev) => ({
                                ...prev,
                                role_decay_overrides: {
                                  ...prev.role_decay_overrides,
                                  [roleName]: {
                                    decay_days: prev.role_decay_overrides[roleName]?.decay_days || 0,
                                    min_factor: Number(e.target.value) || prev.role_decay_overrides[roleName]?.min_factor || 0.3,
                                  },
                                },
                              }))}
                              className="w-full px-2 py-1 rounded bg-input border border-border text-sm text-foreground"
                            />
                          </div>
                        ))}
                      </div>
                    </div>
                  </div>
                )}
              </div>
            </div>
          </div>
        )}

        {!showInit && (
          <div className="flex-1 container py-6">
            {(spuMemoryTags.length > 0 || Number(userMemory?.campaign_count || 0) > 0) && (
              <div className="max-w-5xl mx-auto mb-4 grid md:grid-cols-[1fr_220px] gap-4">
                <div className="glass-panel rounded-xl p-4">
                  <div className="text-xs uppercase tracking-wide text-primary font-display mb-2">SPU 推荐特征</div>
                  <div className="flex flex-wrap gap-2">
                    {spuMemoryTags.length === 0 ? (
                      <span className="text-sm text-muted-foreground font-chinese">当前 SPU 还没有沉淀出的推荐特征。</span>
                    ) : (
                      spuMemoryTags.map((tag) => (
                        <span key={tag} className="px-2.5 py-1 rounded-md text-xs bg-primary/15 text-primary border border-primary/20">{tag}</span>
                      ))
                    )}
                  </div>
                </div>
                <div className="glass-panel rounded-xl p-4">
                  <div className="text-xs uppercase tracking-wide text-primary font-display mb-2">用户私有偏好</div>
                  <div className="text-sm font-chinese text-foreground">历史任务 {Number(userMemory?.campaign_count || 0)} 次</div>
                  <div className="text-xs text-muted-foreground mt-1">用于 Fission 时叠加用户习惯</div>
                </div>
              </div>
            )}

            <FissionInsightBanner weightChanges={lastWeightChanges} rocchio={lastRocchioMeta} />

            {selectedInfluencers.length > 0 && (
              <div className="max-w-5xl mx-auto mb-4 glass-panel rounded-xl p-4 space-y-4">
                <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-3">
                  <div>
                    <div className="text-xs uppercase tracking-wide text-primary font-display mb-1">Creator Data Booster</div>
                    <div className="text-sm font-chinese text-foreground">已选 {selectedInfluencers.length} 位达人，可一键补充全量数据、按字段导出，并保存为模板供后续复用。</div>
                  </div>
                  <div className="flex flex-wrap gap-2">
                    <Button variant="outline" onClick={() => void handleEnrichCreatorData()} disabled={creatorDataLoading} className="border-primary/30 text-primary hover:bg-primary/10">
                      <RefreshCw className={`w-4 h-4 mr-2 ${creatorDataLoading ? "animate-spin" : ""}`} />一键补充数据
                    </Button>
                    <Button variant="outline" onClick={() => void handleExportCreatorData()} disabled={creatorDataLoading || selectedCreatorFields.length === 0}>
                      <ArrowRight className="w-4 h-4 mr-2" />导出当前字段
                    </Button>
                  </div>
                </div>

                <div className="grid lg:grid-cols-[280px_1fr] gap-4">
                  <div className="space-y-3">
                    <div className="space-y-2">
                      <div className="text-xs uppercase tracking-wide text-primary font-display">导出模板</div>
                      <select
                        value={selectedTemplateId}
                        onChange={(e) => handleApplyTemplate(e.target.value)}
                        className="w-full px-3 py-2 rounded-lg bg-input border border-border text-sm text-foreground"
                      >
                        <option value="">不使用模板</option>
                        {exportTemplates.map((template) => (
                          <option key={template.template_id} value={template.template_id}>
                            {template.template_name}
                          </option>
                        ))}
                      </select>
                      <input
                        value={templateName}
                        onChange={(e) => setTemplateName(e.target.value)}
                        placeholder="输入模板名称后可保存"
                        className="w-full px-3 py-2 rounded-lg bg-input border border-border text-sm text-foreground placeholder:text-muted-foreground"
                      />
                      <Button variant="outline" onClick={() => void handleSaveTemplate()} disabled={!templateName.trim()} className="w-full">
                        <Save className="w-4 h-4 mr-2" />保存为导出模板
                      </Button>
                    </div>
                    <div className="space-y-3">
                      <div className="text-xs uppercase tracking-wide text-primary font-display">字段选择</div>
                      <div className="max-h-[320px] overflow-auto space-y-3 pr-1">
                        {creatorFieldGroups.map((group) => (
                          <div key={group.group} className="rounded-lg border border-border/50 bg-card/40 p-3">
                            <div className="text-sm font-chinese text-foreground mb-2">{group.group}</div>
                            <div className="space-y-2">
                              {group.fields.map((field) => {
                                const checked = selectedCreatorFields.includes(field.key);
                                return (
                                  <label key={field.key} className="flex items-start gap-2 text-xs text-muted-foreground">
                                    <input
                                      type="checkbox"
                                      checked={checked}
                                      onChange={(e) => {
                                        setSelectedCreatorFields((prev) => {
                                          if (e.target.checked) return Array.from(new Set([...prev, field.key]));
                                          return prev.filter((item) => item !== field.key);
                                        });
                                      }}
                                      className="mt-0.5"
                                    />
                                    <span>
                                      <span className="text-foreground font-chinese">{field.label}</span>
                                      <span className="block text-[11px] text-muted-foreground/80">{field.key}</span>
                                    </span>
                                  </label>
                                );
                              })}
                            </div>
                          </div>
                        ))}
                      </div>
                    </div>
                  </div>
                  <div className="space-y-3">
                    <div className="flex items-center justify-between">
                      <div>
                        <div className="text-xs uppercase tracking-wide text-primary font-display">补充结果表</div>
                        <div className="text-xs text-muted-foreground font-chinese mt-1">表格会按当前所选字段展示，导出时也将沿用这份字段配置。</div>
                      </div>
                      {creatorDataRows.length > 0 && <div className="text-xs text-muted-foreground">已补充 {creatorDataRows.length} / {selectedInfluencers.length}</div>}
                    </div>
                    <div className="rounded-xl border border-border/50 overflow-hidden bg-card/40">
                      <div className="overflow-auto max-h-[420px]">
                        <table className="min-w-full text-xs">
                          <thead className="bg-background/80 sticky top-0">
                            <tr>
                              <th className="px-3 py-2 text-left font-chinese text-muted-foreground">达人</th>
                              {selectedCreatorFields.map((fieldKey) => {
                                const field = creatorFieldCatalog.find((item) => item.key === fieldKey);
                                return (
                                  <th key={fieldKey} className="px-3 py-2 text-left font-chinese text-muted-foreground whitespace-nowrap">
                                    {field?.label || fieldKey}
                                  </th>
                                );
                              })}
                            </tr>
                          </thead>
                          <tbody>
                            {(creatorDataRows.length > 0 ? creatorDataRows : selectedCreatorPayload).map((row, index) => {
                              const matchedRow = (creatorDataRows[index] || row) as CreatorDataRow & Record<string, unknown>;
                              const fields = (matchedRow.fields || {}) as Record<string, unknown>;
                              const displayFields = (matchedRow.display_fields || {}) as Record<string, string>;
                              return (
                                <tr key={String(matchedRow.creator_id || matchedRow.creator_uid || index)} className="border-t border-border/40">
                                  <td className="px-3 py-2 align-top">
                                    <div className="font-chinese text-foreground">{String((matchedRow.raw as Record<string, unknown> | undefined)?.nickname || (matchedRow as Record<string, unknown>).nickname || `达人 #${index + 1}`)}</div>
                                    <div className="text-[11px] text-muted-foreground mt-1">UID: {String(matchedRow.creator_uid || "-")}</div>
                                  </td>
                                  {selectedCreatorFields.map((fieldKey) => {
                                    const field = creatorFieldCatalog.find((item) => item.key === fieldKey);
                                    const cellValue = displayFields[field?.label || ""] ?? formatCreatorDisplayValue(fields[fieldKey]);
                                    return (
                                      <td key={`${String(matchedRow.creator_id || index)}_${fieldKey}`} className="px-3 py-2 align-top whitespace-nowrap text-muted-foreground">
                                        {cellValue || "-"}
                                      </td>
                                    );
                                  })}
                                </tr>
                              );
                            })}
                          </tbody>
                        </table>
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            )}

            <ScrollArea className="h-[calc(100vh-240px)]">
              <div className="max-w-5xl mx-auto space-y-4 pb-4">
                {messages.map((msg) => (
                  <motion.div key={msg.id} initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} className={`flex gap-3 ${msg.role === "user" ? "justify-end" : "justify-start"}`}>
                    {msg.role !== "user" && (
                      <div className="w-8 h-8 rounded-full bg-primary/10 flex items-center justify-center shrink-0 mt-1"><Sparkles className="w-4 h-4 text-primary" /></div>
                    )}
                    <div className={`max-w-[90%] ${msg.role === "user" ? "rounded-2xl rounded-tr-sm px-4 py-2.5 bg-primary text-primary-foreground" : ""}`}>
                      {msg.role === "user" ? (
                        <p className="text-sm font-chinese">{msg.content}</p>
                      ) : msg.component === "loading" && loading ? (
                        <LoadingTerminal logs={loadingLogs} />
                      ) : msg.component === "grid" ? (
                        <div>
                          <p className="text-sm text-foreground font-chinese mb-3">{msg.content}</p>
                          <Tabs value={activeGroup} onValueChange={setActiveGroup} className="mb-2">
                            <TabsList className="bg-card border border-border/50">
                              {Object.entries(COLUMN_GROUPS).map(([key, group]) => (
                                <TabsTrigger key={key} value={key} className="text-xs font-chinese data-[state=active]:text-primary">
                                  {(group as { label?: string }).label || key}
                                </TabsTrigger>
                              ))}
                            </TabsList>
                          </Tabs>
                          <DataGridList influencers={influencers} onRowClick={handleRowClick} activeGroup={activeGroup} />
                        </div>
                      ) : (
                        <div className="glass-panel rounded-xl px-4 py-3">
                          <p className="text-sm text-foreground font-chinese">{msg.content}</p>
                        </div>
                      )}
                    </div>
                    {msg.role === "user" && (
                      <div className="w-8 h-8 rounded-full bg-secondary flex items-center justify-center shrink-0 mt-1"><User className="w-4 h-4 text-secondary-foreground" /></div>
                    )}
                  </motion.div>
                ))}
                <div ref={chatEndRef} />
              </div>
            </ScrollArea>

            <div className="max-w-5xl mx-auto mt-4">
              <div className="glass-panel rounded-xl p-3 flex items-end gap-3">
                <textarea
                  value={input}
                  onChange={(e) => setInput(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" && !e.shiftKey) {
                      e.preventDefault();
                      void handleSend();
                    }
                  }}
                  placeholder="描述你的达人需求，例如：找几个上海的高冷风女博主，粉丝 10-50 万，图文 CPM 不超过 300..."
                  rows={2}
                  className="flex-1 bg-transparent border-none outline-none resize-none text-sm text-foreground placeholder:text-muted-foreground/50 font-chinese max-h-40"
                />
                <Button onClick={() => void handleSend()} disabled={!input.trim() || busyAction || loading} size="icon" className="shrink-0 h-10 w-10">
                  <Send className="w-4 h-4" />
                </Button>
              </div>
            </div>
          </div>
        )}
      </div>

      <AnimatePresence>
        {reviewIndex !== null && influencers[reviewIndex] && (
          <ReviewModal
            influencer={influencers[reviewIndex]}
            onAction={handleReviewAction}
            onClose={() => setReviewIndex(null)}
            onNext={() => setReviewIndex((prev) => (prev !== null && prev < influencers.length - 1 ? prev + 1 : prev))}
            onPrev={() => setReviewIndex((prev) => (prev !== null && prev > 0 ? prev - 1 : prev))}
            hasNext={reviewIndex < influencers.length - 1}
            hasPrev={reviewIndex > 0}
          />
        )}
      </AnimatePresence>

      <AnimatePresence>
        <FissionDock
          selected={selectedInfluencers}
          spuTags={spuMemoryTags}
          onFission={() => void handleFission()}
          onCommit={() => void handleCommit()}
          busy={busyAction || loading}
        />
      </AnimatePresence>
    </div>
  );
}
