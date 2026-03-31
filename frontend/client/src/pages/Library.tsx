/*
 * Design: Dark Constellation (暗夜星图)
 * Page: 达人资产库与履约中心 /library
 * Layout: Top filter bar + Data table + Side drawer + Bottom action panel
 */

import { Navbar } from "@/components/Navbar";
import { ASSETS } from "@/lib/constants";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import { motion, AnimatePresence } from "framer-motion";
import { useState } from "react";
import {
  Search,
  Filter,
  Download,
  Send as SendIcon,
  ShoppingCart,
  X,
  ChevronRight,
  Clock,
  FileText,
  Package,
  CheckSquare,
  Square,
  Database,
  Calendar,
  User,
  Building2,
  Tag,
  Upload,
  CheckCircle2,
  AlertCircle,
  HelpCircle,
  ArrowRight,
} from "lucide-react";
import { toast } from "sonner";

// ===== Types =====
interface LibraryInfluencer {
  id: string;
  name: string;
  avatar: string;
  platform: string;
  followers: string;
  brand: string;
  spu: string;
  addedBy: string;
  addedRole: string;
  addedAt: string;
  tags: string[];
  selected: boolean;
}

interface HistoryEvent {
  id: string;
  type: "commit" | "invite" | "order";
  date: string;
  title: string;
  detail: string;
}

// ===== Mock Data =====
const MOCK_LIBRARY: LibraryInfluencer[] = [
  {
    id: "lib_001", name: "时尚小鱼", avatar: "https://images.unsplash.com/photo-1494790108377-be9c29b29330?w=80&h=80&fit=crop",
    platform: "小红书", followers: "52.3万", brand: "某奶粉品牌", spu: "高端系列A段",
    addedBy: "张策划", addedRole: "策划", addedAt: "2026-03-15", tags: ["高冷风", "时尚穿搭"],
    selected: false,
  },
  {
    id: "lib_002", name: "美妆达人Lily", avatar: "https://images.unsplash.com/photo-1438761681033-6461ffad8d80?w=80&h=80&fit=crop",
    platform: "小红书", followers: "38.1万", brand: "某奶粉品牌", spu: "高端系列A段",
    addedBy: "李采购", addedRole: "采购", addedAt: "2026-03-14", tags: ["美妆", "护肤"],
    selected: false,
  },
  {
    id: "lib_003", name: "生活家小王", avatar: "https://images.unsplash.com/photo-1507003211169-0a1dd7228f2d?w=80&h=80&fit=crop",
    platform: "小红书", followers: "25.6万", brand: "某护肤品牌", spu: "精华液系列",
    addedBy: "王客户", addedRole: "客户", addedAt: "2026-03-12", tags: ["生活方式", "家居"],
    selected: false,
  },
  {
    id: "lib_004", name: "穿搭博主CC", avatar: "https://images.unsplash.com/photo-1534528741775-53994a69daeb?w=80&h=80&fit=crop",
    platform: "小红书", followers: "67.8万", brand: "某奶粉品牌", spu: "高端系列A段",
    addedBy: "张策划", addedRole: "策划", addedAt: "2026-03-10", tags: ["穿搭", "高冷风"],
    selected: false,
  },
  {
    id: "lib_005", name: "探店小达人", avatar: "https://images.unsplash.com/photo-1517841905240-472988babdf9?w=80&h=80&fit=crop",
    platform: "小红书", followers: "15.2万", brand: "某护肤品牌", spu: "精华液系列",
    addedBy: "李采购", addedRole: "采购", addedAt: "2026-03-08", tags: ["探店", "美食"],
    selected: false,
  },
];

const MOCK_HISTORY: HistoryEvent[] = [
  { id: "h1", type: "commit", date: "2026-03-15", title: "入库操作", detail: "张策划将 3 位达人入库至「高端系列A段」" },
  { id: "h2", type: "invite", date: "2026-03-16", title: "批量邀约", detail: "向 3 位达人发送合作邀约" },
  { id: "h3", type: "order", date: "2026-03-18", title: "批量下单", detail: "对 2 位达人完成下单操作" },
  { id: "h4", type: "commit", date: "2026-03-20", title: "入库操作", detail: "王客户将 2 位达人入库至「精华液系列」" },
];

