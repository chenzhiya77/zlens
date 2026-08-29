import { useQuery } from "@tanstack/react-query";

import EChart from "../components/EChart";
import ModelTable from "../components/ModelTable";
import { EmptyBlock, ErrorBlock, LoadingBlock } from "../components/states";
import { fetchOverview } from "../lib/api";
import { disambiguate, displayName, getAliases } from "../lib/alias";
import { chartBase, chartColors, modelColor } from "../lib/chart";
import { formatTokens } from "../lib/format";
import { useTheme } from "../lib/theme";
import type { EChartsOption } from "echarts";

export default function Models() {
  const query = useQuery({ queryKey: ["overview"], queryFn: () => fetchOverview() });
  const { mode } = useTheme();
  const colors = chartColors(mode);

  if (query.isLoading) return <LoadingBlock />;
  if (query.isError) return <ErrorBlock error={query.error} />;
  const models = query.data?.by_model ?? [];
  if (models.length === 0) return <EmptyBlock text="暂无模型用量记录" />;

  const grandTotal = models.reduce((sum, m) => sum + m.total_tokens, 0);
  const aliases = getAliases();
  const names = disambiguate(
    models.map((m) => displayName(aliases, m.source, m.provider_id, m.model_id)),
    models.map((m) => m.provider_id),
  );
  const donutOption: EChartsOption = {
    ...chartBase(mode),
    tooltip: {
      ...chartBase(mode).tooltip,
      trigger: "item",
      formatter: (params) => {
        const p = Array.isArray(params) ? params[0]! : params;
        const name = String(p.name);
        const value = Number(p.value);
        const pct = grandTotal > 0 ? ((value / grandTotal) * 100).toFixed(1) : "0";
        return `${name}<br/>${formatTokens(value)} tokens(${pct}%)`;
      },
    },
    legend: { show: false },
    series: [
      {
        type: "pie",
        radius: ["48%", "74%"],
        center: ["50%", "50%"],
        itemStyle: { borderColor: colors.page, borderWidth: 2 },
        label: { show: false },
        data: models.map((m, index) => ({
          name: names[index]!,
          value: m.total_tokens,
          itemStyle: { color: modelColor(index) },
        })),
      },
    ],
  };

  return (
    <div className="space-y-8">
      <section>
        <h2 className="mb-3 text-sm font-medium text-zinc-400">模型用量占比(按总 Token)</h2>
        <div className="rounded-xl border border-zinc-800/80 bg-zinc-900 p-4">
          <EChart option={donutOption} height={260} />
          <div className="mt-3 grid grid-cols-1 gap-x-8 gap-y-1.5 border-t border-zinc-800/60 pt-3 sm:grid-cols-2">
            {models.map((m, index) => (
              <div key={`${m.provider_id}/${m.model_id}`} className="flex items-center gap-2 text-xs">
                <span
                  className="h-2 w-2 shrink-0 rounded-full"
                  style={{ backgroundColor: modelColor(index) }}
                />
                <span className="truncate font-mono text-zinc-300" title={m.model_id}>
                  {names[index]!}
                </span>
                <span className="ml-auto shrink-0 tabular-nums text-zinc-400">
                  {grandTotal > 0 ? ((m.total_tokens / grandTotal) * 100).toFixed(1) : "0"}%
                </span>
                <span className="w-20 shrink-0 text-right tabular-nums text-zinc-500">
                  {formatTokens(m.total_tokens)}
                </span>
              </div>
            ))}
          </div>
        </div>
      </section>

      <section>
        <h2 className="mb-3 text-sm font-medium text-zinc-400">模型排行</h2>
        <ModelTable models={models} aliases={aliases} />
      </section>
    </div>
  );
}
