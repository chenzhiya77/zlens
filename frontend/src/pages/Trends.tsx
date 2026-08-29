import { useQuery } from "@tanstack/react-query";
import { useMemo, useState } from "react";

import EChart from "../components/EChart";
import Segmented from "../components/Segmented";
import { EmptyBlock, ErrorBlock, LoadingBlock } from "../components/states";
import { fetchTrends } from "../lib/api";
import { disambiguate, displayName, getAliases } from "../lib/alias";
import { chartBase, chartColors, modelColor } from "../lib/chart";
import { formatCost, formatTokens } from "../lib/format";
import { useTheme } from "../lib/theme";
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

// Legend chips default to the top-N models by volume; the rest start dimmed.
const TOP_MODELS = 8;

function weekStart(day: string): string {
  const d = new Date(`${day}T00:00:00`);
  const offset = (d.getDay() + 6) % 7; // Monday = 0
  d.setDate(d.getDate() - offset);
  return d.toISOString().slice(0, 10);
}

interface Triple {
  source: string;
  provider_id: string;
  model_id: string;
}

// Series split per provider: same-named models from different routings stay
// separate lines and can carry distinct aliases.
const seriesKey = (r: Triple) => `${r.source}/${r.provider_id}/${r.model_id}`;

export default function Trends() {
  const query = useQuery({ queryKey: ["trends"], queryFn: () => fetchTrends() });
  const [range, setRange] = useState<RangeKey>("30d");
  const [metric, setMetric] = useState<MetricKey>("total_tokens");
  const [heatMode, setHeatMode] = useState<HeatMode>("daily");
  const [enabled, setEnabled] = useState<Set<string> | null>(null);
  const { mode } = useTheme();

  const data = query.data;

  const view = useMemo(() => {
    if (!data) return null;
    const days = data.days;
    if (days.length === 0) {
      return {
        days: [] as typeof days,
        models: [] as string[],
        byModelDay: new Map<string, number>(),
        tripleOf: new Map<string, Triple>(),
      };
    }
    const cutoffDays = RANGES.find((r) => r.key === range)?.days ?? null;
    const shown = cutoffDays === null ? days : days.slice(-cutoffDays);
    const shownKeys = new Set(shown.map((d) => d.day));

    const tripleOf = new Map<string, Triple>();
    for (const row of data.by_model) {
      tripleOf.set(seriesKey(row), {
        source: row.source,
        provider_id: row.provider_id,
        model_id: row.model_id,
      });
    }
    const models = [...tripleOf.keys()];
    const byModelDay = new Map<string, number>();
    for (const row of data.by_model) {
      if (shownKeys.has(row.day)) {
        byModelDay.set(`${seriesKey(row)}|${row.day}`, row[metric]);
      }
    }
    return { days: shown, models, byModelDay, tripleOf };
  }, [data, range, metric]);

  const ranked = useMemo(() => {
    if (!view) return [];
    const total = (model: string) => {
      let sum = 0;
      for (const day of view.days) sum += view.byModelDay.get(`${model}|${day.day}`) ?? 0;
      return sum;
    };
    return [...view.models].sort((a, b) => total(b) - total(a));
  }, [view]);

  if (query.isLoading) return <LoadingBlock />;
  if (query.isError) return <ErrorBlock error={query.error} />;
  if (!view || view.days.length === 0) return <EmptyBlock text="该范围内暂无用量记录" />;

  const dayLabels = view.days.map((d) => d.day);
  const colors = chartColors(mode);
  const colorIndex = new Map(view.models.map((model, index) => [model, index]));

  const aliases = getAliases();
  const names = disambiguate(
    view.models.map((key) => {
      const t = view.tripleOf.get(key)!;
      return displayName(aliases, t.source, t.provider_id, t.model_id);
    }),
    view.models.map((key) => view.tripleOf.get(key)!.provider_id),
  );
  const labelOf = new Map(view.models.map((key, index) => [key, names[index]!]));

  // The legend lives outside the canvas as clickable chips; with many models
  // only the top-N by volume start enabled, the rest are a click away.
  const visible = enabled ?? new Set(ranked.slice(0, TOP_MODELS));
  const toggleModel = (model: string) => {
    const next = new Set(visible);
    if (next.has(model)) next.delete(model);
    else next.add(model);
    setEnabled(next);
  };

  const lineOption: EChartsOption = {
    ...chartBase(mode),
    // chartBase() carries legend text styles for the donut pages; here the
    // legend is the HTML chip row, so the in-canvas one must stay off.
    legend: { show: false },
    tooltip: { ...chartBase(mode).tooltip, trigger: "axis" },
    xAxis: {
      type: "category",
      data: dayLabels,
      axisLine: { lineStyle: { color: colors.axisLine } },
    },
    yAxis: { type: "value", splitLine: { lineStyle: { color: colors.splitLine } } },
    series: view.models
      .filter((model) => visible.has(model))
      .map((model) => ({
        name: labelOf.get(model)!,
        type: "line" as const,
        smooth: true,
        showSymbol: view.days.length <= 31,
        lineStyle: { width: 2, color: modelColor(colorIndex.get(model)!) },
        itemStyle: { color: modelColor(colorIndex.get(model)!) },
        data: view.days.map((d) => view.byModelDay.get(`${model}|${d.day}`) ?? 0),
      })),
  };

  // --- activity chart: daily heatmap / weekly bars / cumulative line ---
  let activityOption: EChartsOption;
  if (heatMode === "daily") {
    const values = view.days.map((d) => d.total_tokens);
    activityOption = {
      ...chartBase(mode),
      visualMap: {
        min: 0,
        max: Math.max(...values, 1),
        calculable: false,
        orient: "horizontal",
        left: "center",
        bottom: 0,
        textStyle: { color: colors.axisText },
        inRange: { color: colors.heatRange },
      },
      calendar: {
        range: [dayLabels[0]!, dayLabels[dayLabels.length - 1]!],
        cellSize: ["auto", 16],
        left: 40,
        right: 16,
        top: 16,
        itemStyle: { color: colors.heatRange[0], borderColor: colors.page },
        yearLabel: { show: false },
        monthLabel: { color: colors.axisText },
        dayLabel: { color: colors.axisText, firstDay: 1 },
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
      ...chartBase(mode),
      xAxis: {
        type: "category",
        data: entries.map(([w]) => w),
        axisLine: { lineStyle: { color: colors.axisLine } },
      },
      yAxis: { type: "value", splitLine: { lineStyle: { color: colors.splitLine } } },
      series: [
        {
          type: "bar",
          itemStyle: { color: colors.accent },
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
      ...chartBase(mode),
      tooltip: { ...chartBase(mode).tooltip, trigger: "axis" },
      xAxis: {
        type: "category",
        data: dayLabels,
        axisLine: { lineStyle: { color: colors.axisLine } },
      },
      yAxis: { type: "value", splitLine: { lineStyle: { color: colors.splitLine } } },
      series: [
        {
          type: "line",
          smooth: true,
          showSymbol: false,
          areaStyle: { color: colors.accentArea },
          lineStyle: { color: colors.accent, width: 2 },
          data: cumulative,
        },
      ],
    };
  }

  const lastDay = view.days[view.days.length - 1]!;

  return (
    <div className="space-y-8">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <Segmented value={range} options={RANGES.map(({ key, label }) => ({ key, label }))} onChange={setRange} />
        <Segmented value={metric} options={METRICS.map(({ key, label }) => ({ key, label }))} onChange={setMetric} />
      </div>

      <section>
        <h2 className="mb-3 text-sm font-medium text-zinc-400">
          每日趋势 — {METRICS.find((m) => m.key === metric)?.label}(按模型)
        </h2>
        <div className="rounded-xl border border-zinc-800/80 bg-zinc-900 p-4">
          <EChart option={lineOption} height={300} />
          <div className="mt-3 flex flex-wrap gap-1.5 border-t border-zinc-800/60 pt-3">
            {ranked.map((model) => {
              const on = visible.has(model);
              return (
                <button
                  key={model}
                  type="button"
                  onClick={() => toggleModel(model)}
                  title={view.tripleOf.get(model)!.model_id}
                  className={`flex items-center gap-1.5 rounded-full border px-2.5 py-1 font-mono text-xs transition ${
                    on
                      ? "border-zinc-700 bg-zinc-800/60 text-zinc-200"
                      : "border-zinc-800 text-zinc-500 opacity-50 hover:opacity-80"
                  }`}
                >
                  <span
                    className="h-2 w-2 rounded-full"
                    style={{ backgroundColor: modelColor(colorIndex.get(model)!) }}
                  />
                  {labelOf.get(model)}
                </button>
              );
            })}
          </div>
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
        <div className="rounded-xl border border-zinc-800/80 bg-zinc-900 p-4">
          <EChart option={activityOption} height={heatMode === "daily" ? 200 : 260} />
        </div>
        <p className="mt-2 text-xs text-zinc-600">
          截至最近一天 {lastDay.day}:{formatTokens(lastDay.total_tokens)} tokens /{" "}
          {lastDay.request_count.toLocaleString("zh-CN")} 次请求
          {lastDay.estimated_cost !== null && ` / ${formatCost(lastDay.estimated_cost)}`}
        </p>
      </section>
    </div>
  );
}
