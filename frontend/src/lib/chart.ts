import type { EChartsOption } from "echarts";

// Shared dark-theme bits (zinc palette) so every chart reads consistently.
const AXIS_TEXT = "#a1a1aa";

export function darkBase(): EChartsOption {
  return {
    textStyle: { color: AXIS_TEXT },
    legend: { textStyle: { color: "#d4d4d8" }, pageTextStyle: { color: AXIS_TEXT } },
    grid: { left: 8, right: 16, top: 32, bottom: 8, containLabel: true },
    tooltip: {
      backgroundColor: "#18181b",
      borderColor: "#3f3f46",
      textStyle: { color: "#e4e4e7" },
    },
  };
}

// Stable per-model colors, reused across every chart so a model keeps its color.
export const MODEL_COLORS = ["#60a5fa", "#34d399", "#fbbf24", "#f472b6", "#a78bfa", "#f87171"];

export function modelColor(index: number): string {
  return MODEL_COLORS[index % MODEL_COLORS.length]!;
}
