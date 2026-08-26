import { useQuery } from "@tanstack/react-query";

import { EmptyBlock, ErrorBlock, LoadingBlock } from "../components/states";
import { fetchPerformance } from "../lib/api";
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
    <div className="flex-1 rounded-xl border border-zinc-800/80 bg-zinc-900/40 p-5">
      <div className="mb-4 flex items-baseline justify-between">
        <h2 className="text-sm font-medium text-zinc-300">{title}</h2>
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

export default function Performance() {
  const query = useQuery({ queryKey: ["performance"], queryFn: fetchPerformance });

  if (query.isLoading) return <LoadingBlock />;
  if (query.isError) return <ErrorBlock error={query.error} />;
  const data = query.data;
  if (!data) return <EmptyBlock />;

  const hasAny = data.duration_ms !== null || data.time_to_first_token_ms !== null;
  if (!hasAny) return <EmptyBlock text="数据库中暂无耗时样本" />;

  return (
    <div className="flex flex-col gap-6 lg:flex-row">
      <LatencyPanel title="请求耗时(duration)" stats={data.duration_ms} />
      <LatencyPanel
        title="首字延迟(TTFT)"
        stats={data.time_to_first_token_ms}
        note="TTFT 仅统计有该字段的请求,空值已排除,样本数见上。"
      />
    </div>
  );
}
