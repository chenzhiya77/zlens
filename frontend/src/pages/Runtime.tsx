import { useQueries, useQuery } from "@tanstack/react-query";
import { useSearchParams } from "react-router-dom";

import { EmptyBlock, ErrorBlock, LoadingBlock } from "../components/states";
import {
  fetchHealth,
  fetchMeta,
  fetchPerformance,
  type LatencyStats,
  type ViewQuery,
} from "../lib/api";

// 视觉结构照 Ardot 画布「运行质量2」720202836547247 顶层 2:2(T26):
// 页头 → 健康结论栏 → 请求耗时/首字延迟两卡 → 三张统计卡 → 分源对比卡 →
// 错误类型分布卡 → 底部口径注。视图状态只有 source 一项,住 URL query(同 T24)。
// 分源不是前端拆分:chips 让后端按 ?source= 重算整页;分源对比卡对每个可用源
// 并行发独立请求,前端只做纯计数除法,P99 直接用后端 latency_stats 结果。

const REFRESH_MS = 300_000; // 页头文案「自动刷新 · 5 分钟」必须与此一致

/** 状态点阈值(按出错率):健康结论栏与分源对比卡行级共用,票 T26 定的口径。 */
const WARN_RATE = 0.05;
const BAD_RATE = 0.15;

const fmtInt = (n: number) => n.toLocaleString("zh-CN");
const fmtPct = (ratio: number) => `${(ratio * 100).toFixed(1)}%`;

function fmtMs(ms: number): string {
  return ms >= 1000 ? `${(ms / 1000).toFixed(1)} s` : `${ms.toFixed(0)} ms`;
}

/** 比率数值颜色:0 变暗(零值变暗);出错率 ≥5% 上红,重试/取消率不上红。 */
function errorRateClass(rate: number): string {
  if (rate === 0) return "text-zinc-600";
  return rate >= WARN_RATE ? "text-rose-500" : "";
}

const zeroDimClass = (rate: number) => (rate === 0 ? "text-zinc-600" : "");

function LatencyCard({
  title,
  stats,
  note,
}: {
  title: string;
  stats: LatencyStats | null;
  note: string;
}) {
  return (
    <div className="flex-1 rounded-xl border border-zinc-800 bg-zinc-900 p-5">
      <div className="mb-4 flex items-baseline justify-between gap-3">
        <h3 className="text-sm font-semibold">{title}</h3>
        <span className="whitespace-nowrap text-xs text-zinc-500">
          {stats ? `有效样本 ${fmtInt(stats.sample_count)}` : "暂无样本"}
        </span>
      </div>
      {!stats ? (
        <p className="py-8 text-center text-sm text-zinc-600">数据库中没有该字段的有效样本</p>
      ) : (
        <div className="space-y-3.5">
          {(
            [
              ["P50", stats.p50_ms],
              ["P90", stats.p90_ms],
              ["P99", stats.p99_ms],
            ] as const
          ).map(([label, ms]) => (
            <div key={label} className="flex items-center gap-3">
              <span className="w-8 font-mono text-xs text-zinc-500">{label}</span>
              {/* 单一强调色条,条长按本卡 P99 归一(画布:各分位同一最大值比较)。 */}
              <div className="h-1.5 flex-1 rounded bg-zinc-800">
                <div
                  className="h-1.5 rounded bg-sky-500"
                  style={{ width: `${Math.max((ms / (stats.p99_ms || 1)) * 100, 2)}%` }}
                />
              </div>
              <span className="w-16 text-right text-sm tabular-nums">{fmtMs(ms)}</span>
            </div>
          ))}
        </div>
      )}
      <p className="mt-4 text-[11px] text-zinc-600">{note}</p>
    </div>
  );
}

function Metric({
  label,
  value,
  valueClass = "",
}: {
  label: string;
  value: string;
  valueClass?: string;
}) {
  return (
    <div>
      <p className="text-xs text-zinc-500">{label}</p>
      <p className={`mt-1 text-2xl font-semibold tabular-nums ${valueClass}`}>{value}</p>
    </div>
  );
}

