/*
 * Design: Dark Constellation (暗夜星图)
 * Page: 智能检索工作台 /workspace
 * Layout: Left chat + Right data panels + Bottom dock
 */

import { Navbar } from "@/components/Navbar";
import { ASSETS, COLUMN_GROUPS, ROLES } from "@/lib/constants";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { motion, AnimatePresence } from "framer-motion";
import { useState, useRef, useEffect } from "react";
import {
  Send,
  Settings2,
  Sparkles,
  Terminal,
  ChevronRight,
  X,
  Star,
  Clock,
  Ban,
  ArrowRight,
  Save,
  RefreshCw,
  User,
  SlidersHorizontal,
  Eye,
  ChevronLeft,
  ChevronDown,
  Radar,
  Zap,
} from "lucide-react";
import { toast } from "sonner";

// ===== Types =====
interface ChatMessage {
  id: string;
  role: "user" | "system" | "assistant";
  content: string;
  component?: "intent" | "loading" | "grid";
  timestamp: Date;
}

interface IntentFilter {
  key: string;
  value: string;
  weight: number;
  type: "hard" | "soft";
  source: "spu" | "user";
}

interface Influencer {
  id: string;
  name: string;
  avatar: string;
  platform: string;
  followers: string;
  matchScore: number;
  roiProxy: number;
  tags: string[];
  status: "none" | "selected" | "pending" | "rejected";
  metrics: Record<string, string | number>;
}

// ===== Mock Data =====
const MOCK_INFLUENCERS: Influencer[] = [
  {
    id: "kol_001",
    name: "时尚小鱼",
    avatar: "https://images.unsplash.com/photo-1494790108377-be9c29b29330?w=80&h=80&fit=crop",
    platform: "小红书",
    followers: "52.3万",
    matchScore: 96,
    roiProxy: 8.7,
    tags: ["高冷风", "时尚穿搭", "上海"],
    status: "none",
    metrics: { "曝光中位数(日常)": "12.5万", "阅读中位数(日常)": "3.2万", "互动中位数(日常)": "1,850", "千赞笔记比例": "45%", "百赞笔记比例": "82%" },
  },
  {
    id: "kol_002",
    name: "美妆达人Lily",
    avatar: "https://images.unsplash.com/photo-1438761681033-6461ffad8d80?w=80&h=80&fit=crop",
    platform: "小红书",
    followers: "38.1万",
    matchScore: 91,
    roiProxy: 7.9,
    tags: ["美妆", "护肤", "北京"],
    status: "none",
    metrics: { "曝光中位数(日常)": "8.7万", "阅读中位数(日常)": "2.1万", "互动中位数(日常)": "1,320", "千赞笔记比例": "38%", "百赞笔记比例": "75%" },
  },
  {
    id: "kol_003",
    name: "生活家小王",
    avatar: "https://images.unsplash.com/photo-1507003211169-0a1dd7228f2d?w=80&h=80&fit=crop",
    platform: "小红书",
    followers: "25.6万",
    matchScore: 88,
    roiProxy: 9.2,
    tags: ["生活方式", "家居", "杭州"],
    status: "none",
    metrics: { "曝光中位数(日常)": "6.3万", "阅读中位数(日常)": "1.8万", "互动中位数(日常)": "980", "千赞笔记比例": "32%", "百赞笔记比例": "68%" },
  },
  {
    id: "kol_004",
    name: "穿搭博主CC",
    avatar: "https://images.unsplash.com/photo-1534528741775-53994a69daeb?w=80&h=80&fit=crop",
    platform: "小红书",
    followers: "67.8万",
    matchScore: 85,
    roiProxy: 6.5,
    tags: ["穿搭", "高冷风", "广州"],
    status: "none",
    metrics: { "曝光中位数(日常)": "18.2万", "阅读中位数(日常)": "4.5万", "互动中位数(日常)": "2,100", "千赞笔记比例": "52%", "百赞笔记比例": "88%" },
  },
  {
    id: "kol_005",
    name: "探店小达人",
    avatar: "https://images.unsplash.com/photo-1517841905240-472988babdf9?w=80&h=80&fit=crop",
    platform: "小红书",
    followers: "15.2万",
    matchScore: 82,
    roiProxy: 10.1,
    tags: ["探店", "美食", "上海"],
    status: "none",
    metrics: { "曝光中位数(日常)": "4.1万", "阅读中位数(日常)": "1.2万", "互动中位数(日常)": "750", "千赞笔记比例": "28%", "百赞笔记比例": "62%" },
  },
];

