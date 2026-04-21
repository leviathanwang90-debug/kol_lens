import { useEffect, useMemo, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import {
  AlertCircle,
  Building2,
  Calendar,
  Database,
  Filter,
  RefreshCw,
  Search,
  Sparkles,
  User,
  X,
} from "lucide-react";
import { toast } from "sonner";

import { Navbar } from "@/components/Navbar";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import {
  getLibraryHistory,
  listLibrary,
  type FeedbackEvidenceExample,
  type FulfillmentRecordDetail,
  type LibraryHistoryResult,
  type LibraryHistoryTimelineItem,
  type LibraryInfluencerItem,
} from "@/lib/api";

interface FiltersState {
  brand_name: string;
  spu_name: string;
  region: string;
  gender: string;
  tags: string;
  followers_min: string;
  followers_max: string;
}

function formatFollowers(value: unknown) {
  const numeric = Number(String(value ?? "").replace(/[^\d.-]/g, ""));
  if (!Number.isFinite(numeric) || numeric <= 0) return "-";
  if (numeric >= 100000000) return `${(numeric / 100000000).toFixed(1)}亿`;
  if (numeric >= 10000) return `${(numeric / 10000).toFixed(1)}万`;
  return `${numeric}`;
}

function normalizeTags(value: unknown): string[] {
  if (Array.isArray(value)) return value.map((item) => String(item)).filter(Boolean);
  if (typeof value === "string") return value.split(",").map((item) => item.trim()).filter(Boolean);
  return [];
}

function normalizeExamples(value: unknown): Array<Record<string, unknown>> {
  return Array.isArray(value) ? (value as Array<Record<string, unknown>>) : [];
}

function renderEvidenceLabel(item: FeedbackEvidenceExample | Record<string, unknown>) {
  const displayName = String((item as FeedbackEvidenceExample).display_name || (item as Record<string, unknown>).display_name || (item as Record<string, unknown>).internal_id || "未知达人");
  const tags = normalizeTags((item as FeedbackEvidenceExample).tags || (item as Record<string, unknown>).tags);
  const sourceBucket = String((item as FeedbackEvidenceExample).source_bucket || (item as Record<string, unknown>).source_bucket || "current");
  const roleName = String((item as FeedbackEvidenceExample).role_name || (item as Record<string, unknown>).role_name || "");
  const timeDecay = Number((item as FeedbackEvidenceExample).time_decay_factor || (item as Record<string, unknown>).time_decay_factor || 0);
  const freshness = Number((item as FeedbackEvidenceExample).campaign_freshness_factor || (item as Record<string, unknown>).campaign_freshness_factor || 0);
  const stage = String((item as FeedbackEvidenceExample).brand_stage || (item as Record<string, unknown>).brand_stage || "");
  const suffix = [
    tags.length ? tags.slice(0, 2).join(" / ") : "",
    roleName,
    sourceBucket === "history" && timeDecay > 0 ? `时间衰减 ${timeDecay.toFixed(2)}` : "",
    sourceBucket === "history" && freshness > 0 ? `新鲜度 ${freshness.toFixed(2)}` : "",
    stage ? `阶段 ${stage}` : "",
  ].filter(Boolean);
  return `${displayName}${suffix.length ? ` · ${suffix.join(" · ")}` : ""}`;
}

function EvidenceButton({
  item,
  onOpenInfluencer,
}: {
  item: FeedbackEvidenceExample | Record<string, unknown>;
  onOpenInfluencer: (influencerId: number, title?: string) => void;
}) {
  const influencerId = Number((item as FeedbackEvidenceExample).internal_id || (item as Record<string, unknown>).internal_id || 0);
  const label = renderEvidenceLabel(item);
  if (!Number.isFinite(influencerId) || influencerId <= 0) {
    return <div className="text-muted-foreground">{label}</div>;
  }
  return (
    <button
      type="button"
      onClick={() => onOpenInfluencer(influencerId, String((item as FeedbackEvidenceExample).display_name || (item as Record<string, unknown>).display_name || `达人 ${influencerId}`))}
      className="w-full text-left rounded-lg border border-border/50 bg-card/40 px-3 py-2 hover:border-primary/40 hover:bg-primary/5 transition-colors"
    >
      {label}
    </button>
  );
}

function FilterBar({
  keyword,
  setKeyword,
  filters,
  setFilters,
  onSearch,
  loading,
}: {
  keyword: string;
  setKeyword: (value: string) => void;
  filters: FiltersState;
  setFilters: (value: FiltersState) => void;
  onSearch: () => void;
  loading: boolean;
}) {
  return (
    <div className="glass-panel rounded-xl p-4 space-y-3">
      <div className="flex flex-wrap gap-3 items-center">
        <div className="flex items-center gap-2 flex-1 min-w-[220px] bg-input rounded-lg px-3 py-2 border border-border focus-within:border-primary/30 transition-colors">
          <Search className="w-4 h-4 text-muted-foreground" />
          <input
            value={keyword}
            onChange={(e) => setKeyword(e.target.value)}
            placeholder="搜索达人昵称、平台或标签"
            className="w-full bg-transparent outline-none text-sm"
          />
        </div>
        <Button onClick={onSearch} disabled={loading} className="glow-red">
          <RefreshCw className={`w-4 h-4 mr-2 ${loading ? "animate-spin" : ""}`} />刷新
        </Button>
      </div>
      <div className="grid md:grid-cols-3 xl:grid-cols-6 gap-3 text-sm">
        <input className="bg-input border border-border rounded-lg px-3 py-2" placeholder="品牌" value={filters.brand_name} onChange={(e) => setFilters({ ...filters, brand_name: e.target.value })} />
        <input className="bg-input border border-border rounded-lg px-3 py-2" placeholder="SPU" value={filters.spu_name} onChange={(e) => setFilters({ ...filters, spu_name: e.target.value })} />
        <input className="bg-input border border-border rounded-lg px-3 py-2" placeholder="地区" value={filters.region} onChange={(e) => setFilters({ ...filters, region: e.target.value })} />
        <input className="bg-input border border-border rounded-lg px-3 py-2" placeholder="性别" value={filters.gender} onChange={(e) => setFilters({ ...filters, gender: e.target.value })} />
        <input className="bg-input border border-border rounded-lg px-3 py-2" placeholder="标签，逗号分隔" value={filters.tags} onChange={(e) => setFilters({ ...filters, tags: e.target.value })} />
        <div className="grid grid-cols-2 gap-2">
          <input className="bg-input border border-border rounded-lg px-3 py-2" placeholder="粉丝最小" value={filters.followers_min} onChange={(e) => setFilters({ ...filters, followers_min: e.target.value })} />
          <input className="bg-input border border-border rounded-lg px-3 py-2" placeholder="粉丝最大" value={filters.followers_max} onChange={(e) => setFilters({ ...filters, followers_max: e.target.value })} />
        </div>
      </div>
    </div>
  );
}

function TimelineCard({
  row,
  onOpenInfluencer,
  onOpenRecord,
}: {
  row: LibraryHistoryTimelineItem | Record<string, unknown>;
  onOpenInfluencer: (influencerId: number, title?: string) => void;
  onOpenRecord: (recordId: number, title?: string) => void;
}) {
  const explanation = ((row as LibraryHistoryTimelineItem).history_explanation || (row as Record<string, unknown>).history_explanation || {}) as Record<string, unknown>;
  const weightChanges = (explanation.weight_changes || {}) as Record<string, unknown>;
  const promoted = Array.isArray(weightChanges.promoted)
    ? (weightChanges.promoted as Array<Record<string, unknown>>)
    : Array.isArray(explanation.promoted)
      ? (explanation.promoted as Array<Record<string, unknown>>)
      : [];
  const demoted = Array.isArray(weightChanges.demoted)
    ? (weightChanges.demoted as Array<Record<string, unknown>>)
    : Array.isArray(explanation.demoted)
      ? (explanation.demoted as Array<Record<string, unknown>>)
      : [];
  const focus = promoted[0] || demoted[0] || null;
  const focusExamples = focus
    ? [...normalizeExamples(focus.positive_examples), ...normalizeExamples(focus.negative_examples)].slice(0, 3)
    : [];
  const influencerCards = Array.isArray((row as LibraryHistoryTimelineItem).influencer_cards)
    ? ((row as LibraryHistoryTimelineItem).influencer_cards as Array<Record<string, unknown>>)
    : [];

  return (
    <div className="rounded-xl border border-border/50 p-4 bg-card/30 space-y-3">
      <div className="flex items-center justify-between gap-3">
        <div>
          <div className="text-sm font-chinese text-foreground">{String((row as Record<string, unknown>).action_type || "commit")}</div>
          <div className="text-xs text-muted-foreground mt-1">{String((row as Record<string, unknown>).created_at || "-")}</div>
        </div>
        {String((row as Record<string, unknown>).brand_stage || "") && (
          <span className="px-2 py-1 rounded-md text-[10px] border border-primary/20 bg-primary/10 text-primary">
            {String((row as Record<string, unknown>).brand_stage)}
          </span>
        )}
      </div>
      <div className="text-sm font-chinese text-foreground">{String(explanation.summary || "暂无摘要")}</div>
      {focus && (
        <div className="rounded-lg border border-border/50 bg-card/40 p-3 text-xs space-y-2">
          <div className="font-chinese text-primary">关键证据：{String(focus.display_name || focus.key || "-")}</div>
          <div className="space-y-2">
            {focusExamples.length === 0 ? <div className="text-muted-foreground">暂无达人证据</div> : focusExamples.map((item, index) => <EvidenceButton key={`evidence-${index}`} item={item} onOpenInfluencer={onOpenInfluencer} />)}
          </div>
        </div>
      )}
      {influencerCards.length > 0 && (
        <div className="space-y-2">
          <div className="text-xs uppercase tracking-wide text-primary font-display">关联达人</div>
          <div className="flex flex-wrap gap-2">
            {influencerCards.slice(0, 6).map((card, index) => (
              <button
                key={`influencer-card-${index}`}
                type="button"
                onClick={() => onOpenInfluencer(Number(card.internal_id || 0), String(card.display_name || `达人 ${card.internal_id}`))}
                className="px-3 py-1.5 rounded-lg border border-border/50 bg-card/40 text-xs hover:border-primary/40 hover:bg-primary/5 transition-colors"
              >
                {String(card.display_name || card.internal_id || `达人 ${index + 1}`)}
              </button>
            ))}
          </div>
        </div>
      )}
      {Number((row as Record<string, unknown>).record_id || 0) > 0 && (
        <div className="pt-1">
          <Button
            variant="outline"
            size="sm"
            onClick={() => onOpenRecord(Number((row as Record<string, unknown>).record_id || 0), `${String((row as Record<string, unknown>).action_type || "commit")} 详情`)}
            className="border-primary/30 text-primary hover:bg-primary/10"
          >
            查看履约 / 素材详情
          </Button>
        </div>
      )}
    </div>
  );
}

function HistoryDrawer({
  open,
  onClose,
  history,
  title,
  onOpenInfluencer,
  onOpenRecord,
}: {
  open: boolean;
  onClose: () => void;
  history: LibraryHistoryResult | null;
  title: string;
  onOpenInfluencer: (influencerId: number, title?: string) => void;
  onOpenRecord: (recordId: number, title?: string) => void;
}) {
  if (!open) return null;

  const timeline = Array.isArray(history?.campaign_timeline) ? history.campaign_timeline : [];
  const campaigns = Array.isArray(history?.brand_campaigns) ? history.brand_campaigns : [];
  const influencerHistory = Array.isArray(history?.influencer_history) ? history.influencer_history : [];
  const influencerProfile = (history?.influencer_profile || {}) as Record<string, unknown>;

  return (
    <motion.div
      initial={{ x: "100%" }}
      animate={{ x: 0 }}
      exit={{ x: "100%" }}
      transition={{ type: "spring", damping: 22, stiffness: 180 }}
      className="fixed top-0 right-0 z-50 h-full w-[540px] glass-panel border-l border-border/50"
    >
      <div className="flex items-center justify-between px-5 py-4 border-b border-border/50">
        <div>
          <div className="text-xs uppercase tracking-wide text-primary font-display">library/history</div>
          <div className="text-lg font-chinese mt-1">{title}</div>
        </div>
        <button onClick={onClose} className="p-2 rounded-lg hover:bg-muted transition-colors">
          <X className="w-4 h-4" />
        </button>
      </div>
      <ScrollArea className="h-[calc(100%-72px)]">
        <div className="p-5 space-y-4">
          {history?.mode === "influencer_history" && (
            <section className="rounded-xl border border-border/50 bg-card/30 p-4 space-y-3">
              <div className="text-xs uppercase tracking-wide text-primary font-display">达人档案</div>
              <div>
                <div className="text-lg font-chinese text-foreground">{String(influencerProfile.nickname || influencerProfile.name || influencerProfile.internal_id || "达人")}</div>
                <div className="mt-1 text-xs text-muted-foreground">
                  {String(influencerProfile.platform || "未知平台")} · 粉丝 {formatFollowers(influencerProfile.followers)}
                </div>
              </div>
              <div className="flex flex-wrap gap-2">
                {normalizeTags(influencerProfile.tags).length === 0 ? <span className="text-xs text-muted-foreground">暂无标签</span> : normalizeTags(influencerProfile.tags).slice(0, 8).map((tag) => <span key={`profile-tag-${tag}`} className="px-2 py-1 rounded-md bg-card text-xs border border-border/50">{tag}</span>)}
              </div>
            </section>
          )}

          {campaigns.length > 0 && (
            <section className="space-y-3">
              <div className="text-xs uppercase tracking-wide text-primary font-display">批次摘要</div>
              {campaigns.map((item, index) => {
                const summary = (item.history_summary as Record<string, unknown>) || {};
                const promoted = Array.isArray(summary.promoted) ? summary.promoted : [];
                const demoted = Array.isArray(summary.demoted) ? summary.demoted : [];
                return (
                  <div key={`campaign-${index}`} className="rounded-xl border border-border/50 p-4 bg-card/30 space-y-3">
                    <div className="flex items-center justify-between gap-3">
                      <div>
                        <div className="font-chinese text-foreground">{String(item.spu_name || item.brand_name || `批次 ${index + 1}`)}</div>
                        <div className="text-xs text-muted-foreground mt-1">{String(item.created_at || "-")}</div>
                      </div>
                      <div className="text-xs text-muted-foreground">timeline {String(item.timeline_count || 0)}</div>
                    </div>
                    <div className="text-sm font-chinese text-foreground">{String(summary.summary || "暂无推荐偏移摘要")}</div>
                    {(promoted.length > 0 || demoted.length > 0) && (
                      <div className="grid grid-cols-2 gap-3 text-xs">
                        <div className="rounded-lg border border-primary/15 bg-primary/5 p-3">
                          <div className="text-primary font-chinese mb-2">升权</div>
                          <div className="space-y-1">
                            {promoted.slice(0, 2).map((delta, deltaIndex) => (
                              <div key={`promoted-${deltaIndex}`}>{String((delta as Record<string, unknown>).display_name || (delta as Record<string, unknown>).key || "-")}</div>
                            ))}
                          </div>
                        </div>
                        <div className="rounded-lg border border-amber-400/15 bg-amber-400/5 p-3">
                          <div className="text-amber-200 font-chinese mb-2">降权</div>
                          <div className="space-y-1">
                            {demoted.slice(0, 2).map((delta, deltaIndex) => (
                              <div key={`demoted-${deltaIndex}`}>{String((delta as Record<string, unknown>).display_name || (delta as Record<string, unknown>).key || "-")}</div>
                            ))}
                          </div>
                        </div>
                      </div>
                    )}
                  </div>
                );
              })}
            </section>
          )}

          {timeline.length > 0 && (
            <section className="space-y-3">
              <div className="text-xs uppercase tracking-wide text-primary font-display">时间线</div>
              {timeline.map((row, index) => (
                <TimelineCard key={`timeline-${index}`} row={row} onOpenInfluencer={onOpenInfluencer} onOpenRecord={onOpenRecord} />
              ))}
            </section>
          )}

          {influencerHistory.length > 0 && (
            <section className="space-y-3">
              <div className="text-xs uppercase tracking-wide text-primary font-display">达人完整历史时间线</div>
              {influencerHistory.map((row, index) => (
                <TimelineCard key={`influencer-history-${index}`} row={row} onOpenInfluencer={onOpenInfluencer} onOpenRecord={onOpenRecord} />
              ))}
            </section>
          )}

          {campaigns.length === 0 && timeline.length === 0 && influencerHistory.length === 0 && (
            <div className="rounded-xl border border-dashed border-border/50 p-6 text-sm text-muted-foreground font-chinese">
              当前查询暂无可展示的历史摘要。
            </div>
          )}
        </div>
      </ScrollArea>
    </motion.div>
  );
}

function RecordDetailDrawer({
  open,
  onClose,
  detail,
  title,
  onOpenInfluencer,
}: {
  open: boolean;
  onClose: () => void;
  detail: FulfillmentRecordDetail | null;
  title: string;
  onOpenInfluencer: (influencerId: number, title?: string) => void;
}) {
  if (!open) return null;
  const campaign = (detail?.campaign || {}) as Record<string, unknown>;
  const contentDetail = (detail?.content_detail || {}) as Record<string, unknown>;
  const materialAssets = Array.isArray(detail?.material_assets) ? detail.material_assets : [];
  const notePreviews = Array.isArray(detail?.note_previews) ? detail.note_previews : [];
  const influencerCards = Array.isArray(detail?.influencer_cards) ? detail.influencer_cards : [];

  return (
    <motion.div
      initial={{ x: "100%" }}
      animate={{ x: 0 }}
      exit={{ x: "100%" }}
      transition={{ type: "spring", damping: 22, stiffness: 180 }}
      className="fixed top-0 right-0 z-[60] h-full w-[560px] glass-panel border-l border-border/50"
    >
      <div className="flex items-center justify-between px-5 py-4 border-b border-border/50">
        <div>
          <div className="text-xs uppercase tracking-wide text-primary font-display">fulfillment detail</div>
          <div className="text-lg font-chinese mt-1">{title}</div>
        </div>
        <button onClick={onClose} className="p-2 rounded-lg hover:bg-muted transition-colors">
          <X className="w-4 h-4" />
        </button>
      </div>
      <ScrollArea className="h-[calc(100%-72px)]">
        <div className="p-5 space-y-4">
          <section className="rounded-xl border border-border/50 bg-card/30 p-4 space-y-2">
            <div className="text-xs uppercase tracking-wide text-primary font-display">记录概览</div>
            <div className="text-lg font-chinese text-foreground">{String(detail?.action_type || "commit")}</div>
            <div className="text-xs text-muted-foreground">{String(detail?.created_at || "-")}</div>
            <div className="grid grid-cols-2 gap-3 text-sm pt-2">
              <div className="rounded-lg border border-border/50 p-3 bg-card/40">
                <div className="text-xs text-muted-foreground">品牌 / SPU</div>
                <div className="font-chinese mt-1">{String(campaign.brand_name || "-")} / {String(campaign.spu_name || "-")}</div>
              </div>
              <div className="rounded-lg border border-border/50 p-3 bg-card/40">
                <div className="text-xs text-muted-foreground">品牌阶段</div>
                <div className="font-chinese mt-1">{String(detail?.brand_stage || "-")}</div>
              </div>
            </div>
          </section>

          <section className="rounded-xl border border-border/50 bg-card/30 p-4 space-y-3">
            <div className="text-xs uppercase tracking-wide text-primary font-display">履约内容详情</div>
            <div className="text-sm font-chinese text-foreground">{String(contentDetail.content_summary || detail?.history_explanation?.summary || "暂无履约内容摘要")}</div>
            {String(contentDetail.collaboration_note || "") && (
              <div className="text-xs text-muted-foreground leading-6">{String(contentDetail.collaboration_note || "")}</div>
            )}
            <div className="grid grid-cols-3 gap-3 text-xs">
              <div className="rounded-lg border border-primary/15 bg-primary/5 p-3">
                <div className="text-primary mb-1">已选</div>
                <div>{Array.isArray(contentDetail.selected_ids) ? contentDetail.selected_ids.length : 0}</div>
              </div>
              <div className="rounded-lg border border-amber-400/15 bg-amber-400/5 p-3">
                <div className="text-amber-200 mb-1">淘汰</div>
                <div>{Array.isArray(contentDetail.rejected_ids) ? contentDetail.rejected_ids.length : 0}</div>
              </div>
              <div className="rounded-lg border border-border/50 bg-card/40 p-3">
                <div className="text-muted-foreground mb-1">待定</div>
                <div>{Array.isArray(contentDetail.pending_ids) ? contentDetail.pending_ids.length : 0}</div>
              </div>
            </div>
          </section>

          <section className="rounded-xl border border-border/50 bg-card/30 p-4 space-y-3">
            <div className="text-xs uppercase tracking-wide text-primary font-display">关联达人</div>
            <div className="flex flex-wrap gap-2">
              {influencerCards.length === 0 ? <div className="text-xs text-muted-foreground">暂无关联达人</div> : influencerCards.map((card, index) => (
                <button
                  key={`detail-influencer-${index}`}
                  type="button"
                  onClick={() => onOpenInfluencer(Number((card as Record<string, unknown>).internal_id || 0), String((card as Record<string, unknown>).display_name || `达人 ${index + 1}`))}
                  className="px-3 py-1.5 rounded-lg border border-border/50 bg-card/40 text-xs hover:border-primary/40 hover:bg-primary/5 transition-colors"
                >
                  {String((card as Record<string, unknown>).display_name || (card as Record<string, unknown>).internal_id || `达人 ${index + 1}`)}
                </button>
              ))}
            </div>
          </section>

          <section className="rounded-xl border border-border/50 bg-card/30 p-4 space-y-3">
            <div className="text-xs uppercase tracking-wide text-primary font-display">素材资产</div>
            {materialAssets.length === 0 ? (
              <div className="text-xs text-muted-foreground">当前记录尚未提交显式素材资产，已自动回退展示内容笔记预览。</div>
            ) : (
              <div className="space-y-2">
                {materialAssets.map((asset, index) => (
                  <div key={`asset-${index}`} className="rounded-lg border border-border/50 bg-card/40 p-3 text-sm space-y-1">
                    <div className="font-chinese text-foreground">{String((asset as Record<string, unknown>).title || `素材 ${index + 1}`)}</div>
                    <div className="text-xs text-muted-foreground">{String((asset as Record<string, unknown>).type || "asset")}</div>
                    {String((asset as Record<string, unknown>).url || "") && (
                      <a href={String((asset as Record<string, unknown>).url)} target="_blank" rel="noreferrer" className="text-xs text-primary underline break-all">{String((asset as Record<string, unknown>).url)}</a>
                    )}
                  </div>
                ))}
              </div>
            )}
          </section>

          <section className="rounded-xl border border-border/50 bg-card/30 p-4 space-y-3">
            <div className="text-xs uppercase tracking-wide text-primary font-display">内容笔记预览</div>
            {notePreviews.length === 0 ? (
              <div className="text-xs text-muted-foreground">暂无可用的合作内容预览。</div>
            ) : (
              <div className="space-y-2">
                {notePreviews.map((note, index) => (
                  <div key={`note-${index}`} className="rounded-lg border border-border/50 bg-card/40 p-3 text-sm space-y-1">
                    <div className="font-chinese text-foreground">{String((note as Record<string, unknown>).influencer_name || "达人内容")}</div>
                    <div className="text-xs text-muted-foreground">{String((note as Record<string, unknown>).note_type || "笔记")} · {String((note as Record<string, unknown>).published_at || "-")}</div>
                    <div className="text-xs text-muted-foreground">阅读 {String((note as Record<string, unknown>).reads || 0)} · 点赞 {String((note as Record<string, unknown>).likes || 0)}</div>
                    {String((note as Record<string, unknown>).cover_image_url || "") && (
                      <a href={String((note as Record<string, unknown>).cover_image_url)} target="_blank" rel="noreferrer" className="text-xs text-primary underline break-all">查看封面素材</a>
                    )}
                  </div>
                ))}
              </div>
            )}
          </section>
        </div>
      </ScrollArea>
    </motion.div>
  );
}

export default function Library() {
  const [keyword, setKeyword] = useState("");
  const [filters, setFilters] = useState<FiltersState>({
    brand_name: "",
    spu_name: "",
    region: "",
    gender: "",
    tags: "",
    followers_min: "",
    followers_max: "",
  });
  const [items, setItems] = useState<LibraryInfluencerItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [drawerTitle, setDrawerTitle] = useState("历史详情");
  const [historyResult, setHistoryResult] = useState<LibraryHistoryResult | null>(null);
  const [influencerDrawerOpen, setInfluencerDrawerOpen] = useState(false);
  const [influencerDrawerTitle, setInfluencerDrawerTitle] = useState("达人时间线");
  const [influencerHistoryResult, setInfluencerHistoryResult] = useState<LibraryHistoryResult | null>(null);
  const [recordDrawerOpen, setRecordDrawerOpen] = useState(false);
  const [recordDrawerTitle, setRecordDrawerTitle] = useState("履约详情");
  const [recordDetail, setRecordDetail] = useState<FulfillmentRecordDetail | null>(null);

  const activeFilterCount = useMemo(
    () => Object.values(filters).filter(Boolean).length + (keyword ? 1 : 0),
    [filters, keyword],
  );

  const loadLibrary = async () => {
    setLoading(true);
    try {
      const response = await listLibrary({
        keyword,
        brand_name: filters.brand_name,
        spu_name: filters.spu_name,
        region: filters.region,
        gender: filters.gender,
        tags: filters.tags,
        followers_min: filters.followers_min,
        followers_max: filters.followers_max,
      });
      setItems(response.result.items || []);
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "资产库加载失败");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void loadLibrary();
  }, []);

  const openBrandHistory = async (brandName: string, spuName?: string) => {
    setHistoryLoading(true);
    try {
      const response = await getLibraryHistory({ brand_name: brandName, spu_name: spuName });
      setHistoryResult(response.result);
      setDrawerTitle(`${brandName}${spuName ? ` / ${spuName}` : ""} 历史摘要`);
      setDrawerOpen(true);
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "历史查询失败");
    } finally {
      setHistoryLoading(false);
    }
  };

  const openInfluencerHistory = async (influencerId: number, title?: string) => {
    if (!Number.isFinite(influencerId) || influencerId <= 0) return;
    setHistoryLoading(true);
    try {
      const response = await getLibraryHistory({ influencer_id: influencerId });
      setInfluencerHistoryResult(response.result);
      setInfluencerDrawerTitle(title ? `${title} · 完整时间线` : `达人 ${influencerId} · 完整时间线`);
      setInfluencerDrawerOpen(true);
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "达人时间线加载失败");
    } finally {
      setHistoryLoading(false);
    }
  };

  const openRecordDetail = async (recordId: number, title?: string) => {
    if (!Number.isFinite(recordId) || recordId <= 0) return;
    setHistoryLoading(true);
    try {
      const response = await getLibraryHistory({ record_id: recordId });
      setRecordDetail((response.result?.record_detail || null) as FulfillmentRecordDetail | null);
      setRecordDrawerTitle(title ? `${title} · 履约详情` : `记录 ${recordId} · 履约详情`);
      setRecordDrawerOpen(true);
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "履约详情加载失败");
    } finally {
      setHistoryLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-background text-foreground overflow-hidden">
      <Navbar />
      <div className="relative z-10 pt-16 pb-12 min-h-screen">
        <div className="absolute inset-0 bg-gradient-to-br from-background via-background/95 to-background pointer-events-none" />
        <div className="relative max-w-7xl mx-auto px-6 py-8 space-y-6">
          <div className="flex flex-col lg:flex-row lg:items-end lg:justify-between gap-4">
            <div>
              <div className="text-xs uppercase tracking-[0.24em] text-primary font-display">Library & History</div>
              <h1 className="text-4xl font-display mt-2">达人资产库与推荐复盘</h1>
              <p className="text-muted-foreground font-chinese mt-2 max-w-3xl">
                当前页面已接入真实的资产库列表与历史查询接口，可直接查看某个品牌 / SPU 在不同批次中如何发生 tag 权重偏移，并继续下钻到某位达人的完整历史时间线。
              </p>
            </div>
            <div className="glass-panel rounded-xl px-4 py-3 min-w-[240px]">
              <div className="text-xs uppercase tracking-wide text-primary font-display">Filters</div>
              <div className="text-sm font-chinese mt-2">已启用 {activeFilterCount} 个筛选条件</div>
              <div className="text-xs text-muted-foreground mt-1">支持按品牌、SPU、地区、性别、粉丝区间与标签过滤。</div>
            </div>
          </div>

          <FilterBar
            keyword={keyword}
            setKeyword={setKeyword}
            filters={filters}
            setFilters={setFilters}
            onSearch={() => void loadLibrary()}
            loading={loading}
          />

          <div className="grid lg:grid-cols-[1fr_320px] gap-6">
            <div className="glass-panel rounded-2xl overflow-hidden">
              <div className="px-5 py-4 border-b border-border/50 flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <Database className="w-4 h-4 text-primary" />
                  <span className="font-chinese font-semibold">资产库列表</span>
                </div>
                <div className="text-xs text-muted-foreground">共 {items.length} 位达人</div>
              </div>
              <ScrollArea className="h-[calc(100vh-280px)]">
                <div className="divide-y divide-border/40">
                  {items.length === 0 && !loading && (
                    <div className="p-8 text-center text-sm text-muted-foreground font-chinese">当前筛选条件下暂无达人。</div>
                  )}
                  {items.map((item, index) => {
                    const brandName = String(item.brand_name || item.brand || "");
                    const spuName = String(item.spu_name || item.spu || "");
                    const tags = normalizeTags(item.tags);
                    return (
                      <div key={`item-${item.internal_id || index}`} className="p-5 hover:bg-card/30 transition-colors">
                        <div className="flex items-start justify-between gap-4">
                          <div className="space-y-2 min-w-0">
                            <div className="flex items-center gap-2 flex-wrap">
                              <div className="text-lg font-chinese text-foreground">{String(item.nickname || item.name || item.internal_id || `达人 ${index + 1}`)}</div>
                              <span className="px-2 py-1 rounded-md text-[10px] bg-primary/10 text-primary border border-primary/20">{String(item.platform || "未知平台")}</span>
                            </div>
                            <div className="flex flex-wrap gap-3 text-xs text-muted-foreground">
                              <span className="inline-flex items-center gap-1"><User className="w-3 h-3" />粉丝 {formatFollowers(item.followers)}</span>
                              <span className="inline-flex items-center gap-1"><Building2 className="w-3 h-3" />{brandName || "未绑定品牌"}</span>
                              <span className="inline-flex items-center gap-1"><Calendar className="w-3 h-3" />{String(item.created_at || item.added_at || "-")}</span>
                            </div>
                            <div className="flex flex-wrap gap-2">
                              {tags.length === 0 ? <span className="text-xs text-muted-foreground">暂无标签</span> : tags.slice(0, 6).map((tag) => <span key={`${item.internal_id}-${tag}`} className="px-2 py-1 rounded-md bg-card text-xs border border-border/50">{tag}</span>)}
                            </div>
                          </div>
                          <div className="shrink-0 flex flex-col gap-2">
                            <Button
                              variant="outline"
                              disabled={historyLoading || !brandName}
                              onClick={() => void openBrandHistory(brandName, spuName || undefined)}
                              className="border-primary/30 text-primary hover:bg-primary/10"
                            >
                              <Sparkles className="w-4 h-4 mr-2" />查看推荐偏移
                            </Button>
                            {Number(item.internal_id || 0) > 0 && (
                              <Button
                                variant="outline"
                                disabled={historyLoading}
                                onClick={() => void openInfluencerHistory(Number(item.internal_id || 0), String(item.nickname || item.name || `达人 ${item.internal_id}`))}
                                className="border-border/50 hover:border-primary/30"
                              >
                                查看达人时间线
                              </Button>
                            )}
                          </div>
                        </div>
                      </div>
                    );
                  })}
                </div>
              </ScrollArea>
            </div>

            <div className="space-y-4">
              <div className="glass-panel rounded-xl p-4">
                <div className="flex items-center gap-2 mb-2">
                  <Filter className="w-4 h-4 text-primary" />
                  <div className="text-xs uppercase tracking-wide text-primary font-display">Explainable History</div>
                </div>
                <p className="text-sm font-chinese text-foreground">现在 `library/history` 不仅能展示每批次 Fission 的摘要、Rocchio 说明和达人证据，还支持继续下钻到达人完整时间线。</p>
                <div className="mt-3 text-xs text-muted-foreground space-y-2 font-chinese">
                  <div>1. 看到哪些 tag 被升权/降权。</div>
                  <div>2. 区分变化来自本轮反馈还是历史反馈。</div>
                  <div>3. 点击证据达人，继续查看完整历史时间线。</div>
                </div>
              </div>
              <div className="glass-panel rounded-xl p-4 border border-primary/20 bg-primary/5">
                <div className="flex items-center gap-2 mb-2">
                  <AlertCircle className="w-4 h-4 text-primary" />
                  <div className="text-xs uppercase tracking-wide text-primary font-display">Decay Upgrade</div>
                </div>
                <p className="text-sm font-chinese text-foreground">后端已支持按角色、品牌阶段和 campaign 新鲜度做更细粒度衰减，历史证据卡片中会直接显示这些因子的解释线索。</p>
              </div>
            </div>
          </div>
        </div>
      </div>

      <AnimatePresence>
        <HistoryDrawer
          open={drawerOpen}
          onClose={() => setDrawerOpen(false)}
          history={historyResult}
          title={drawerTitle}
          onOpenInfluencer={openInfluencerHistory}
          onOpenRecord={openRecordDetail}
        />
      </AnimatePresence>
      <AnimatePresence>
        <HistoryDrawer
          open={influencerDrawerOpen}
          onClose={() => setInfluencerDrawerOpen(false)}
          history={influencerHistoryResult}
          title={influencerDrawerTitle}
          onOpenInfluencer={openInfluencerHistory}
          onOpenRecord={openRecordDetail}
        />
      </AnimatePresence>
      <AnimatePresence>
        <RecordDetailDrawer
          open={recordDrawerOpen}
          onClose={() => setRecordDrawerOpen(false)}
          detail={recordDetail}
          title={recordDrawerTitle}
          onOpenInfluencer={openInfluencerHistory}
        />
      </AnimatePresence>
    </div>
  );
}
