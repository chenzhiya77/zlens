// Typed client for the read-only zlens API. The backend's structured errors
// (see sources/base.py) arrive as { error: { code, message } } with status 503.

export class ApiError extends Error {
  readonly code: string;
  readonly status: number;

  constructor(code: string, message: string, status: number) {
    super(message);
    this.code = code;
    this.status = status;
  }
}

async function getJson<T>(path: string): Promise<T> {
  const res = await fetch(path);
  if (!res.ok) {
    let code = `http_${res.status}`;
    let message = res.statusText;
    try {
      const body = (await res.json()) as { error?: { code?: string; message?: string } };
      if (body.error?.code) code = body.error.code;
      if (body.error?.message) message = body.error.message;
    } catch {
      // non-JSON error body: keep status-based fallbacks
    }
    throw new ApiError(code, message, res.status);
  }
  return res.json() as Promise<T>;
}

export interface SourceRef {
  id: string;
  available: boolean;
  /** Why the source is unavailable (path missing, schema drift); null when fine. */
  error: string | null;
}

export interface MetaInfo {
  source_id: string;
  /** Package version (zlens.__version__) for the footer; comes from the backend. */
  version: string;
  /** Every registered source, including unavailable ones (grey out, don't erase). */
  sources: SourceRef[];
  request_count: number;
  first_request_at: string | null;
  last_request_at: string | null;
  generated_at: string;
  unpriced_models: string[];
}

export interface ModelUsageSummary {
  source: string;
  provider_id: string;
  model_id: string;
  request_count: number;
  input_tokens: number;
  output_tokens: number;
  reasoning_tokens: number;
  cache_creation_tokens: number;
  cache_read_tokens: number;
  total_tokens: number;
  estimated_cost: number | null;
  /** cache_read / (input + cache_read + cache_creation); denominator 0 → null. */
  cache_hit_rate: number | null;
}

export interface MetricDelta {
  /** Previous equal-length window's value; null when it wasn't fully measured. */
  previous: number | null;
  /** (current-previous)/previous; null when either side is unknown or base is 0. */
  change_rate: number | null;
}

export interface PeriodDelta {
  request_count: MetricDelta;
  estimated_cost: MetricDelta;
}

export interface OverviewTotals {
  /** Backend-computed grand totals (full window+source set, no pagination). */
  request_count: number;
  input_tokens: number;
  output_tokens: number;
  reasoning_tokens: number;
  cache_creation_tokens: number;
  cache_read_tokens: number;
  total_tokens: number;
  /** null while any served model is unpriced — never re-sum in the client. */
  estimated_cost: number | null;
}

export interface Overview {
  request_count: number;
  input_tokens: number;
  output_tokens: number;
  reasoning_tokens: number;
  cache_creation_tokens: number;
  cache_read_tokens: number;
  total_tokens: number;
  estimated_cost: number | null;
  /**
   * One-off buyout/plan spend from the price table; never summed with estimated_cost.
   * null means the price table has no buyout row at all (未填); 0 is a real filled-in
   * zero (免费套餐) and must stay distinguishable from null.
   */
  buyout_total: number | null;
  /** cache_read / (input + cache_read + cache_creation) 按全量合并;分母 0 → null。按 token 计。 */
  cache_hit_rate: number | null;
  /**
   * 环比 vs the previous equal-length window; null unless a closed window is set
   * and the previous window is fully inside the data range. Never render a
   * placeholder when null — no "—%", no 0%.
   */
  delta: PeriodDelta | null;
  totals: OverviewTotals | null;
  by_model: ModelUsageSummary[];
}

export const fetchMeta = () => getJson<MetaInfo>("/api/meta");
export const fetchOverview = () => getJson<Overview>("/api/overview");

export interface DailyUsage {
  source: string;
  day: string;
  request_count: number;
  input_tokens: number;
  output_tokens: number;
  reasoning_tokens: number;
  cache_creation_tokens: number;
  cache_read_tokens: number;
  total_tokens: number;
  estimated_cost: number | null;
}

export interface DailyModelUsage {
  source: string;
  day: string;
  provider_id: string;
  model_id: string;
  request_count: number;
  input_tokens: number;
  output_tokens: number;
  reasoning_tokens: number;
  cache_creation_tokens: number;
  cache_read_tokens: number;
  total_tokens: number;
  estimated_cost: number | null;
}

export interface DailyTrends {
  /** Echoed bucket key: "day" or "month" (granularity param). */
  granularity: string;
  days: DailyUsage[];
  by_model: DailyModelUsage[];
}

