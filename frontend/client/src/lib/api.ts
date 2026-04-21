const API_BASE = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers || {}),
    },
    ...init,
  });

  if (!response.ok) {
    let detail = `请求失败: ${response.status}`;
    try {
      const data = await response.json();
      detail = data?.detail || data?.message || detail;
    } catch {
      // ignore
    }
    throw new Error(detail);
  }

  return (await response.json()) as T;
}

export interface ApiEnvelope<T> {
  success?: boolean;
  result?: T;
  intent?: T;
  task?: T;
}

export interface IntentParseResult {
  raw_text?: string;
  hard_filters?: Record<string, unknown>;
  data_requirements?: Record<string, unknown>;
  query_plan?: Record<string, unknown>;
  elastic_weights?: Record<string, unknown>;
}

export interface MemoryResult {
  campaign_count?: number;
  preferred_tags?: Array<Record<string, unknown>>;
  recommended_tag_weights?: Record<string, number>;
  role_breakdown?: Record<string, unknown>;
  [key: string]: unknown;
}

export interface FeedbackEvidenceExample {
  internal_id: number;
  display_name?: string;
  tags?: string[];
  source?: string;
  source_bucket?: "current" | "history";
  history_source?: string | null;
  role_name?: string | null;
  time_decay_factor?: number;
  campaign_freshness_factor?: number;
  brand_stage?: string | null;
  brand_stage_factor?: number;
  detail_path?: string;
  weight?: number;
}

export interface WeightDeltaItem {
  key: string;
  display_name: string;
  before: number;
  after: number;
  delta: number;
  direction: "up" | "down";
  reason?: string;
  positive_examples?: FeedbackEvidenceExample[];
  negative_examples?: FeedbackEvidenceExample[];
  positive_source_weights?: Record<string, number>;
  negative_source_weights?: Record<string, number>;
}

export interface WeightChangeExplanation {
  before?: Record<string, number>;
  after?: Record<string, number>;
  summary?: string;
  deltas?: WeightDeltaItem[];
  promoted?: WeightDeltaItem[];
  demoted?: WeightDeltaItem[];
}

export interface RocchioGroupMeta {
  applied?: boolean;
  requested_ids?: number[];
  used_ids?: number[];
  count?: number;
  effective_weight?: number;
  by_source?: Record<string, number>;
}

export interface RocchioMeta {
  applied?: boolean;
  method?: string;
  message?: string;
  strategy?: Record<string, unknown>;
  current_role?: Record<string, unknown>;
  breakdown?: {
    current_positive?: RocchioGroupMeta;
    current_negative?: RocchioGroupMeta;
    history_positive?: RocchioGroupMeta;
    history_negative?: RocchioGroupMeta;
  };
  query_vector?: number[];
}

export interface HistoryExplanationSummary {
  summary?: string;
  promoted?: WeightDeltaItem[];
  demoted?: WeightDeltaItem[];
  rocchio?: RocchioMeta;
  weight_changes?: WeightChangeExplanation;
}

export interface LibraryInfluencerItem {
  internal_id?: number;
  nickname?: string;
  platform?: string;
  followers?: number;
  tags?: string[] | string;
  history_hint?: {
    detail_path?: string;
  };
  [key: string]: unknown;
}

export interface LibraryHistoryTimelineItem {
  record_id?: number;
  campaign_id?: number;
  action_type?: string;
  created_at?: string;
  detail_path?: string;
  record_detail_path?: string;
  campaign_detail_path?: string;
  brand_stage?: string | null;
  content_summary?: string | null;
  material_assets?: Array<Record<string, unknown>>;
  influencer_cards?: Array<Record<string, unknown>>;
  history_explanation?: HistoryExplanationSummary & Record<string, unknown>;
  timeline_preview?: Array<Record<string, unknown>>;
  [key: string]: unknown;
}

export interface FulfillmentRecordDetail {
  record_id?: number;
  campaign_id?: number;
  action_type?: string;
  created_at?: string;
  brand_stage?: string | null;
  campaign?: Record<string, unknown>;
  history_explanation?: HistoryExplanationSummary & Record<string, unknown>;
  influencer_cards?: Array<Record<string, unknown>>;
  content_detail?: {
    content_summary?: string | null;
    collaboration_note?: string | null;
    selected_ids?: number[];
    rejected_ids?: number[];
    pending_ids?: number[];
    tag_weights?: Record<string, number>;
    data_requirements?: Record<string, unknown>;
  };
  material_assets?: Array<Record<string, unknown>>;
  note_previews?: Array<Record<string, unknown>>;
  [key: string]: unknown;
}

export interface DecayStrategyConfig {
  role_time_decay_days: number;
  role_time_decay_min_factor: number;
  brand_stage_match_factor: number;
  brand_stage_mismatch_factor: number;
  campaign_freshness_decay_days: number;
  campaign_freshness_min_factor: number;
  role_decay_overrides: Record<string, { decay_days: number; min_factor: number }>;
}

export interface CreatorDataFieldDefinition {
  key: string;
  label: string;
  group: string;
  source: string;
  default?: boolean;
}

export interface CreatorDataRow {
  creator_id?: number;
  creator_uid?: string;
  provider_status?: string;
  provider_error?: string;
  fields?: Record<string, unknown>;
  display_fields?: Record<string, string>;
  raw?: Record<string, unknown>;
}

export interface ExportTemplateRecord {
  template_id: string;
  template_name: string;
  field_keys: string[];
  brand_name?: string;
  spu_name?: string;
  operator_id?: number | null;
  description?: string;
  updated_at?: number;
  created_at?: number;
}

