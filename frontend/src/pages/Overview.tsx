import { useQuery } from "@tanstack/react-query";
import { useState } from "react";

import ModelTable from "../components/ModelTable";
import { ErrorBlock, LoadingBlock } from "../components/states";
import { displayName, getAliases, parseModelKey, setAlias } from "../lib/alias";
import { fetchMeta, fetchOverview } from "../lib/api";
import { formatDateTime, formatCost, formatTokens } from "../lib/format";

function Kpi({
  value,
  label,
  hint,
}: {
  value: string;
  label: string;
  hint?: string;
}) {
  return (
    <div className="bg-zinc-900 px-6 py-4">
      <div className="flex items-baseline gap-2">
        <span className="whitespace-nowrap text-3xl font-semibold tracking-tight tabular-nums">
          {value}
        </span>
        {hint && <span className="whitespace-nowrap text-xs text-zinc-500">{hint}</span>}
      </div>
      <p className="mt-1 text-sm text-zinc-500">{label}</p>
    </div>
  );
}

export default function Overview() {
  const meta = useQuery({ queryKey: ["meta"], queryFn: fetchMeta });
  const overview = useQuery({ queryKey: ["overview"], queryFn: fetchOverview });
  const [aliases, setAliasesState] = useState<Record<string, string>>(() => getAliases());

  const handleAlias = (key: string, value: string) => {
    setAlias(key, value, key.split("|")[2] ?? "");
    setAliasesState(getAliases());
  };

  if (meta.isLoading || overview.isLoading) return <LoadingBlock />;
  if (meta.isError) return <ErrorBlock error={meta.error} />;
  if (overview.isError) return <ErrorBlock error={overview.error} />;
  if (!meta.data || !overview.data) return null;

  const { data: m } = meta;
  const { data: o } = overview;

  return (
    <div className="@container space-y-8">
      <p className="text-xs text-zinc-500">
        数据源 {m.source_id}
        <span className="mx-2 text-zinc-700">|</span>
        数据范围 {formatDateTime(m.first_request_at)} → {formatDateTime(m.last_request_at)}
        <span className="mx-2 text-zinc-700">|</span>
        统计生成于 {formatDateTime(m.generated_at)}
      </p>

      {/* KPI 条按自身宽度分档:≥900px 一行六格 → 3+3 两行 → 2+2+2 三行。用容器查询而不是
          auto-fit,是因为六格挤不进时 auto-fit 会留下被拉宽的孤格;分档保证每行都排满。
          分隔线由 1px 间隙露出底色画成,折几行都对(表格那处不能折行,才用横滚壳)。 */}
      <div className="grid grid-cols-6 gap-px rounded-xl border border-zinc-800/80 bg-zinc-800/80 @max-[900px]:grid-cols-3 @max-[560px]:grid-cols-2">
        <Kpi value={o.request_count.toLocaleString("zh-CN")} label="模型请求次数" />
        <Kpi value={formatTokens(o.total_tokens)} label="累计 Token (tokens)" />
        <Kpi
          value={formatTokens(o.cache_read_tokens)}
          label="缓存读 Token (tokens)"
          hint="省钱大户"
        />
        <Kpi value={formatTokens(o.output_tokens)} label="输出 Token (tokens)" />
        <Kpi
          value={formatCost(o.estimated_cost)}
          label="按量消耗 (CNY)"
          hint={o.estimated_cost === null ? "未计价" : "估算"}
        />
        <Kpi
          value={formatCost(o.buyout_total)}
          label="买断支出 (CNY)"
          hint={o.buyout_total === 0 ? "未填" : "已付清"}
        />
      </div>

      {m.unpriced_models.length > 0 && (
        <div className="rounded-lg border border-zinc-800 bg-zinc-900 px-5 py-3">
          <p className="text-sm text-zinc-400">
            未计价渠道(价格表中没有,仅显示 token):
            {m.unpriced_models.map((key) => {
              const channel = parseModelKey(key);
              return (
                <span
                  key={key}
                  title={key}
                  className="ml-2 inline-flex items-center gap-1.5 rounded bg-zinc-800 px-2 py-0.5 font-mono text-xs text-zinc-300"
                >
                  <span className="text-[10px] text-zinc-500">
                    {channel ? channel.source : "旧键"}
                  </span>
                  {channel
                    ? displayName(aliases, channel.source, channel.providerId, channel.modelId)
                    : key}
                </span>
              );
            })}
          </p>
        </div>
      )}

      <section>
        <h2 className="mb-3 text-sm font-medium text-zinc-400">按模型明细</h2>
        <ModelTable models={o.by_model} aliases={aliases} onAlias={handleAlias} />
      </section>
    </div>
  );
}