function StatCard({
  label,
  value,
  valueClass = "",
  sub,
}: {
  label: string;
  value: string;
  valueClass?: string;
  sub: string;
}) {
  return (
    <div className="rounded-xl border border-zinc-800 bg-zinc-900 px-5 py-4">
      <p className="text-xs text-zinc-500">{label}</p>
      <p className={`mt-2 text-3xl font-semibold tracking-tight tabular-nums ${valueClass}`}>
        {value}
      </p>
      <p className="mt-1 whitespace-nowrap text-xs text-zinc-600">{sub}</p>
    </div>
  );
}

type CompareRow =
  | { id: string; status: "loading" }
  | { id: string; status: "error" }
  | {
      id: string;
      status: "ready";
      count: number;
      retryRate: number;
      errorRate: number;
      cancelRate: number;
      p99Duration: number | null;
      p99Ttft: number | null;
    };

// Merged "how well is it running" view redesigned per canvas 2:2 (T26):
// summary bar, latency cards, stat cards, per-source comparison and error mix.
export default function Runtime() {
  const [searchParams, setSearchParams] = useSearchParams();
  const source = searchParams.get("source") ?? "";

  const setParams = (updates: Record<string, string | null>) => {
    const next = new URLSearchParams(searchParams);
    for (const [key, value] of Object.entries(updates)) {
      if (value === null || value === "") next.delete(key);
      else next.set(key, value);
    }
    setSearchParams(next, { replace: true });
  };

  const query: ViewQuery = { source: source || undefined };
  const meta = useQuery({
    queryKey: ["meta", "runtime"],
    queryFn: () => fetchMeta(),
    refetchInterval: REFRESH_MS,
  });
  const perf = useQuery({
    queryKey: ["performance", query],
    queryFn: () => fetchPerformance(query),
    refetchInterval: REFRESH_MS,
  });
  const health = useQuery({
    queryKey: ["health", query],
    queryFn: () => fetchHealth(query),
    refetchInterval: REFRESH_MS,
  });

  // 分源对比卡恒显示全部可用源(不受 chips 影响);与主查询共享缓存
  // (选中 zcode 时 ["health", {source:"zcode"}] 就是同一份)。
  const available = (meta.data?.sources ?? []).filter((ref) => ref.available);
  const compareOn = available.length >= 2;
  const perSourceHealth = useQueries({
    queries: available.map((ref) => ({
      queryKey: ["health", { source: ref.id }],
      queryFn: () => fetchHealth({ source: ref.id }),
      enabled: compareOn,
      refetchInterval: REFRESH_MS,
    })),
  });
  const perSourcePerf = useQueries({
    queries: available.map((ref) => ({
      queryKey: ["performance", { source: ref.id }],
      queryFn: () => fetchPerformance({ source: ref.id }),
      enabled: compareOn,
      refetchInterval: REFRESH_MS,
    })),
  });

  if (meta.isLoading || perf.isLoading || health.isLoading) return <LoadingBlock />;
  if (meta.isError) return <ErrorBlock error={meta.error} />;
  if (perf.isError) return <ErrorBlock error={perf.error} />;
  if (health.isError) return <ErrorBlock error={health.error} />;
  if (!meta.data || !perf.data || !health.data) return null;

  const d = health.data;
  const compareRows: CompareRow[] = available.map((ref, i) => {
    const h = perSourceHealth[i];
    const p = perSourcePerf[i];
    if (h?.isError || p?.isError) return { id: ref.id, status: "error" };
    if (!h?.data || !p?.data) return { id: ref.id, status: "loading" };
    const n = h.data.request_count;
    return {
      id: ref.id,
      status: "ready",
      count: n,
      retryRate: n > 0 ? h.data.requests_with_retries / n : 0,
      errorRate: n > 0 ? h.data.errored_requests / n : 0,
      cancelRate: n > 0 ? h.data.cancelled_by_user / n : 0,
      p99Duration: p.data.duration_ms?.p99_ms ?? null,
      p99Ttft: p.data.time_to_first_token_ms?.p99_ms ?? null,
    };
  });
  const compareSettled = compareRows.every((r) => r.status !== "loading");
  const compareTotal = compareRows.reduce((sum, r) => sum + (r.status === "ready" ? r.count : 0), 0);

  const errorRate = d.request_count > 0 ? d.errored_requests / d.request_count : 0;
  const retryRate = d.request_count > 0 ? d.requests_with_retries / d.request_count : 0;
  const cancelRate = d.request_count > 0 ? d.cancelled_by_user / d.request_count : 0;
  const tone =
    errorRate < WARN_RATE
      ? { dot: "bg-emerald-500", label: "总体健康" }
      : errorRate < BAD_RATE
        ? { dot: "bg-amber-500", label: "有波动" }
        : { dot: "bg-rose-500", label: "需要关注" };
  const maxErrorCount = Math.max(...d.errors.map((e) => e.request_count), 1);
  const topError = d.errors[0];

  return (
    <div className="space-y-5">
      <header className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="text-xl font-semibold tracking-tight">运行质量</h1>
          <p className="mt-1 text-xs text-zinc-500">
            累计口径 · {source === "" ? "数据库共" : `${source} 共`} {fmtInt(d.request_count)}{" "}
            次模型请求
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {/* 来源 chips 来自 meta.sources(同总览页):不可用置灰并带原因,
              挂了也不能消失——消失会让人以为那段用量从来不存在。 */}
          <div className="inline-flex rounded-lg border border-zinc-800 bg-zinc-900/60 p-0.5">
            <button
              type="button"
              onClick={() => setParams({ source: null })}
              className={`rounded-md px-3 py-1.5 text-xs transition-colors ${
                source === "" ? "bg-zinc-700/80 text-zinc-100" : "text-zinc-400 hover:text-zinc-200"
              }`}
            >
              全部
            </button>
            {(meta.data.sources ?? []).map((ref) =>
              ref.available ? (
                <button
                  key={ref.id}
                  type="button"
                  onClick={() => setParams({ source: ref.id })}
                  className={`rounded-md px-3 py-1.5 text-xs transition-colors ${
                    source === ref.id
                      ? "bg-zinc-700/80 text-zinc-100"
                      : "text-zinc-400 hover:text-zinc-200"
                  }`}
                >
                  {ref.id}
                </button>
              ) : (
                <span
                  key={ref.id}
                  title={`不可用:${ref.error ?? "未知原因"}`}
                  className="cursor-not-allowed rounded-md px-3 py-1.5 text-xs text-zinc-600 line-through"
                >
                  {ref.id}
                </span>
              ),
            )}
          </div>
          <span className="rounded-lg border border-zinc-800 bg-zinc-900/60 px-3 py-1.5 text-xs text-zinc-500">
            自动刷新 · 5 分钟
          </span>
        </div>
      </header>

      {/* 健康结论栏:状态点 + 三个派生比率(纯计数除法,前端算安全)。 */}
      <section className="flex flex-wrap items-center justify-between gap-x-10 gap-y-4 rounded-xl border border-zinc-800 bg-zinc-900 px-6 py-5">
        <div className="flex items-center gap-2">
          <span className={`h-2 w-2 rounded-full ${tone.dot}`} />
          <span className="text-sm font-medium">{tone.label}</span>
        </div>
        <Metric label="错误率" value={fmtPct(errorRate)} valueClass={errorRateClass(errorRate)} />
        <Metric label="重试率" value={fmtPct(retryRate)} valueClass={zeroDimClass(retryRate)} />
        <Metric label="取消率" value={fmtPct(cancelRate)} valueClass={zeroDimClass(cancelRate)} />
      </section>

      <section className="flex flex-col gap-4 lg:flex-row">
        {perf.data.duration_ms !== null || perf.data.time_to_first_token_ms !== null ? (
          <>
            <LatencyCard
              title="请求耗时 duration"
              stats={perf.data.duration_ms}
              note="各分位按同一最大值(本卡 P99)比较"
            />
            <LatencyCard
              title="首字延迟 TTFT"
              stats={perf.data.time_to_first_token_ms}
              note="仅统计含首字延迟字段的请求,空值已排除"
            />
          </>
        ) : (
          <EmptyBlock text="数据库中暂无耗时样本" />
        )}
      </section>

      <div className="grid gap-4 md:grid-cols-3">
        <StatCard
          label="模型请求总数"
          value={fmtInt(d.request_count)}
          sub={`含用户取消 ${fmtInt(d.cancelled_by_user)} · 上下文超限 ${fmtInt(d.context_exceeded)}`}
        />
        <StatCard
          label="含重试的请求"
          value={fmtInt(d.requests_with_retries)}
          sub={
            d.requests_with_retries > 0
              ? `重试总次数 ${fmtInt(d.total_retries)} · 平均 ${(
                  d.total_retries / d.requests_with_retries
                ).toFixed(1)} 次/请求`
              : `重试总次数 ${fmtInt(d.total_retries)}`
          }
        />
        <StatCard
          label="出错请求"
          value={fmtInt(d.errored_requests)}
          valueClass={
            d.errored_requests > 0 ? "text-rose-500" : d.errored_requests === 0 ? "text-zinc-600" : ""
          }
          sub={
            topError && d.errored_requests > 0
              ? `错误率 ${fmtPct(errorRate)} · 首位 ${topError.error_type} ${fmtPct(
                  topError.request_count / d.errored_requests,
                )}`
              : `错误率 ${fmtPct(errorRate)} · 无错误记录`
          }
        />
      </div>

      {/* 分源对比卡:逐源独立请求,不受页头 chips 影响;仅一个可用源时无对比对象,整卡隐藏。 */}
      {compareOn && (
        <section className="rounded-xl border border-zinc-800 bg-zinc-900 p-6">
          <div className="mb-4 flex flex-wrap items-baseline justify-between gap-3">
            <h3 className="text-sm font-semibold">分源对比</h3>
            <span className="text-xs text-zinc-500">逐源单独统计 · 不受来源切换影响</span>
          </div>
          {!compareSettled ? (
            <LoadingBlock text="正在逐源统计…" />
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-xs text-zinc-500">
                    <th className="py-2 pr-4 text-left font-normal">来源</th>
                    <th className="py-2 px-4 text-left font-normal">请求总数 · 占比</th>
                    <th className="py-2 px-4 text-right font-normal">重试率</th>
                    <th className="py-2 px-4 text-right font-normal">出错率</th>
                    <th className="py-2 px-4 text-right font-normal">取消率</th>
                    <th className="py-2 px-4 text-right font-normal">耗时 P99</th>
                    <th className="py-2 px-4 text-right font-normal">首字 P99</th>
                    <th className="py-2 pl-4 text-right font-normal">状态</th>
                  </tr>
                </thead>
                <tbody className="tabular-nums">
                  {compareRows.map((row) => {
                    if (row.status !== "ready") {
                      return (
                        <tr key={row.id} className="border-t border-zinc-800/60">
                          <td className="py-2.5 pr-4 font-mono">{row.id}</td>
                          <td colSpan={7} className="py-2.5 px-4 text-xs text-zinc-600">
                            {row.status === "error" ? "该来源数据获取失败" : "…"}
                          </td>
                        </tr>
                      );
                    }
                    const rowTone =
                      row.errorRate < WARN_RATE
                        ? { dot: "bg-emerald-500", label: "健康" }
                        : row.errorRate < BAD_RATE
                          ? { dot: "bg-amber-500", label: "偏高" }
                          : { dot: "bg-rose-500", label: "异常" };
                    return (
                      <tr key={row.id} className="border-t border-zinc-800/60">
                        <td className="py-2.5 pr-4 font-mono">{row.id}</td>
                        <td className="py-2.5 px-4">
                          {fmtInt(row.count)} · {fmtPct(compareTotal > 0 ? row.count / compareTotal : 0)}
                        </td>
                        <td className={`py-2.5 px-4 text-right ${zeroDimClass(row.retryRate)}`}>
                          {fmtPct(row.retryRate)}
                        </td>
                        <td className={`py-2.5 px-4 text-right ${errorRateClass(row.errorRate)}`}>
                          {fmtPct(row.errorRate)}
                        </td>
                        <td className={`py-2.5 px-4 text-right ${zeroDimClass(row.cancelRate)}`}>
                          {fmtPct(row.cancelRate)}
                        </td>
                        <td className="py-2.5 px-4 text-right">
                          {row.p99Duration === null ? (
                            <span className="text-zinc-600">—</span>
                          ) : (
                            fmtMs(row.p99Duration)
                          )}
                        </td>
                        <td className="py-2.5 px-4 text-right">
                          {row.p99Ttft === null ? (
                            <span className="text-zinc-600">—</span>
                          ) : (
                            fmtMs(row.p99Ttft)
                          )}
                        </td>
                        <td className="py-2.5 pl-4 text-right">
                          <span className="inline-flex items-center justify-end gap-1.5">
                            <span className={`h-2 w-2 rounded-full ${rowTone.dot}`} />
                            <span className="text-xs font-medium">{rowTone.label}</span>
                          </span>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
          <p className="mt-3 text-[11px] text-zinc-600">
            占比 = 该源请求 ÷ 全部 {fmtInt(compareTotal)} 次;小样本来源的分位数波动大,对比看趋势不看绝对值。
          </p>
        </section>
      )}

      {/* 错误类型分布:标题随 chips 变化;合并视图下每行带来源标签,单来源时省去。 */}
      <section className="rounded-xl border border-zinc-800 bg-zinc-900 p-6">
        <div className="mb-4 flex flex-wrap items-baseline justify-between gap-3">
          <h3 className="text-sm font-semibold">
            错误类型分布 · 来源:{source === "" ? "全部" : source}
          </h3>
          <span className="text-xs text-zinc-500">
            占出错请求 {fmtInt(d.errored_requests)} 次的比例
            {source === "" ? " · 切换来源后仅统计该源" : ""}
          </span>
        </div>
        {d.errors.length === 0 ? (
          <div className="rounded-lg border border-emerald-900/50 bg-emerald-950/20 px-5 py-4">
            <p className="text-sm text-emerald-300">
              {source === "" ? "当前数据库没有任何错误记录 ✓" : `${source} 没有任何错误记录 ✓`}
            </p>
          </div>
        ) : (
          <div className="space-y-3">
            {d.errors.map((e) => (
              <div key={`${e.source}/${e.error_type}/${e.error_code ?? ""}`}>
                <div className="mb-1 flex items-baseline justify-between gap-3 text-xs">
                  <span className="flex items-baseline gap-2 font-mono">
                    {source === "" && (
                      <span className="rounded bg-zinc-800 px-1.5 py-0.5 text-[11px] text-zinc-500">
                        {e.source}
                      </span>
                    )}
                    {e.error_type}
                    {e.error_code !== null && <span className="text-zinc-500">{e.error_code}</span>}
                  </span>
                  <span className="tabular-nums text-zinc-400">
                    {fmtInt(e.request_count)} 次
                    <span className="ml-2 text-zinc-500">
                      {fmtPct(d.errored_requests > 0 ? e.request_count / d.errored_requests : 0)}
                    </span>
                  </span>
                </div>
                <div className="h-2 rounded bg-zinc-800">
                  <div
                    className="h-2 rounded bg-rose-500/70"
                    style={{ width: `${Math.max((e.request_count / maxErrorCount) * 100, 2)}%` }}
                  />
                </div>
              </div>
            ))}
          </div>
        )}
      </section>

      <p className="text-xs leading-relaxed text-zinc-600">
        口径:重试按请求粒度计数(retry_count &gt; 0 视为含重试);错误按 error_type
        非空计,同类错误合并展示。
        {source === "" ? "当前为数据库累计口径" : `当前仅统计 ${source}`} · 共{" "}
        {fmtInt(d.request_count)} 次请求。
      </p>
    </div>
  );
}
