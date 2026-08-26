import { useQuery } from "@tanstack/react-query";

import EChart from "../components/EChart";
import ModelTable from "../components/ModelTable";
import { EmptyBlock, ErrorBlock, LoadingBlock } from "../components/states";
import { fetchOverview } from "../lib/api";
import { darkBase, modelColor } from "../lib/chart";
import { formatTokens } from "../lib/format";
import type { EChartsOption } from "echarts";

export default function Models() {
  const query = useQuery({ queryKey: ["overview"], queryFn: fetchOverview });

  if (query.isLoading) return <LoadingBlock />;
  if (query.isError) return <ErrorBlock error={query.error} />;
  const models = query.data?.by_model ?? [];
  if (models.length === 0) return <EmptyBlock text="暂无模型用量记录" />;

  const grandTotal = models.reduce((sum, m) => sum + m.total_tokens, 0);
  const donutOption: EChartsOption = {
    ...darkBase(),
    tooltip: {
      ...darkBase().tooltip,
      trigger: "item",
      formatter: (params) => {
        const p = Array.isArray(params) ? params[0]! : params;
        const name = String(p.name);
        const value = Number(p.value);
        const pct = grandTotal > 0 ? ((value / grandTotal) * 100).toFixed(1) : "0";
        return `${name}<br/>${formatTokens(value)} tokens(${pct}%)`;
      },
    },
    legend: {
      orient: "vertical",
      right: 8,
      top: "middle",
      textStyle: { color: "#d4d4d8" },
      formatter: (name) => {
        const m = models.find((row) => row.model_id === name);
        if (!m) return name;
        const pct = grandTotal > 0 ? ((m.total_tokens / grandTotal) * 100).toFixed(1) : "0";
        return `${name}  ${pct}%  ${formatTokens(m.total_tokens)}`;
      },
    },
    series: [
      {
        type: "pie",
        radius: ["48%", "74%"],
        center: ["36%", "50%"],
        itemStyle: { borderColor: "#09090b", borderWidth: 2 },
        label: { show: false },
        data: models.map((m, index) => ({
          name: m.model_id,
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
        <div className="rounded-xl border border-zinc-800/80 bg-zinc-900/40 p-4">
          <EChart option={donutOption} height={300} />
        </div>
      </section>

      <section>
        <h2 className="mb-3 text-sm font-medium text-zinc-400">模型排行</h2>
        <ModelTable models={models} />
      </section>
    </div>
  );
}