const MOCK_INTENT_FILTERS: IntentFilter[] = [
  { key: "地域", value: "上海", weight: 5, type: "hard", source: "user" },
  { key: "性别", value: "女", weight: 5, type: "hard", source: "user" },
  { key: "风格标签", value: "高冷风", weight: 3, type: "soft", source: "user" },
  { key: "粉丝量", value: "10万+", weight: 4, type: "hard", source: "spu" },
  { key: "互动率", value: ">3%", weight: 4, type: "soft", source: "spu" },
];

// ===== Sub-components =====

function ContextInitModal({
  open,
  onConfirm,
}: {
  open: boolean;
  onConfirm: (brand: string, spu: string, role: number) => void;
}) {
  const [brand, setBrand] = useState("");
  const [spu, setSpu] = useState("");
  const [role, setRole] = useState(2);

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm">
      <motion.div
        initial={{ opacity: 0, scale: 0.95 }}
        animate={{ opacity: 1, scale: 1 }}
        className="glass-panel rounded-2xl p-8 w-full max-w-md glow-red"
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
            <label className="text-sm text-muted-foreground font-chinese mb-2 block">
              当前角色
            </label>
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
            onConfirm(brand, spu, role);
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

function IntentDashboard({ filters }: { filters: IntentFilter[] }) {
  const [localFilters, setLocalFilters] = useState(filters);

  const updateWeight = (index: number, weight: number) => {
    setLocalFilters((prev) =>
      prev.map((f, i) => (i === index ? { ...f, weight } : f))
    );
  };

  return (
    <div className="glass-panel rounded-xl p-5 mt-3">
      <div className="flex items-center gap-2 mb-4">
        <SlidersHorizontal className="w-4 h-4 text-primary" />
        <span className="text-sm font-semibold font-chinese">意图解析结果</span>
        <span className="text-xs text-muted-foreground ml-auto font-chinese">
          拖动滑块调节权重
        </span>
      </div>

      <div className="space-y-3">
        {localFilters.map((filter, i) => (
          <div key={i} className="flex items-center gap-3">
            {/* Tag */}
            <span
              className={`inline-flex items-center gap-1 px-2.5 py-1 rounded-md text-xs font-medium shrink-0 ${
                filter.source === "spu"
                  ? "bg-primary/15 text-primary border border-primary/20"
                  : "bg-secondary text-secondary-foreground border border-border"
              }`}
              title={
                filter.source === "spu"
                  ? "该 SPU 历史高频命中特征"
                  : "基于您的历史筛选习惯自动附加"
              }
            >
              {filter.source === "spu" ? "★" : "♦"} {filter.key}
            </span>

            {/* Value */}
            <span className="text-sm text-foreground font-chinese min-w-[60px]">
              {filter.value}
            </span>

            {/* Weight slider */}
            <div className="flex-1 flex items-center gap-2">
              <input
                type="range"
                min={1}
                max={5}
                value={filter.weight}
                onChange={(e) => updateWeight(i, parseInt(e.target.value))}
                className="flex-1 h-1 accent-[#D4001A] bg-border rounded-full appearance-none cursor-pointer [&::-webkit-slider-thumb]:appearance-none [&::-webkit-slider-thumb]:w-3 [&::-webkit-slider-thumb]:h-3 [&::-webkit-slider-thumb]:rounded-full [&::-webkit-slider-thumb]:bg-primary"
              />
              <span className="font-data text-xs text-primary w-4 text-center">
                {filter.weight}
              </span>
            </div>

            {/* Type badge */}
            <span
              className={`text-[10px] px-1.5 py-0.5 rounded font-chinese ${
                filter.type === "hard"
                  ? "bg-primary/10 text-primary"
                  : "bg-muted text-muted-foreground"
              }`}
            >
              {filter.type === "hard" ? "硬筛" : "软筛"}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}

function LoadingTerminal({ logs }: { logs: string[] }) {
  return (
    <div className="glass-panel rounded-xl p-4 mt-3 font-mono text-xs">
      <div className="flex items-center gap-2 mb-3">
        <Terminal className="w-3.5 h-3.5 text-primary" />
        <span className="text-primary text-[11px]">SIGMA_MATCH::RETRIEVE</span>
        <div className="flex gap-1 ml-auto">
          <div className="w-2 h-2 rounded-full bg-primary pulse-dot" />
          <div
            className="w-2 h-2 rounded-full bg-brand-gold pulse-dot"
            style={{ animationDelay: "0.5s" }}
          />
        </div>
      </div>
      <div className="space-y-1 text-muted-foreground">
        {logs.map((log, i) => (
          <motion.div
            key={i}
            initial={{ opacity: 0, x: -10 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ delay: i * 0.3 }}
            className="flex gap-2"
          >
            <span className="text-primary/50">{">"}</span>
            <span>{log}</span>
          </motion.div>
        ))}
        <div className="typing-cursor text-muted-foreground/50" />
      </div>
    </div>
  );
}

function DataGridList({
  influencers,
  onRowClick,
  activeGroup,
}: {
  influencers: Influencer[];
  onRowClick: (inf: Influencer) => void;
  activeGroup: string;
}) {
  const columns =
    COLUMN_GROUPS[activeGroup as keyof typeof COLUMN_GROUPS]?.columns || [];

  return (
    <div className="glass-panel rounded-xl mt-3 overflow-hidden">
      <div className="overflow-x-auto relative scroll-fade-right">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-border/50">
              <th className="sticky left-0 z-10 bg-card px-4 py-3 text-left text-xs text-muted-foreground font-chinese font-medium whitespace-nowrap">
                博主信息
              </th>
              <th className="px-4 py-3 text-left text-xs text-muted-foreground font-chinese font-medium whitespace-nowrap">
                <span className="text-primary">匹配度</span>
              </th>
              <th className="px-4 py-3 text-left text-xs text-muted-foreground font-chinese font-medium whitespace-nowrap">
                <span className="text-brand-gold">性价比</span>
              </th>
              {columns.map((col) => (
                <th
                  key={col}
                  className="px-4 py-3 text-left text-xs text-muted-foreground font-chinese font-medium whitespace-nowrap"
                >
                  {col}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {influencers.map((inf) => (
              <tr
                key={inf.id}
                onClick={() => onRowClick(inf)}
                className="border-b border-border/30 hover:bg-primary/5 transition-colors cursor-pointer group"
              >
                {/* Sticky: Influencer info */}
                <td className="sticky left-0 z-10 bg-card group-hover:bg-primary/5 transition-colors px-4 py-3 whitespace-nowrap">
                  <div className="flex items-center gap-3">
                    {/* Status indicator */}
                    <div className="w-1.5 h-8 rounded-full shrink-0" style={{
                      background:
                        inf.status === "selected"
                          ? "#D4001A"
                          : inf.status === "pending"
                          ? "#FFB800"
                          : inf.status === "rejected"
                          ? "#444"
                          : "transparent",
                    }} />
                    <img
                      src={inf.avatar}
                      alt={inf.name}
                      className="w-9 h-9 rounded-full object-cover border border-border"
                    />
                    <div>
                      <div className="font-medium text-foreground text-sm font-chinese">
                        {inf.name}
                      </div>
                      <div className="text-xs text-muted-foreground flex items-center gap-1">
                        {inf.platform} · {inf.followers}
                      </div>
                    </div>
                  </div>
                </td>

                {/* Match Score */}
                <td className="px-4 py-3 whitespace-nowrap">
                  <span className="font-data text-sm font-bold text-primary">
                    {inf.matchScore}
                  </span>
                </td>

                {/* ROI Proxy */}
                <td className="px-4 py-3 whitespace-nowrap">
                  <span className="font-data text-sm font-bold text-brand-gold">
                    {inf.roiProxy}
                  </span>
                </td>

                {/* Dynamic columns */}
                {columns.map((col) => (
                  <td
                    key={col}
                    className="px-4 py-3 whitespace-nowrap text-sm text-muted-foreground"
                  >
                    {inf.metrics[col] ?? (
                      <div className="w-12 h-4 rounded bg-muted animate-pulse" />
                    )}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
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
  onAction: (id: string, status: "selected" | "pending" | "rejected") => void;
  onClose: () => void;
  onNext: () => void;
  onPrev: () => void;
  hasNext: boolean;
  hasPrev: boolean;
}) {
  // Mock notes data
  const mockNotes = Array.from({ length: 8 }, (_, i) => ({
    id: `note_${i}`,
    image: `https://images.unsplash.com/photo-${1540000000000 + i * 1000000}?w=300&h=400&fit=crop`,
    title: `笔记标题 ${i + 1}`,
    likes: Math.floor(Math.random() * 5000) + 200,
  }));

  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 backdrop-blur-sm"
    >
      <motion.div
        initial={{ scale: 0.95, opacity: 0 }}
        animate={{ scale: 1, opacity: 1 }}
        exit={{ scale: 0.95, opacity: 0 }}
        className="w-[95vw] h-[90vh] glass-panel rounded-2xl overflow-hidden flex flex-col"
      >
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-border/50">
          <div className="flex items-center gap-4">
            <img
              src={influencer.avatar}
              alt={influencer.name}
              className="w-12 h-12 rounded-full border-2 border-primary/30"
            />
            <div>
              <h3 className="font-semibold text-foreground font-chinese text-lg">
                {influencer.name}
              </h3>
              <div className="flex items-center gap-3 text-sm text-muted-foreground">
                <span>{influencer.platform}</span>
                <span>·</span>
                <span>{influencer.followers} 粉丝</span>
                <span>·</span>
                <div className="flex gap-1">
                  {influencer.tags.map((tag) => (
                    <span
                      key={tag}
                      className="px-2 py-0.5 rounded text-xs bg-primary/10 text-primary border border-primary/20"
                    >
                      {tag}
                    </span>
                  ))}
                </div>
              </div>
            </div>
          </div>

          <div className="flex items-center gap-4">
            <div className="text-right">
              <div className="text-xs text-muted-foreground font-chinese">匹配度</div>
              <div className="font-data text-2xl font-bold text-primary text-glow-red">
                {influencer.matchScore}
              </div>
            </div>
            <div className="text-right">
              <div className="text-xs text-muted-foreground font-chinese">性价比</div>
              <div className="font-data text-2xl font-bold text-brand-gold text-glow-gold">
                {influencer.roiProxy}
              </div>
            </div>
            <button
              onClick={onClose}
              className="p-2 rounded-lg hover:bg-muted transition-colors"
            >
              <X className="w-5 h-5" />
            </button>
          </div>
        </div>

        {/* Body */}
        <div className="flex-1 flex overflow-hidden">
          {/* Left sidebar: metrics */}
          <div className="w-72 border-r border-border/50 p-5 overflow-y-auto">
            <h4 className="text-xs text-muted-foreground font-chinese mb-4 uppercase tracking-wider">
              核心指标
            </h4>
            <div className="space-y-3">
              {Object.entries(influencer.metrics).map(([key, val]) => (
                <div key={key} className="flex justify-between items-center">
                  <span className="text-xs text-muted-foreground font-chinese">
                    {key}
                  </span>
                  <span className="font-data text-xs text-foreground">{val}</span>
                </div>
              ))}
            </div>
          </div>

          {/* Right: Notes waterfall */}
          <div className="flex-1 p-5 overflow-y-auto">
            <h4 className="text-xs text-muted-foreground font-chinese mb-4 uppercase tracking-wider">
              近期笔记
            </h4>
            <div className="columns-2 md:columns-3 gap-4 space-y-4">
              {mockNotes.map((note) => (
                <div
                  key={note.id}
                  className="break-inside-avoid rounded-xl overflow-hidden border border-border/30 hover:border-primary/30 transition-all group"
                >
                  <div className="aspect-[3/4] bg-muted flex items-center justify-center">
                    <Eye className="w-8 h-8 text-muted-foreground/30" />
                  </div>
                  <div className="p-3">
                    <p className="text-xs text-foreground font-chinese truncate">
                      {note.title}
                    </p>
                    <p className="text-[10px] text-muted-foreground mt-1">
                      ♥ {note.likes.toLocaleString()}
                    </p>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>

        {/* Bottom action bar */}
        <div className="border-t border-border/50 px-6 py-4 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <button
              onClick={onPrev}
              disabled={!hasPrev}
              className="p-2 rounded-lg border border-border hover:border-primary/30 disabled:opacity-30 transition-all"
            >
              <ChevronLeft className="w-4 h-4" />
            </button>
            <button
              onClick={onNext}
              disabled={!hasNext}
              className="p-2 rounded-lg border border-border hover:border-primary/30 disabled:opacity-30 transition-all"
            >
              <ChevronRight className="w-4 h-4" />
            </button>
          </div>

          <div className="flex items-center gap-3">
            <Button
              variant="outline"
              onClick={() => onAction(influencer.id, "rejected")}
              className="border-border hover:border-muted-foreground/50 text-muted-foreground"
            >
              <Ban className="w-4 h-4 mr-2" />
              淘汰
            </Button>
            <Button
              variant="outline"
              onClick={() => onAction(influencer.id, "pending")}
              className="border-brand-gold/30 hover:border-brand-gold/60 text-brand-gold"
            >
              <Clock className="w-4 h-4 mr-2" />
              待定
            </Button>
            <Button
              onClick={() => onAction(influencer.id, "selected")}
              className="glow-red"
            >
              <Star className="w-4 h-4 mr-2" />
              选中
            </Button>
          </div>
        </div>
      </motion.div>
    </motion.div>
  );
}

function FissionDock({
  selected,
  onFission,
  onCommit,
}: {
  selected: Influencer[];
  onFission: () => void;
  onCommit: () => void;
}) {
  if (selected.length === 0) return null;

  return (
    <motion.div
      initial={{ y: 100, opacity: 0 }}
      animate={{ y: 0, opacity: 1 }}
      exit={{ y: 100, opacity: 0 }}
      className="fixed bottom-0 left-0 right-0 z-40 border-t border-primary/20"
      style={{
        background: "oklch(0.1 0.008 25 / 95%)",
        backdropFilter: "blur(20px)",
      }}
    >
      <div className="container py-4 flex items-center gap-4">
        {/* Selected avatars */}
        <div className="flex items-center gap-1 flex-1 overflow-x-auto">
          <span className="text-xs text-muted-foreground font-chinese shrink-0 mr-2">
            已选 <span className="text-primary font-data">{selected.length}</span> 人
          </span>
          {selected.map((inf) => (
            <img
              key={inf.id}
              src={inf.avatar}
              alt={inf.name}
              className="w-8 h-8 rounded-full border-2 border-primary/30 shrink-0"
              title={inf.name}
            />
          ))}
        </div>

        {/* Actions */}
        <div className="flex items-center gap-3 shrink-0">
          <Button variant="outline" onClick={onFission} className="border-primary/30 text-primary hover:bg-primary/10">
            <RefreshCw className="w-4 h-4 mr-2" />
            获取更多
          </Button>
          <Button onClick={onCommit} className="glow-red">
            <Save className="w-4 h-4 mr-2" />
            确认入库
          </Button>
        </div>
      </div>
    </motion.div>
  );
}

// ===== Main Page =====
export default function Workspace() {
  const [showInit, setShowInit] = useState(true);
  const [context, setContext] = useState({ brand: "", spu: "", role: 2 });
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [influencers, setInfluencers] = useState<Influencer[]>([]);
  const [reviewIndex, setReviewIndex] = useState<number | null>(null);
  const [activeGroup, setActiveGroup] = useState("basic");
  const [expectedCount, setExpectedCount] = useState(10);
  const [showSettings, setShowSettings] = useState(false);
  const chatEndRef = useRef<HTMLDivElement>(null);

  const scrollToBottom = () => {
    chatEndRef.current?.scrollIntoView({ behavior: "smooth" });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  const selectedInfluencers = influencers.filter((i) => i.status === "selected");

  const handleContextConfirm = (brand: string, spu: string, role: number) => {
    setContext({ brand, spu, role });
    setShowInit(false);
    setMessages([
      {
        id: "sys_1",
        role: "system",
        content: `寻星任务已创建。品牌：${brand}，SPU：${spu}，角色：${ROLES.find((r) => r.id === role)?.label}。请描述您的达人需求。`,
        timestamp: new Date(),
      },
    ]);
  };

  const handleSend = () => {
    if (!input.trim()) return;
    const userMsg: ChatMessage = {
      id: `user_${Date.now()}`,
      role: "user",
      content: input,
      timestamp: new Date(),
    };

    // Intent parse response
    const intentMsg: ChatMessage = {
      id: `intent_${Date.now()}`,
      role: "assistant",
      content: "已解析您的需求，请确认以下筛选条件：",
      component: "intent",
      timestamp: new Date(),
    };

    // Loading terminal
    const loadingMsg: ChatMessage = {
      id: `loading_${Date.now()}`,
      role: "assistant",
      content: "",
      component: "loading",
      timestamp: new Date(),
    };

    setMessages((prev) => [...prev, userMsg]);
    setInput("");

    // Simulate intent parse
    setTimeout(() => {
      setMessages((prev) => [...prev, intentMsg]);
    }, 500);

    // Simulate loading
    setTimeout(() => {
      setMessages((prev) => [...prev, loadingMsg]);
    }, 1500);

    // Simulate results
    setTimeout(() => {
      const gridMsg: ChatMessage = {
        id: `grid_${Date.now()}`,
        role: "assistant",
        content: `已为您寻回 ${MOCK_INFLUENCERS.length} 位匹配达人，点击任意行进入沉浸式评审：`,
        component: "grid",
        timestamp: new Date(),
      };
      setMessages((prev) => [...prev, gridMsg]);
      setInfluencers(MOCK_INFLUENCERS.map((i) => ({ ...i })));
    }, 4000);
  };

  const handleRowClick = (inf: Influencer) => {
    const idx = influencers.findIndex((i) => i.id === inf.id);
    setReviewIndex(idx);
  };

  const handleReviewAction = (
    id: string,
    status: "selected" | "pending" | "rejected"
  ) => {
    setInfluencers((prev) =>
      prev.map((i) => (i.id === id ? { ...i, status } : i))
    );
    // Auto-advance to next
    if (reviewIndex !== null && reviewIndex < influencers.length - 1) {
      setReviewIndex(reviewIndex + 1);
    } else {
      setReviewIndex(null);
      toast.success("评审完毕！已返回数据列表。");
    }
  };

  const handleFission = () => {
    toast.info("正在基于已选达人特征进行进化检索...", { duration: 2000 });
  };

  const handleCommit = () => {
    toast.success(`已将 ${selectedInfluencers.length} 位达人提交入库！`);
  };

  return (
    <div className="min-h-screen bg-background text-foreground">
      <Navbar />

      {/* Background */}
      <div className="fixed inset-0 z-0">
        <img
          src={ASSETS.workspaceBg}
          alt=""
          className="w-full h-full object-cover opacity-20"
        />
        <div className="absolute inset-0 bg-background/80" />
      </div>

      {/* Context Init Modal */}
      <ContextInitModal open={showInit} onConfirm={handleContextConfirm} />

      {/* Main content */}
      <div className="relative z-10 pt-16 pb-20 min-h-screen flex flex-col">
        {/* Context bar */}
        {!showInit && (
          <div className="border-b border-border/30 bg-card/50 backdrop-blur-sm">
            <div className="container flex items-center gap-4 py-2 text-xs">
              <span className="text-muted-foreground font-chinese">
                品牌: <span className="text-foreground">{context.brand}</span>
              </span>
              <span className="text-border">|</span>
              <span className="text-muted-foreground font-chinese">
                SPU: <span className="text-foreground">{context.spu}</span>
              </span>
              <span className="text-border">|</span>
              <span className="text-muted-foreground font-chinese">
                角色: <span className="text-primary">{ROLES.find((r) => r.id === context.role)?.label}</span>
              </span>
              <div className="ml-auto flex items-center gap-2">
                <button
                  onClick={() => setShowSettings(!showSettings)}
                  className="flex items-center gap-1 text-muted-foreground hover:text-foreground transition-colors"
                >
                  <Settings2 className="w-3.5 h-3.5" />
                  <span className="font-chinese">期望寻回: {expectedCount}</span>
                  <ChevronDown className="w-3 h-3" />
                </button>
                {showSettings && (
                  <div className="absolute top-full right-4 mt-1 glass-panel rounded-lg p-3 z-50">
                    <label className="text-xs text-muted-foreground font-chinese block mb-2">
                      期望寻回数量
                    </label>
                    <input
                      type="number"
                      value={expectedCount}
                      onChange={(e) => setExpectedCount(parseInt(e.target.value) || 10)}
                      min={1}
                      max={50}
                      className="w-20 px-2 py-1 rounded bg-input border border-border text-sm text-foreground"
                    />
                  </div>
                )}
              </div>
            </div>
          </div>
        )}

        {/* Chat area */}
        {!showInit && (
          <div className="flex-1 container py-6">
            <ScrollArea className="h-[calc(100vh-200px)]">
              <div className="max-w-4xl mx-auto space-y-4 pb-4">
                {messages.map((msg) => (
                  <motion.div
                    key={msg.id}
                    initial={{ opacity: 0, y: 10 }}
                    animate={{ opacity: 1, y: 0 }}
                    className={`flex gap-3 ${
                      msg.role === "user" ? "justify-end" : "justify-start"
                    }`}
                  >
                    {msg.role !== "user" && (
                      <div className="w-8 h-8 rounded-full bg-primary/10 flex items-center justify-center shrink-0 mt-1">
                        <Sparkles className="w-4 h-4 text-primary" />
                      </div>
                    )}

                    <div
                      className={`max-w-[85%] ${
                        msg.role === "user"
                          ? "rounded-2xl rounded-tr-sm px-4 py-2.5 bg-primary text-primary-foreground"
                          : ""
                      }`}
                    >
                      {msg.role === "user" ? (
                        <p className="text-sm font-chinese">{msg.content}</p>
                      ) : msg.component === "intent" ? (
                        <div>
                          <p className="text-sm text-foreground font-chinese mb-1">
                            {msg.content}
                          </p>
                          <IntentDashboard filters={MOCK_INTENT_FILTERS} />
                        </div>
                      ) : msg.component === "loading" ? (
                        <LoadingTerminal
                          logs={[
                            "正在解析意图向量...",
                            `本地库命中 3 人，触发全网寻回，目标补齐至 ${expectedCount} 人...`,
                            "已寻回 3/5... 扩展搜索半径...",
                            `${MOCK_INFLUENCERS.length}/${expectedCount} 寻回完毕。`,
                          ]}
                        />
                      ) : msg.component === "grid" ? (
                        <div>
                          <p className="text-sm text-foreground font-chinese mb-3">
                            {msg.content}
                          </p>
                          {/* View group tabs */}
                          <Tabs
                            value={activeGroup}
                            onValueChange={setActiveGroup}
                            className="mb-2"
                          >
                            <TabsList className="bg-card border border-border/50">
                              {Object.entries(COLUMN_GROUPS).map(([key, group]) => (
                                <TabsTrigger
                                  key={key}
                                  value={key}
                                  className="text-xs font-chinese data-[state=active]:text-primary"
                                >
                                  {group.label}
                                </TabsTrigger>
                              ))}
                            </TabsList>
                          </Tabs>
                          <DataGridList
                            influencers={influencers}
                            onRowClick={handleRowClick}
                            activeGroup={activeGroup}
                          />
                        </div>
                      ) : (
                        <div className="glass-panel rounded-xl px-4 py-3">
                          <p className="text-sm text-foreground font-chinese">
                            {msg.content}
                          </p>
                        </div>
                      )}
                    </div>

                    {msg.role === "user" && (
                      <div className="w-8 h-8 rounded-full bg-secondary flex items-center justify-center shrink-0 mt-1">
                        <User className="w-4 h-4 text-secondary-foreground" />
                      </div>
                    )}
                  </motion.div>
                ))}
                <div ref={chatEndRef} />
              </div>
            </ScrollArea>

            {/* Input area */}
            <div className="max-w-4xl mx-auto mt-4">
              <div className="glass-panel rounded-xl p-3 flex items-end gap-3">
                <textarea
                  value={input}
                  onChange={(e) => setInput(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" && !e.shiftKey) {
                      e.preventDefault();
                      handleSend();
                    }
                  }}
                  placeholder="描述您的达人需求，例如：找几个上海的高冷风女博主..."
                  rows={1}
                  className="flex-1 bg-transparent border-none outline-none resize-none text-sm text-foreground placeholder:text-muted-foreground/50 font-chinese max-h-32"
                />
                <Button
                  onClick={handleSend}
                  disabled={!input.trim()}
                  size="icon"
                  className="shrink-0 h-9 w-9"
                >
                  <Send className="w-4 h-4" />
                </Button>
              </div>
            </div>
          </div>
        )}
      </div>

      {/* Review Modal */}
      <AnimatePresence>
        {reviewIndex !== null && influencers[reviewIndex] && (
          <ReviewModal
            influencer={influencers[reviewIndex]}
            onAction={handleReviewAction}
            onClose={() => setReviewIndex(null)}
            onNext={() =>
              setReviewIndex((prev) =>
                prev !== null && prev < influencers.length - 1 ? prev + 1 : prev
              )
            }
            onPrev={() =>
              setReviewIndex((prev) =>
                prev !== null && prev > 0 ? prev - 1 : prev
              )
            }
            hasNext={reviewIndex < influencers.length - 1}
            hasPrev={reviewIndex > 0}
          />
        )}
      </AnimatePresence>

      {/* Fission Dock */}
      <AnimatePresence>
        <FissionDock
          selected={selectedInfluencers}
          onFission={handleFission}
          onCommit={handleCommit}
        />
      </AnimatePresence>
    </div>
  );
}
