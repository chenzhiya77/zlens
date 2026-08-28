import { useQuery } from "@tanstack/react-query";

import { EmptyBlock, ErrorBlock, LoadingBlock } from "../components/states";
import { fetchHealth, fetchPerformance } from "../lib/api";
import type { LatencyStats } from "../lib/api";

function LatencyPanel({
  title,
  stats,
  note,
}: {
  title: string;
  stats: LatencyStats | null;
  note?: string;
}) {
  return (
    <div className="flex-1 rounded-xl border border-zinc-800/80 bg-zinc-900 p-5">
      <div className="mb-4 flex items-baseline justify-between">
        <h3 className="text-sm font-medium text-zinc-300">{title}</h3>
        <span className="text-xs text-zinc-500">
          有效样本 {stats ? stats.sample_count.toLocaleString("zh-CN") : 0}
        </span>
      </div>
      {!stats ? (
        <p className="py-8 text-center text-sm text-zinc-600">暂无样本</p>
      ) : (
        <div className="space-y-4">
          {(
            [
              ["P50", stats.p50_ms],
              ["P90", stats.p90_ms],
              ["P99", stats.p99_ms],
            ] as const
          ).map(([label, ms], index) => {
            const max = stats.p99_ms || 1;
            const width = Math.max((ms / max) * 100, 2);
            const colors = ["bg-sky-500", "bg-sky-400/70", "bg-sky-300/40"];
            return (
              <div key={label}>
                <div className="mb-1 flex items-baseline justify-between text-xs">
                  <span className="text-zinc-500">{label}</span>
                  <span className="tabular-nums text-zinc-300">
                    {ms >= 1000 ? `${(ms / 1000).toFixed(1)} s` : `${ms.toFixed(0)} ms`}
                  </span>
                </div>
                <div className="h-2 rounded bg-zinc-800">
                  <div className={`h-2 rounded ${colors[index]}`} style={{ width: `${width}%` }} />
                </div>
              </div>
            );
          })}
        </div>
      )}
      {note && <p className="mt-4 text-xs text-zinc-600">{note}</p>}
    </div>
  );
}

function HealthCard({ value, label }: { value: string; label: string }) {
  return (
    <div className="rounded-xl border border-zinc-800/80 bg-zinc-900 px-5 py-4">
      <div className="text-2xl font-semibold tabular-nums">{value}</div>
      <p className="mt-1 text-xs text-zinc-500">{label}</p>
    </div>
  );
}

// Merged "how well is it running" view: latency percentiles plus retry / error
// health, formerly two thin pages.
export default function Runtime() {
  const perf = useQuery({ queryKey: ["performance"], queryFn: fetchPerformance });
  const health = useQuery({ queryKey: ["health"], queryFn: fetchHealth });

  if (perf.isLoading || health.isLoading) return <LoadingBlock />;
  if (perf.isError) return <ErrorBlock error={perf.error} />;
  if (health.isError) return <ErrorBlock error={health.error} />;

  const p = perf.data ?? null;
  const d = health.data ?? null;
  const hasLatency = p !== null && (p.duration_ms !== null || p.time_to_first_token_ms !== null);
  const maxErrors = d ? Math.max(...d.errors.map((e) => e.request_count), 1) : 1;

  return (
    <div className="space-y-8">
      <section>
        <h2 className="mb-3 text-sm font-medium text-zinc-400">请求性能</h2>
        {p && hasLatency ? (
          <div className="flex flex-col gap-6 lg:flex-row">
            <LatencyPanel title="请求耗时(duration)" stats={p.duration_ms} />
            <LatencyPanel
              title="首字延迟(TTFT)"
              stats={p.time_to_first_token_ms}
              note="TTFT 仅统计有该字段的请求,空值已排除,样本数见上。"
            />
          </div>
        ) : (
          <EmptyBlock text="数据库中暂无耗时样本" />
        )}
      </section>

      <section>
        <h2 className="mb-3 text-sm font-medium text-zinc-400">重试与错误分布</h2>
        {!d ? (
          <EmptyBlock />
        ) : d.request_count === 0 ? (
          <EmptyBlock text="暂无请求记录" />
        ) : (
          <div className="space-y-6">
            <div className="grid grid-cols-2 gap-4 lg:grid-cols-3">
              <HealthCard
                value={d.request_count.toLocaleString("zh-CN")}
                label="模型请求总数"
              />
              <HealthCard
                value={`${d.requests_with_retries.toLocaleString("zh-CN")}`}
                label="含重试的请求"
              />
              <HealthCard
                value={d.total_retries.toLocaleString("zh-CN")}
                label="重试总次数"
              />
              <HealthCard
                value={d.errored_requests.toLocaleString("zh-CN")}
                label="出错请求"
              />
              <HealthCard
                value={d.cancelled_by_user.toLocaleString("zh-CN")}
                label="用户取消"
              />
              <HealthCard
                value={d.context_exceeded.toLocaleString("zh-CN")}
                label="上下文超限"
              />
            </div>

            {d.errors.length === 0 ? (
              <div className="rounded-xl border border-emerald-900/50 bg-emerald-950/20 px-5 py-4">
                <p className="text-sm text-emerald-300">当前数据库没有任何错误记录 ✓</p>
              </div>
            ) : (
              <div className="space-y-3 rounded-xl border border-zinc-800/80 bg-zinc-900 p-5">
                {d.errors.map((e) => (
                  <div key={`${e.source}/${e.error_type}/${e.error_code ?? ""}`}>
                    <div className="mb-1 flex items-baseline justify-between gap-3 text-xs">
                      <span className="flex items-baseline gap-2 font-mono text-zinc-300">
                        <span className="rounded bg-zinc-800 px-1.5 py-0.5 text-[11px] text-zinc-500">
                          {e.source}
                        </span>
                        {e.error_type}
                        {e.error_code !== null && (
                          <span className="text-zinc-500">{e.error_code}</span>
                        )}
                      </span>
                      <span className="tabular-nums text-zinc-400">
                        {e.request_count.toLocaleString("zh-CN")} 次
                      </span>
                    </div>
                    <div className="h-2 rounded bg-zinc-800">
                      <div
                        className="h-2 rounded bg-rose-500/70"
                        style={{ width: `${Math.max((e.request_count / maxErrors) * 100, 2)}%` }}
                      />
                    </div>
                  </div>
                ))}
              </div>
            )}

            <p className="text-xs text-zinc-600">
              口径:重试按请求粒度计数(retry_count &gt; 0 视为含重试);错误按 error_type
              非空计,同类错误合并展示。当前数据库累计 {d.request_count.toLocaleString("zh-CN")}{" "}
              次请求。
            </p>
          </div>
        )}
      </section>
    </div>
  );
}
