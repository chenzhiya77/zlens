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