export const fetchTrends = () => getJson<DailyTrends>("/api/trends/daily");

export interface ProjectUsage {
  source: string;
  directory: string;
  title: string;
  request_count: number;
  input_tokens: number;
  output_tokens: number;
  reasoning_tokens: number;
  cache_creation_tokens: number;
  cache_read_tokens: number;
  total_tokens: number;
  estimated_cost: number | null;
}

export const fetchProjects = () =>
  getJson<{ projects: ProjectUsage[] }>("/api/projects");

export interface LatencyStats {
  sample_count: number;
  p50_ms: number;
  p90_ms: number;
  p99_ms: number;
}

export interface PerformanceReport {
  duration_ms: LatencyStats | null;
  time_to_first_token_ms: LatencyStats | null;
}

export const fetchPerformance = () => getJson<PerformanceReport>("/api/performance");

/** Currency a price screenshot was written in, as reported by the extractor. */
export type Currency = "cny" | "usd";

export interface ModelPrice {
  input: number;
  output: number;
  cache_read: number;
  cache_write: number;
  /** One-off CNY paid for a plan/buyout channel; null means "not a buyout row". */
  buyout_amount: number | null;
}

export interface PriceTable {
  version: number;
  /** All prices are CNY (the app's money base). */
  models: Record<string, ModelPrice>;
  /** Entry-time rate the pricing form folds $ prices with; never used in costing. */
  fx_usd_cny: number | null;
}

export const fetchPricing = () => getJson<PriceTable>("/api/pricing");

export const savePricing = (table: PriceTable) =>
  fetch("/api/pricing", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(table),
  }).then(async (res) => {
    if (!res.ok) {
      let message = "价格表保存失败";
      try {
        // Key/price validation failures name the offending row in `detail`.
        const body = (await res.json()) as { detail?: unknown };
        if (typeof body.detail === "string") message = body.detail;
      } catch {
        // non-JSON error body: keep the generic message
      }
      throw new ApiError(`http_${res.status}`, message, res.status);
    }
    return res.json() as Promise<PriceTable>;
  });

export interface VlmSettings {
  base_url: string;
  model: string;
  api_key_configured: boolean;
}

export const fetchVlmSettings = () => getJson<VlmSettings>("/api/settings/vlm");

export const saveVlmSettings = (payload: {
  base_url?: string;
  model?: string;
  api_key?: string;
}) =>
  fetch("/api/settings/vlm", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  }).then((res) => {
    if (!res.ok) throw new ApiError(`http_${res.status}`, "设置保存失败", res.status);
    return res.json() as Promise<{ ok: boolean }>;
  });

export const testVlm = () =>
  fetch("/api/settings/vlm/test", { method: "POST" }).then(async (res) => {
    if (!res.ok) {
      let code = `http_${res.status}`;
      let message = res.statusText;
      try {
        const body = (await res.json()) as { error?: { code?: string; message?: string } };
        if (body.error?.code) code = body.error.code;
        if (body.error?.message) message = body.error.message;
      } catch {
        // keep status-based fallbacks
      }
      throw new ApiError(code, message, res.status);
    }
    return res.json() as Promise<{ ok: boolean; reply: string }>;
  });

export interface ExtractedPrice {
  model_id: string;
  input: number | null;
  output: number | null;
  cache_read: number | null;
  cache_write: number | null;
}

export interface ExtractResult {
  currency: Currency | null;
  unit: string;
  models: ExtractedPrice[];
}

export const extractPricing = (imageBase64: string, focusModel?: string) =>
  fetch("/api/pricing/extract", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      image_base64: imageBase64,
      ...(focusModel ? { focus_model: focusModel } : {}),
    }),
  }).then(async (res) => {
    if (!res.ok) {
      let code = `http_${res.status}`;
      let message = res.statusText;
      try {
        const body = (await res.json()) as { error?: { code?: string; message?: string } };
        if (body.error?.code) code = body.error.code;
        if (body.error?.message) message = body.error.message;
      } catch {
        // keep status-based fallbacks
      }
      throw new ApiError(code, message, res.status);
    }
    return res.json() as Promise<ExtractResult>;
  });

export interface ErrorGroup {
  source: string;
  error_type: string;
  error_code: string | null;
  request_count: number;
}

export interface HealthReport {
  request_count: number;
  requests_with_retries: number;
  total_retries: number;
  cancelled_by_user: number;
  context_exceeded: number;
  errored_requests: number;
  errors: ErrorGroup[];
}

export const fetchHealth = () => getJson<HealthReport>("/api/health");
