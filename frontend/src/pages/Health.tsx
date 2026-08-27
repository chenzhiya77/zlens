import { useQuery } from "@tanstack/react-query";

import { EmptyBlock, ErrorBlock, LoadingBlock } from "../components/states";
import { fetchHealth } from "../lib/api";

function HealthCard({ value, label }: { value: string; label: string }) {
  return (
    <div className="rounded-xl border border-zinc-800/80 bg-zinc-900/40 px-5 py-4">
      <div className="text-2xl font-semibold tabular-nums">{value}</div>
      <p className="mt-1 text-xs text-zinc-500">{label}</p>
    </div>
  );
}

export default function Health() {
  const query = useQuery({ queryKey: ["health"], queryFn: fetchHealth });

  if (query.isLoading) return <LoadingBlock />;
  if (query.isError) return <ErrorBlock error={query.error} />;
  const data = query.data;
  if (!data) return <EmptyBlock />;
  if (data.request_count === 0) return <EmptyBlock text="暂无请求记录" />;

  const maxErrors = Math.max(...data.errors.map((e) => e.request_count), 1);

  return (
    <div className="space-y-8">
      <div className="grid grid-cols-2 gap-4 lg:grid-cols-3">
        <HealthCard value={data.request_count.toLocaleString("zh-CN")} label="模型请求总数" />
        <HealthCard
          value={`${data.requests_with_retries.toLocaleString("zh-CN")}`}
          label="含重试的请求"
        />
        <HealthCard value={data.total_retries.toLocaleString("zh-CN")} label="重试总次数" />
        <HealthCard value={data.errored_requests.toLocaleString("zh-CN")} label="出错请求" />
        <HealthCard value={data.cancelled_by_user.toLocaleString("zh-CN")} label="用户取消" />
        <HealthCard value={data.context_exceeded.toLocaleString("zh-CN")} label="上下文超限" />
      </div>

      <section>
        <h2 className="mb-3 text-sm font-medium text-zinc-400">错误分布</h2>
        {data.errors.length === 0 ? (
          <div className="rounded-xl border border-emerald-900/50 bg-emerald-950/20 px-5 py-4">
            <p className="text-sm text-emerald-300">当前数据库没有任何错误记录 ✓</p>
          </div>
        ) : (
          <div className="space-y-3 rounded-xl border border-zinc-800/80 bg-zinc-900/40 p-5">
            {data.errors.map((e) => (
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
      </section>

      <p className="text-xs text-zinc-600">
        口径:重试按请求粒度计数(retry_count &gt; 0 视为含重试);错误按 error_type 非空计,
        同类错误合并展示。当前数据库累计 {data.request_count.toLocaleString("zh-CN")} 次请求。
      </p>
    </div>
  );
}
