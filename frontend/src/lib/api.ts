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

export interface MetaInfo {
  source_id: string;
  request_count: number;
  first_request_at: string | null;
  last_request_at: string | null;
  generated_at: string;
  unpriced_models: string[];
}

export interface ModelUsageSummary {
  provider_id: string;
  model_id: string;
  request_count: number;
  input_tokens: number;
  output_tokens: number;
  reasoning_tokens: number;
  cache_creation_tokens: number;
  cache_read_tokens: number;
  total_tokens: number;
  estimated_cost_usd: number | null;
}

export interface Overview {
  request_count: number;
  input_tokens: number;
  output_tokens: number;
  reasoning_tokens: number;
  cache_creation_tokens: number;
  cache_read_tokens: number;
  total_tokens: number;
  estimated_cost_usd: number | null;
  by_model: ModelUsageSummary[];
}

export const fetchMeta = () => getJson<MetaInfo>("/api/meta");
export const fetchOverview = () => getJson<Overview>("/api/overview");

export interface DailyUsage {
  day: string;
  request_count: number;
  input_tokens: number;
  output_tokens: number;
  reasoning_tokens: number;
  cache_creation_tokens: number;
  cache_read_tokens: number;
  total_tokens: number;
  estimated_cost_usd: number | null;
}

export interface DailyModelUsage {
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
  estimated_cost_usd: number | null;
}

export interface DailyTrends {
  days: DailyUsage[];
  by_model: DailyModelUsage[];
}

export const fetchTrends = () => getJson<DailyTrends>("/api/trends/daily");

export interface ProjectUsage {
  directory: string;
  title: string;
  request_count: number;
  input_tokens: number;
  output_tokens: number;
  reasoning_tokens: number;
  cache_creation_tokens: number;
  cache_read_tokens: number;
  total_tokens: number;
  estimated_cost_usd: number | null;
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

export interface ErrorGroup {
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