// ===== Sub-components =====

function FilterBar({
  onSearch,
  filters,
  setFilters,
}: {
  onSearch: (q: string) => void;
  filters: { brand: string; role: string; dateFrom: string; dateTo: string };
  setFilters: (f: typeof filters) => void;
}) {
  const [query, setQuery] = useState("");

  return (
    <div className="glass-panel rounded-xl p-4">
      <div className="flex flex-wrap items-center gap-3">
        {/* Search */}
        <div className="flex items-center gap-2 flex-1 min-w-[200px] bg-input rounded-lg px-3 py-2 border border-border focus-within:border-primary/30 transition-colors">
          <Search className="w-4 h-4 text-muted-foreground shrink-0" />
          <input
            value={query}
            onChange={(e) => {
              setQuery(e.target.value);
              onSearch(e.target.value);
            }}
            placeholder="搜索达人名称..."
            className="bg-transparent border-none outline-none text-sm text-foreground placeholder:text-muted-foreground/50 font-chinese w-full"
          />
        </div>

        {/* Brand filter */}
        <select
          value={filters.brand}
          onChange={(e) => setFilters({ ...filters, brand: e.target.value })}
          className="bg-input border border-border rounded-lg px-3 py-2 text-sm text-foreground font-chinese outline-none focus:border-primary/30"
        >
          <option value="">全部品牌</option>
          <option value="某奶粉品牌">某奶粉品牌</option>
          <option value="某护肤品牌">某护肤品牌</option>
        </select>

        {/* Role filter */}
        <select
          value={filters.role}
          onChange={(e) => setFilters({ ...filters, role: e.target.value })}
          className="bg-input border border-border rounded-lg px-3 py-2 text-sm text-foreground font-chinese outline-none focus:border-primary/30"
        >
          <option value="">全部角色</option>
          <option value="采购">采购</option>
          <option value="策划">策划</option>
          <option value="客户">客户</option>
        </select>

        {/* Date range */}
        <div className="flex items-center gap-2">
          <Calendar className="w-4 h-4 text-muted-foreground" />
          <input
            type="date"
            value={filters.dateFrom}
            onChange={(e) => setFilters({ ...filters, dateFrom: e.target.value })}
            className="bg-input border border-border rounded-lg px-2 py-2 text-xs text-foreground outline-none focus:border-primary/30"
          />
          <span className="text-muted-foreground text-xs">至</span>
          <input
            type="date"
            value={filters.dateTo}
            onChange={(e) => setFilters({ ...filters, dateTo: e.target.value })}
            className="bg-input border border-border rounded-lg px-2 py-2 text-xs text-foreground outline-none focus:border-primary/30"
          />
        </div>
      </div>
    </div>
  );
}

