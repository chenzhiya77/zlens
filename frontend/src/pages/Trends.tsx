import { useQuery } from "@tanstack/react-query";
import { useMemo, useState } from "react";

import EChart from "../components/EChart";
import Segmented from "../components/Segmented";
import { EmptyBlock, ErrorBlock, LoadingBlock } from "../components/states";
import { fetchTrends } from "../lib/api";
import { darkBase, modelColor } from "../lib/chart";
import { formatCost, formatTokens } from "../lib/format";
import type { EChartsOption } from "echarts";

const RANGES = [
  { key: "7d", label: "近 7 日", days: 7 },
  { key: "30d", label: "近 30 日", days: 30 },
  { key: "all", label: "全部", days: null },
] as const;

const METRICS = [
  { key: "total_tokens", label: "总 Token" },
  { key: "request_count", label: "请求次数" },
  { key: "input_tokens", label: "输入" },
  { key: "output_tokens", label: "输出" },
  { key: "cache_read_tokens", label: "缓存读" },
] as const;

type RangeKey = (typeof RANGES)[number]["key"];
type MetricKey = (typeof METRICS)[number]["key"];
type HeatMode = "daily" | "weekly" | "cumulative";

function weekStart(day: string): string {
  const d = new Date(`${day}T00:00:00`);
  const offset = (d.getDay() + 6) % 7; // Monday = 0
  d.setDate(d.getDate() - offset);
  return d.toISOString().slice(0, 10);
}

