import type { EChartsOption } from "echarts";

import type { ThemeMode } from "./theme";

// ECharts paints on a canvas, so it can't read the CSS variables that flip the
// Tailwind palette; pages pass the active mode in and get matching hex values.
// The two ramps mirror the zinc scale in index.css (page < surface < border).
export interface ChartColors {
  axisText: string;
  axisLine: string;
  splitLine: string;
  surface: string;
  page: string;
  border: string;
  legendText: string;
  tooltipText: string;
  accent: string;
  accentArea: string;
  heatRange: [string, string, string];
}

export function chartColors(mode: ThemeMode): ChartColors {
  if (mode === "light") {
    return {
      axisText: "#52525b",
      axisLine: "#d4d4d8",
      splitLine: "#e4e4e7",
      surface: "#ffffff",
      page: "#fafafa",
      border: "#d4d4d8",
      legendText: "#27272a",
      tooltipText: "#27272a",
      accent: "#2563eb",
      accentArea: "rgba(37, 99, 235, 0.10)",
      heatRange: ["#e4e4e7", "#93c5fd", "#1d4ed8"],
    };
  }
  return {
    axisText: "#a1a1aa",
    axisLine: "#3f4650",
    splitLine: "#262b31",
    surface: "#16191d",
    page: "#0f1215",
    border: "#3f4650",
    legendText: "#d4d4d8",
    tooltipText: "#e4e4e7",
    accent: "#60a5fa",
    accentArea: "rgba(96, 165, 250, 0.15)",
    heatRange: ["#16191d", "#1d4ed8", "#60a5fa"],
  };
}

export function chartBase(mode: ThemeMode): EChartsOption {
  const c = chartColors(mode);
  return {
    textStyle: { color: c.axisText },
    legend: { textStyle: { color: c.legendText }, pageTextStyle: { color: c.axisText } },
    grid: { left: 8, right: 16, top: 32, bottom: 8, containLabel: true },
    tooltip: {
      backgroundColor: c.surface,
      borderColor: c.border,
      textStyle: { color: c.tooltipText },
    },
  };
}

// Stable per-model colors, reused across every chart so a model keeps its color.
export const MODEL_COLORS = ["#60a5fa", "#34d399", "#fbbf24", "#f472b6", "#a78bfa", "#f87171"];

export function modelColor(index: number): string {
  return MODEL_COLORS[index % MODEL_COLORS.length]!;
}
