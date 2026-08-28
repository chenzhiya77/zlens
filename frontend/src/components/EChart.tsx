import { useEffect, useRef } from "react";
import * as echarts from "echarts";

import type { EChartsOption } from "echarts";

// Minimal React wrapper: init once, push options, follow container resizes.
export default function EChart({ option, height = 320 }: { option: EChartsOption; height?: number }) {
  const ref = useRef<HTMLDivElement>(null);
  const chartRef = useRef<echarts.ECharts | null>(null);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const chart = echarts.init(el);
    chartRef.current = chart;
    const observer = new ResizeObserver(() => chart.resize());
    observer.observe(el);
    return () => {
      observer.disconnect();
      chart.dispose();
      chartRef.current = null;
    };
  }, []);

  useEffect(() => {
    chartRef.current?.setOption(option, true);
  }, [option]);

  return <div ref={ref} style={{ width: "100%", height, overflow: "hidden" }} />;
}