export default function Trends() {
  const query = useQuery({ queryKey: ["trends"], queryFn: fetchTrends });
  const [range, setRange] = useState<RangeKey>("30d");
  const [metric, setMetric] = useState<MetricKey>("total_tokens");
  const [heatMode, setHeatMode] = useState<HeatMode>("daily");

  const data = query.data;

  const view = useMemo(() => {
    if (!data) return null;
    const days = data.days;
    if (days.length === 0) return { days: [], models: [], byModelDay: new Map<string, number>() };
    const cutoffDays = RANGES.find((r) => r.key === range)?.days ?? null;
    const shown = cutoffDays === null ? days : days.slice(-cutoffDays);
    const shownKeys = new Set(shown.map((d) => d.day));

    const models = [...new Set(data.by_model.map((r) => r.model_id))];
    const byModelDay = new Map<string, number>();
    for (const row of data.by_model) {
      if (shownKeys.has(row.day)) byModelDay.set(`${row.model_id}|${row.day}`, row[metric]);
    }
    return { days: shown, models, byModelDay };
  }, [data, range, metric]);

  if (query.isLoading) return <LoadingBlock />;
  if (query.isError) return <ErrorBlock error={query.error} />;
  if (!view || view.days.length === 0) return <EmptyBlock text="该范围内暂无用量记录" />;

  const dayLabels = view.days.map((d) => d.day);

  const lineOption: EChartsOption = {
    ...darkBase(),
    legend: { ...darkBase().legend, top: 0 },
    tooltip: { ...darkBase().tooltip, trigger: "axis" },
    xAxis: { type: "category", data: dayLabels, axisLine: { lineStyle: { color: "#3f3f46" } } },
    yAxis: { type: "value", splitLine: { lineStyle: { color: "#27272a" } } },
    series: view.models.map((model, index) => ({
      name: model,
      type: "line" as const,
      smooth: true,
      showSymbol: view.days.length <= 31,
      lineStyle: { width: 2, color: modelColor(index) },
      itemStyle: { color: modelColor(index) },
      data: view.days.map((d) => view.byModelDay.get(`${model}|${d.day}`) ?? 0),
    })),
  };

  // --- activity chart: daily heatmap / weekly bars / cumulative line ---
  let activityOption: EChartsOption;
  if (heatMode === "daily") {
    const values = view.days.map((d) => d.total_tokens);
    activityOption = {
      ...darkBase(),
      visualMap: {
        min: 0,
        max: Math.max(...values, 1),
        calculable: false,
        orient: "horizontal",
        left: "center",
        bottom: 0,
        textStyle: { color: "#a1a1aa" },
        inRange: { color: ["#18181b", "#1d4ed8", "#60a5fa"] },
      },
      calendar: {
        range: [dayLabels[0]!, dayLabels[dayLabels.length - 1]!],
        cellSize: ["auto", 16],
        left: 40,
        right: 16,
        top: 16,
        itemStyle: { color: "#18181b", borderColor: "#09090b" },
        yearLabel: { show: false },
        monthLabel: { color: "#a1a1aa" },
        dayLabel: { color: "#71717a", firstDay: 1 },
      },
      series: [
        {
          type: "heatmap",
          coordinateSystem: "calendar",
          data: view.days.map((d) => [d.day, d.total_tokens]),
        },
      ],
    };
  } else if (heatMode === "weekly") {
    const weeks = new Map<string, number>();
    for (const d of view.days) {
      weeks.set(weekStart(d.day), (weeks.get(weekStart(d.day)) ?? 0) + d.total_tokens);
    }
    const entries = [...weeks.entries()];
    activityOption = {
      ...darkBase(),
      xAxis: {
        type: "category",
        data: entries.map(([w]) => w),
        axisLine: { lineStyle: { color: "#3f3f46" } },
      },
      yAxis: { type: "value", splitLine: { lineStyle: { color: "#27272a" } } },
      series: [
        {
          type: "bar",
          itemStyle: { color: "#60a5fa" },
          data: entries.map(([, v]) => v),
        },
      ],
    };
  } else {
    let running = 0;
    const cumulative = view.days.map((d) => {
      running += d.total_tokens;
      return running;
    });
    activityOption = {
      ...darkBase(),
      tooltip: { ...darkBase().tooltip, trigger: "axis" },
      xAxis: {
        type: "category",
        data: dayLabels,
        axisLine: { lineStyle: { color: "#3f3f46" } },
      },
      yAxis: { type: "value", splitLine: { lineStyle: { color: "#27272a" } } },
      series: [
        {
          type: "line",
          smooth: true,
          showSymbol: false,
          areaStyle: { color: "rgba(96,165,250,0.15)" },
          lineStyle: { color: "#60a5fa", width: 2 },
          data: cumulative,
        },
      ],
    };
  }

  const lastDay = view.days[view.days.length - 1]!;

  return (
    <div className="space-y-8">
      <div className="flex items-center justify-between">
        <Segmented value={range} options={RANGES.map(({ key, label }) => ({ key, label }))} onChange={setRange} />
        <Segmented value={metric} options={METRICS.map(({ key, label }) => ({ key, label }))} onChange={setMetric} />
      </div>

      <section>
        <h2 className="mb-3 text-sm font-medium text-zinc-400">
          每日趋势 — {METRICS.find((m) => m.key === metric)?.label}(按模型)
        </h2>
        <div className="rounded-xl border border-zinc-800/80 bg-zinc-900/40 p-4">
          <EChart option={lineOption} height={300} />
        </div>
      </section>

      <section>
        <div className="mb-3 flex items-center justify-between">
          <h2 className="text-sm font-medium text-zinc-400">Token 活动</h2>
          <Segmented
            value={heatMode}
            options={[
              { key: "daily", label: "每日" },
              { key: "weekly", label: "每周" },
              { key: "cumulative", label: "累计" },
            ]}
            onChange={setHeatMode}
          />
        </div>
        <div className="rounded-xl border border-zinc-800/80 bg-zinc-900/40 p-4">
          <EChart option={activityOption} height={heatMode === "daily" ? 200 : 260} />
        </div>
        <p className="mt-2 text-xs text-zinc-600">
          截至最近一天 {lastDay.day}:{formatTokens(lastDay.total_tokens)} tokens /{" "}
          {lastDay.request_count.toLocaleString("zh-CN")} 次请求
          {lastDay.estimated_cost_usd !== null && ` / ${formatCost(lastDay.estimated_cost_usd)}`}
        </p>
      </section>
    </div>
  );
}