function HistoryDrawer({
  open,
  onClose,
  events,
}: {
  open: boolean;
  onClose: () => void;
  events: HistoryEvent[];
}) {
  if (!open) return null;

  const typeIcons = {
    commit: Database,
    invite: SendIcon,
    order: ShoppingCart,
  };

  const typeColors = {
    commit: "text-primary",
    invite: "text-brand-gold",
    order: "text-green-400",
  };

  return (
    <motion.div
      initial={{ x: "100%" }}
      animate={{ x: 0 }}
      exit={{ x: "100%" }}
      transition={{ type: "spring", damping: 25, stiffness: 200 }}
      className="fixed top-0 right-0 h-full w-96 z-50 glass-panel border-l border-border/50"
    >
      <div className="flex items-center justify-between p-5 border-b border-border/50">
        <h3 className="font-semibold font-chinese text-foreground">履约历史</h3>
        <button onClick={onClose} className="p-1 rounded hover:bg-muted transition-colors">
          <X className="w-4 h-4" />
        </button>
      </div>

      <ScrollArea className="h-[calc(100%-60px)]">
        <div className="p-5">
          {/* Timeline */}
          <div className="relative">
            {/* Vertical line */}
            <div className="absolute left-4 top-2 bottom-2 w-px bg-border" />

            <div className="space-y-6">
              {events.map((event) => {
                const Icon = typeIcons[event.type];
                const colorClass = typeColors[event.type];
                return (
                  <div key={event.id} className="relative pl-10 group cursor-pointer">
                    {/* Dot */}
                    <div className={`absolute left-2.5 top-1 w-3 h-3 rounded-full border-2 border-background ${
                      event.type === "commit" ? "bg-primary" : event.type === "invite" ? "bg-[#FFB800]" : "bg-green-400"
                    }`} />

                    <div className="glass-panel rounded-lg p-4 hover:border-primary/30 transition-all">
                      <div className="flex items-center gap-2 mb-2">
                        <Icon className={`w-3.5 h-3.5 ${colorClass}`} />
                        <span className="text-sm font-medium font-chinese text-foreground">
                          {event.title}
                        </span>
                        <span className="text-[10px] text-muted-foreground ml-auto">
                          {event.date}
                        </span>
                      </div>
                      <p className="text-xs text-muted-foreground font-chinese">
                        {event.detail}
                      </p>
                      <div className="flex items-center gap-1 mt-2 text-[10px] text-primary opacity-0 group-hover:opacity-100 transition-opacity">
                        查看详情 <ChevronRight className="w-3 h-3" />
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        </div>
      </ScrollArea>
    </motion.div>
  );
}

function SmartExportModal({
  open,
  onClose,
}: {
  open: boolean;
  onClose: () => void;
}) {
  const [step, setStep] = useState(1);
  const [headerInput, setHeaderInput] = useState("");

  const mockMappings = [
    { input: "粉丝数", matched: "粉丝数", status: "auto" as const },
    { input: "互动中位", matched: "互动中位数(日常)", status: "auto" as const },
    { input: "视频均赞", matched: "", status: "pending" as const, suggestions: ["视频互动中位数(日常)", "视频千赞比例", "忽略此列"] },
    { input: "博主昵称", matched: "博主信息", status: "auto" as const },
    { input: "备注说明", matched: "", status: "pending" as const, suggestions: ["忽略此列"] },
  ];

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm">
      <motion.div
        initial={{ opacity: 0, scale: 0.95 }}
        animate={{ opacity: 1, scale: 1 }}
        className="glass-panel rounded-2xl w-full max-w-2xl max-h-[80vh] overflow-hidden flex flex-col"
      >
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-border/50">
          <div className="flex items-center gap-3">
            <Download className="w-5 h-5 text-primary" />
            <h3 className="font-semibold font-chinese">智能导出</h3>
          </div>
          <div className="flex items-center gap-4">
            {/* Step indicators */}
            <div className="flex items-center gap-2">
              {[1, 2, 3, 4].map((s) => (
                <div key={s} className="flex items-center gap-1">
                  <div
                    className={`w-6 h-6 rounded-full flex items-center justify-center text-[10px] font-data ${
                      s === step
                        ? "bg-primary text-primary-foreground"
                        : s < step
                        ? "bg-primary/20 text-primary"
                        : "bg-muted text-muted-foreground"
                    }`}
                  >
                    {s}
                  </div>
                  {s < 4 && (
                    <div className={`w-4 h-px ${s < step ? "bg-primary/40" : "bg-border"}`} />
                  )}
                </div>
              ))}
            </div>
            <button onClick={onClose} className="p-1 rounded hover:bg-muted transition-colors">
              <X className="w-4 h-4" />
            </button>
          </div>
        </div>

        {/* Body */}
        <div className="flex-1 overflow-y-auto p-6">
          {step === 1 && (
            <div className="space-y-4">
              <h4 className="font-chinese text-sm font-medium text-foreground">
                Step 1: 录入目标表头
              </h4>
              <p className="text-xs text-muted-foreground font-chinese">
                粘贴您的 Excel 表头（用逗号或制表符分隔），或上传示例空表
              </p>
              <textarea
                value={headerInput}
                onChange={(e) => setHeaderInput(e.target.value)}
                placeholder="粉丝数, 互动中位, 视频均赞, 博主昵称, 备注说明"
                rows={4}
                className="w-full bg-input border border-border rounded-lg px-4 py-3 text-sm text-foreground placeholder:text-muted-foreground/50 font-chinese outline-none focus:border-primary/30 resize-none"
              />
              <div className="flex items-center gap-3">
                <button className="flex items-center gap-2 px-4 py-2 rounded-lg border border-dashed border-border hover:border-primary/30 text-sm text-muted-foreground font-chinese transition-colors">
                  <Upload className="w-4 h-4" />
                  上传示例表格
                </button>
              </div>
            </div>
          )}

          {step === 2 && (
            <div className="space-y-4">
              <h4 className="font-chinese text-sm font-medium text-foreground">
                Step 2: 精准比对匹配
              </h4>
              <div className="space-y-2">
                {mockMappings
                  .filter((m) => m.status === "auto")
                  .map((m, i) => (
                    <div key={i} className="flex items-center gap-3 p-3 rounded-lg bg-primary/5 border border-primary/10">
                      <CheckCircle2 className="w-4 h-4 text-green-400 shrink-0" />
                      <span className="text-sm font-chinese text-foreground">{m.input}</span>
                      <ArrowRight className="w-3 h-3 text-muted-foreground" />
                      <span className="text-sm font-chinese text-primary">{m.matched}</span>
                      <span className="text-[10px] bg-green-400/10 text-green-400 px-2 py-0.5 rounded ml-auto">
                        已自动匹配
                      </span>
                    </div>
                  ))}
              </div>
            </div>
          )}

          {step === 3 && (
            <div className="space-y-4">
              <h4 className="font-chinese text-sm font-medium text-foreground">
                Step 3: AI 语义排异与确认
              </h4>
              <div className="space-y-3">
                {mockMappings
                  .filter((m) => m.status === "pending")
                  .map((m, i) => (
                    <div key={i} className="p-4 rounded-lg border border-border bg-card">
                      <div className="flex items-center gap-2 mb-3">
                        <AlertCircle className="w-4 h-4 text-[#FFB800]" />
                        <span className="text-sm font-chinese text-foreground font-medium">
                          "{m.input}"
                        </span>
                        <HelpCircle className="w-3 h-3 text-muted-foreground" />
                      </div>
                      <div className="space-y-2 pl-6">
                        {m.suggestions?.map((sug, j) => (
                          <label
                            key={j}
                            className="flex items-center gap-2 text-sm font-chinese text-muted-foreground hover:text-foreground cursor-pointer"
                          >
                            <input
                              type="radio"
                              name={`mapping_${i}`}
                              className="accent-[#D4001A]"
                            />
                            {sug}
                          </label>
                        ))}
                      </div>
                    </div>
                  ))}
              </div>
            </div>
          )}

          {step === 4 && (
            <div className="text-center py-8">
              <CheckCircle2 className="w-16 h-16 text-green-400 mx-auto mb-4" />
              <h4 className="font-chinese text-lg font-medium text-foreground mb-2">
                导出完成
              </h4>
              <p className="text-sm text-muted-foreground font-chinese mb-6">
                文件已生成，同时已将手动确认的映射关系沉淀至系统字典
              </p>
              <Button className="glow-red">
                <Download className="w-4 h-4 mr-2" />
                下载 Excel 文件
              </Button>
            </div>
          )}
        </div>

        {/* Footer */}
        {step < 4 && (
          <div className="border-t border-border/50 px-6 py-4 flex justify-between">
            <Button
              variant="outline"
              onClick={() => setStep(Math.max(1, step - 1))}
              disabled={step === 1}
            >
              上一步
            </Button>
            <Button
              onClick={() => setStep(Math.min(4, step + 1))}
              className={step === 3 ? "glow-red" : ""}
            >
              {step === 3 ? "确认导出" : "下一步"}
            </Button>
          </div>
        )}
      </motion.div>
    </div>
  );
}

// ===== Main Page =====
export default function Library() {
  const [data, setData] = useState<LibraryInfluencer[]>(MOCK_LIBRARY);
  const [filters, setFilters] = useState({ brand: "", role: "", dateFrom: "", dateTo: "" });
  const [showHistory, setShowHistory] = useState(false);
  const [showExport, setShowExport] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");

  const filteredData = data.filter((item) => {
    if (searchQuery && !item.name.includes(searchQuery)) return false;
    if (filters.brand && item.brand !== filters.brand) return false;
    if (filters.role && item.addedRole !== filters.role) return false;
    return true;
  });

  const selectedCount = data.filter((d) => d.selected).length;

  const toggleSelect = (id: string) => {
    setData((prev) =>
      prev.map((d) => (d.id === id ? { ...d, selected: !d.selected } : d))
    );
  };

  const toggleAll = () => {
    const allSelected = filteredData.every((d) => d.selected);
    const ids = new Set(filteredData.map((d) => d.id));
    setData((prev) =>
      prev.map((d) => (ids.has(d.id) ? { ...d, selected: !allSelected } : d))
    );
  };

  return (
    <div className="min-h-screen bg-background text-foreground">
      <Navbar />

      {/* Background */}
      <div className="fixed inset-0 z-0">
        <div className="absolute inset-0 bg-gradient-to-br from-background via-background to-primary/[0.02]" />
      </div>

      <div className="relative z-10 pt-20 pb-24 container">
        {/* Page header */}
        <div className="flex items-center justify-between mb-6">
          <div>
            <h1 className="font-display text-3xl tracking-wider mb-1">
              达人<span className="text-primary">资产库</span>
            </h1>
            <p className="text-sm text-muted-foreground font-chinese">
              管理已入库达人、追踪履约历史、智能导出数据
            </p>
          </div>
          <div className="flex items-center gap-3">
            <Button
              variant="outline"
              onClick={() => setShowHistory(true)}
              className="border-border"
            >
              <Clock className="w-4 h-4 mr-2" />
              履约历史
            </Button>
            <Button
              variant="outline"
              onClick={() => setShowExport(true)}
              className="border-border"
            >
              <Download className="w-4 h-4 mr-2" />
              智能导出
            </Button>
          </div>
        </div>

        {/* Filter bar */}
        <div className="mb-4">
          <FilterBar
            onSearch={setSearchQuery}
            filters={filters}
            setFilters={setFilters}
          />
        </div>

        {/* Data table */}
        <div className="glass-panel rounded-xl overflow-hidden">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border/50">
                <th className="px-4 py-3 text-left w-10">
                  <button onClick={toggleAll}>
                    {filteredData.every((d) => d.selected) && filteredData.length > 0 ? (
                      <CheckSquare className="w-4 h-4 text-primary" />
                    ) : (
                      <Square className="w-4 h-4 text-muted-foreground" />
                    )}
                  </button>
                </th>
                <th className="px-4 py-3 text-left text-xs text-muted-foreground font-chinese font-medium">
                  达人信息
                </th>
                <th className="px-4 py-3 text-left text-xs text-muted-foreground font-chinese font-medium">
                  品牌 / SPU
                </th>
                <th className="px-4 py-3 text-left text-xs text-muted-foreground font-chinese font-medium">
                  标签
                </th>
                <th className="px-4 py-3 text-left text-xs text-muted-foreground font-chinese font-medium">
                  入库人
                </th>
                <th className="px-4 py-3 text-left text-xs text-muted-foreground font-chinese font-medium">
                  入库时间
                </th>
              </tr>
            </thead>
            <tbody>
              {filteredData.map((item) => (
                <tr
                  key={item.id}
                  className="border-b border-border/30 hover:bg-primary/5 transition-colors"
                >
                  <td className="px-4 py-3">
                    <button onClick={() => toggleSelect(item.id)}>
                      {item.selected ? (
                        <CheckSquare className="w-4 h-4 text-primary" />
                      ) : (
                        <Square className="w-4 h-4 text-muted-foreground" />
                      )}
                    </button>
                  </td>
                  <td className="px-4 py-3">
                    <div className="flex items-center gap-3">
                      <img
                        src={item.avatar}
                        alt={item.name}
                        className="w-9 h-9 rounded-full object-cover border border-border"
                      />
                      <div>
                        <div className="font-medium text-foreground font-chinese text-sm">
                          {item.name}
                        </div>
                        <div className="text-xs text-muted-foreground">
                          {item.platform} · {item.followers}
                        </div>
                      </div>
                    </div>
                  </td>
                  <td className="px-4 py-3">
                    <div className="text-sm text-foreground font-chinese">{item.brand}</div>
                    <div className="text-xs text-muted-foreground font-chinese">{item.spu}</div>
                  </td>
                  <td className="px-4 py-3">
                    <div className="flex gap-1 flex-wrap">
                      {item.tags.map((tag) => (
                        <span
                          key={tag}
                          className="px-2 py-0.5 rounded text-[10px] bg-primary/10 text-primary border border-primary/15 font-chinese"
                        >
                          {tag}
                        </span>
                      ))}
                    </div>
                  </td>
                  <td className="px-4 py-3">
                    <div className="flex items-center gap-1.5">
                      <User className="w-3 h-3 text-muted-foreground" />
                      <span className="text-sm text-foreground font-chinese">{item.addedBy}</span>
                      <span className="text-[10px] text-muted-foreground">({item.addedRole})</span>
                    </div>
                  </td>
                  <td className="px-4 py-3 text-sm text-muted-foreground">
                    {item.addedAt}
                  </td>
                </tr>
              ))}

              {filteredData.length === 0 && (
                <tr>
                  <td colSpan={6} className="px-4 py-12 text-center">
                    <Database className="w-10 h-10 text-muted-foreground/30 mx-auto mb-3" />
                    <p className="text-sm text-muted-foreground font-chinese">
                      暂无匹配的达人数据
                    </p>
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* Bottom batch action panel */}
      <AnimatePresence>
        {selectedCount > 0 && (
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
            <div className="container py-4 flex items-center justify-between">
              <span className="text-sm text-muted-foreground font-chinese">
                已选择 <span className="text-primary font-data">{selectedCount}</span> 位达人
              </span>
              <div className="flex items-center gap-3">
                <Button
                  variant="outline"
                  onClick={() => toast.info("批量邀约功能即将上线", { duration: 2000 })}
                  className="border-brand-gold/30 text-brand-gold hover:bg-brand-gold/10"
                >
                  <SendIcon className="w-4 h-4 mr-2" />
                  批量邀约
                </Button>
                <Button
                  onClick={() => toast.info("批量下单功能即将上线", { duration: 2000 })}
                  className="glow-red"
                >
                  <ShoppingCart className="w-4 h-4 mr-2" />
                  批量下单
                </Button>
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* History Drawer */}
      <AnimatePresence>
        {showHistory && (
          <>
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              className="fixed inset-0 z-40 bg-black/50"
              onClick={() => setShowHistory(false)}
            />
            <HistoryDrawer
              open={showHistory}
              onClose={() => setShowHistory(false)}
              events={MOCK_HISTORY}
            />
          </>
        )}
      </AnimatePresence>

      {/* Smart Export Modal */}
      <SmartExportModal open={showExport} onClose={() => setShowExport(false)} />
    </div>
  );
}