export interface CreatorDataCatalogResult {
  fields?: CreatorDataFieldDefinition[];
  groups?: Record<string, CreatorDataFieldDefinition[]>;
  default_field_keys?: string[];
}

export interface CreatorDataEnrichResult {
  rows?: CreatorDataRow[];
  field_keys?: string[];
  fields?: CreatorDataFieldDefinition[];
  catalog?: CreatorDataCatalogResult;
  provider_enabled?: boolean;
  selected_template?: ExportTemplateRecord | null;
}

export interface ExportTemplateListResult {
  templates?: ExportTemplateRecord[];
}

export interface CreatorExportResult {
  file_name?: string;
  download_url?: string;
  row_count?: number;
  field_keys?: string[];
  headers?: string[];
  template_id?: string;
}

export interface LibraryHistoryResult {
  mode?: string;
  influencer_profile?: Record<string, unknown>;
  influencer_history?: LibraryHistoryTimelineItem[];
  campaign_timeline?: LibraryHistoryTimelineItem[];
  brand_campaigns?: Array<Record<string, unknown>>;
  record_detail?: FulfillmentRecordDetail;
  query?: Record<string, unknown>;
}

export interface NextBatchResult {
  memory_profile?: {
    spu_memory?: MemoryResult;
    user_memory?: MemoryResult;
    base_merged_tag_weights?: Record<string, number>;
    merged_tag_weights?: Record<string, number>;
  };
  effective_request?: {
    tag_weights?: Record<string, number>;
    manual_tag_weights?: Record<string, number>;
    weight_changes?: WeightChangeExplanation;
    rocchio?: RocchioMeta;
    [key: string]: unknown;
  };
  recommendation_task?: {
    task_id?: string;
    status?: string;
    result?: Record<string, unknown>;
  };
  [key: string]: unknown;
}

export function parseIntent(payload: {
  raw_text: string;
  brand_name?: string;
  spu_name?: string;
}) {
  return request<{ success: boolean; intent: IntentParseResult }>("/api/v1/intent/parse", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function getSpuMemory(params: { brand_name: string; spu_name: string }) {
  const search = new URLSearchParams(params).toString();
  return request<{ success: boolean; result: MemoryResult }>(`/api/v1/spu/memory?${search}`);
}

export function getUserMemory(params: {
  operator_id: number;
  brand_name?: string;
  spu_name?: string;
}) {
  const search = new URLSearchParams(
    Object.entries(params).reduce<Record<string, string>>((acc, [key, value]) => {
      if (value === undefined || value === null || value === "") return acc;
      acc[key] = String(value);
      return acc;
    }, {}),
  ).toString();
  return request<{ success: boolean; result: MemoryResult }>(`/api/v1/user/memory?${search}`);
}

export function retrieveMatches(payload: Record<string, unknown>) {
  return request<{ success: boolean; task_id: string; status: string; result: Record<string, unknown> }>(
    "/api/v1/match/retrieve",
    {
      method: "POST",
      body: JSON.stringify(payload),
    },
  );
}

export function getTask(taskId: string) {
  return request<{ success: boolean; task: Record<string, unknown> }>(`/api/v1/tasks/${taskId}`);
}

export function nextBatch(payload: Record<string, unknown>) {
  return request<{ success: boolean; result: NextBatchResult }>("/api/v1/match/next-batch", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function commitAssets(payload: Record<string, unknown>) {
  return request<{ success: boolean; result: Record<string, unknown> }>("/api/v1/assets/commit", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function listLibrary(params: Record<string, string | number | undefined>) {
  const search = new URLSearchParams(
    Object.entries(params).reduce<Record<string, string>>((acc, [key, value]) => {
      if (value === undefined || value === null || value === "") return acc;
      acc[key] = String(value);
      return acc;
    }, {}),
  ).toString();
  return request<{ success: boolean; result: { items?: LibraryInfluencerItem[]; pagination?: Record<string, unknown>; filters?: Record<string, unknown> } }>(`/api/v1/library/list?${search}`);
}

export function getLibraryHistory(params: Record<string, string | number | undefined>) {
  const search = new URLSearchParams(
    Object.entries(params).reduce<Record<string, string>>((acc, [key, value]) => {
      if (value === undefined || value === null || value === "") return acc;
      acc[key] = String(value);
      return acc;
    }, {}),
  ).toString();
  return request<{ success: boolean; result: LibraryHistoryResult }>(`/api/v1/library/history?${search}`);
}

export function getCreatorDataCatalog() {
  return request<{ success: boolean; result: CreatorDataCatalogResult }>("/api/v1/creator-data/catalog");
}

export function enrichCreatorData(payload: Record<string, unknown>) {
  return request<{ success: boolean; result: CreatorDataEnrichResult }>("/api/v1/creator-data/enrich", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function listExportTemplates(params: Record<string, string | number | undefined>) {
  const search = new URLSearchParams(
    Object.entries(params).reduce<Record<string, string>>((acc, [key, value]) => {
      if (value === undefined || value === null || value === "") return acc;
      acc[key] = String(value);
      return acc;
    }, {}),
  ).toString();
  return request<{ success: boolean; result: ExportTemplateListResult }>(`/api/v1/export/templates?${search}`);
}

export function saveExportTemplate(payload: Record<string, unknown>) {
  return request<{ success: boolean; result: { template?: ExportTemplateRecord } }>("/api/v1/export/templates", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function exportCreators(payload: Record<string, unknown>) {
  return request<{ success: boolean; result: CreatorExportResult }>("/api/v1/export/creators", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function buildExportDownloadUrl(downloadPath?: string | null) {
  if (!downloadPath) return "";
  if (downloadPath.startsWith("http://") || downloadPath.startsWith("https://")) return downloadPath;
  return `${API_BASE}${downloadPath}`;
}
