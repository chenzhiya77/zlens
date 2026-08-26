import { useQuery } from "@tanstack/react-query";

import EChart from "../components/EChart";
import { EmptyBlock, ErrorBlock, LoadingBlock } from "../components/states";
import { fetchProjects } from "../lib/api";
import { MODEL_COLORS, darkBase } from "../lib/chart";
import { formatCost, formatTokens } from "../lib/format";
import type { EChartsOption } from "echarts";

export default function Projects() {
  const query = useQuery({ queryKey: ["projects"], queryFn: fetchProjects });

  if (query.isLoading) return <LoadingBlock />;
  if (query.isError) return <ErrorBlock error={query.error} />;
  const projects = query.data?.projects ?? [];
  if (projects.length === 0) return <EmptyBlock text="暂无项目用量记录" />;

  const donutOption: EChartsOption = {
    ...darkBase(),
    tooltip: { ...darkBase().tooltip, trigger: "item" },
    legend: { ...darkBase().legend, type: "scroll", bottom: 0, left: "center" },
    series: [
      {
        type: "pie",
        radius: ["48%", "74%"],
        center: ["50%", "46%"],
        itemStyle: { borderColor: "#09090b", borderWidth: 2 },
        label: { show: false },
        data: projects.map((p, index) => ({
          name: p.directory,
          value: p.total_tokens,
          itemStyle: { color: MODEL_COLORS[index % MODEL_COLORS.length] },
        })),
      },
    ],
  };

  return (
    <div className="space-y-8">
      <section>
        <h2 className="mb-3 text-sm font-medium text-zinc-400">项目用量占比(按总 Token)</h2>
        <div className="rounded-xl border border-zinc-800/80 bg-zinc-900/40 p-4">
          <EChart option={donutOption} height={320} />
        </div>
      </section>

      <section>
        <h2 className="mb-3 text-sm font-medium text-zinc-400">项目明细</h2>
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-zinc-800 text-left text-xs text-zinc-500">
              <th className="py-2 pr-4 font-medium">项目目录</th>
              <th className="py-2 pr-4 font-medium">代表会话</th>
              <th className="py-2 pr-4 text-right font-medium">请求</th>
              <th className="py-2 pr-4 text-right font-medium">输入</th>
              <th className="py-2 pr-4 text-right font-medium">输出</th>
              <th className="py-2 pr-4 text-right font-medium">缓存读</th>
              <th className="py-2 pr-4 text-right font-medium">总计</th>
              <th className="py-2 text-right font-medium">成本(估算)</th>
            </tr>
          </thead>
          <tbody>
            {projects.map((p) => (
              <tr key={p.directory} className="border-b border-zinc-900">
                <td className="max-w-72 truncate py-2 pr-4 font-mono text-xs text-zinc-300">
                  {p.directory}
                </td>
                <td className="max-w-48 truncate py-2 pr-4 text-xs text-zinc-400">{p.title}</td>
                <td className="py-2 pr-4 text-right tabular-nums">
                  {p.request_count.toLocaleString("zh-CN")}
                </td>
                <td className="py-2 pr-4 text-right tabular-nums">{formatTokens(p.input_tokens)}</td>
                <td className="py-2 pr-4 text-right tabular-nums">{formatTokens(p.output_tokens)}</td>
                <td className="py-2 pr-4 text-right tabular-nums">
                  {formatTokens(p.cache_read_tokens)}
                </td>
                <td className="py-2 pr-4 text-right tabular-nums font-medium">
                  {formatTokens(p.total_tokens)}
                </td>
                <td className="py-2 text-right tabular-nums">
                  {p.estimated_cost_usd === null ? (
                    <span className="rounded bg-zinc-800 px-1.5 py-0.5 text-xs text-zinc-400">未计价</span>
                  ) : (
                    formatCost(p.estimated_cost_usd)
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>
    </div>
  );
}
