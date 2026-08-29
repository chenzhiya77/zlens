import { useQuery } from "@tanstack/react-query";
import { useMemo, useState, type ReactNode } from "react";
import { useSearchParams } from "react-router-dom";

import EChart from "../components/EChart";
import ModelTable from "../components/ModelTable";
import Segmented from "../components/Segmented";
import { ErrorBlock, LoadingBlock } from "../components/states";
import { displayName, getAliases, parseModelKey, setAlias } from "../lib/alias";
import {
  fetchMeta,
  fetchOverview,
  fetchTrends,
  viewQueryString,
  type SortColumn,
  type ViewQuery,
} from "../lib/api";
import { formatDateTime, formatCost, formatTokens } from "../lib/format";
import type { EChartsOption } from "echarts";

// 视觉结构照 Ardot 设计稿 719793184410961「AI用量总览-优化版」(T23),交互接线为 T24:
// 周期选择器 / 来源 chips / 搜索 / 表头排序 / 合计行 / 导出 / 每小时自动刷新。
// 视图状态只有四项(窗口、来源、排序方向),全部住在 URL query 里——刷新、
// 前进后退、分享链接天然还原,不需要额外的状态管理。
// 唯一允许的客户端过滤是搜索框(过滤显示行,不影响任何聚合);其余一律走后端参数,
// 因为未计价判定与四档归一是业务口径,前端复制必算错。

const HOUR_MS = 3_600_000;

type WindowPreset = "7" | "30" | "90" | "all" | "custom";

const WINDOW_OPTIONS: { key: WindowPreset; label: string }[] = [
  { key: "7", label: "近 7 天" },
  { key: "30", label: "近 30 天" },
  { key: "90", label: "近 90 天" },
  { key: "all", label: "全部" },
  { key: "custom", label: "自定义" },
];

function localDate(d: Date): string {
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}

/** 后端只认绝对日期;「近 N 天」的锚点是今天,由前端翻译(T15 的分工)。 */
function resolveWindow(preset: WindowPreset, start?: string, end?: string): ViewQuery {
  if (preset === "all") return {};
  if (preset === "custom") return { start: start || undefined, end: end || undefined };
  const days = Number(preset);
  const today = new Date();
  const first = new Date(today);
  first.setDate(today.getDate() - (days - 1));
  return { start: localDate(first), end: localDate(today) };
}

/** 环比徽章:红涨绿跌。delta 或 change_rate 为 null 时不渲染——没有 "—%" 或 0%。
 * 两种措辞(设计稿 2:17/2:31):Hero 带「上行/下行」方向词,辅指标卡用 +/- 号;
 * 红两处都是设计稿原值(hero #ef4444=red-500,requests #10b981=emerald-500)。 */
function DeltaBadge({
  rate,
  upIsGood,
  showDirection = false,
}: {
  rate: number | null | undefined;
  upIsGood: boolean;
  showDirection?: boolean;
}) {
  if (rate === null || rate === undefined) return null;
  if (rate === 0) {
    return <span className="whitespace-nowrap text-xs text-zinc-500">较上期 ±0.0%</span>;
  }
  const good = rate > 0 === upIsGood;
  const color = good ? "text-emerald-500" : "text-red-500";
  if (showDirection) {
    const pct = `${Math.abs(rate * 100).toFixed(1)}%`;
    const word = rate > 0 ? "上行" : "下行";
    return (
      <span className={`whitespace-nowrap text-xs font-medium ${color}`}>
        较上期 {pct} {word}
      </span>
    );
  }
  const pct = `${rate > 0 ? "+" : ""}${(rate * 100).toFixed(1)}%`;
  return (
    <span className={`whitespace-nowrap text-xs ${color}`}>较上期 {pct}</span>
  );
}

export default function Overview() {
  const [searchParams, setSearchParams] = useSearchParams();
  const [aliases, setAliasesState] = useState<Record<string, string>>(() => getAliases());
  const [search, setSearch] = useState("");

  const param = (key: string, fallback: string) => searchParams.get(key) ?? fallback;
  const windowPreset = param("window", "30") as WindowPreset;
  const customStart = searchParams.get("start") ?? undefined;
  const customEnd = searchParams.get("end") ?? undefined;
  const source = param("source", "");
  const sort = param("sort", "estimated_cost") as SortColumn;
  const order = param("order", "desc");

  const setParams = (updates: Record<string, string | null>) => {
    const next = new URLSearchParams(searchParams);
    for (const [key, value] of Object.entries(updates)) {
      if (value === null || value === "") next.delete(key);
      else next.set(key, value);
    }
    setSearchParams(next, { replace: true });
  };

  /** 切到自定义时预填近 30 天,保证 URL 里的区间永远合法、请求不会带空日期。 */
  const switchWindow = (preset: WindowPreset) => {
    if (preset !== "custom") {
      setParams({ window: preset, start: null, end: null });
      return;
    }
    const { start, end } = resolveWindow("30");
    setParams({
      window: "custom",
      start: customStart || start || null,
      end: customEnd || end || null,
    });
  };

  const handleSort = (column: SortColumn) => {
    if (sort === column) {
      setParams({ order: order === "desc" ? "asc" : "desc" });
    } else {
      setParams({ sort: column, order: "desc" });
    }
  };

  const handleAlias = (key: string, value: string) => {
    setAlias(key, value, key.split("|")[2] ?? "");
    setAliasesState(getAliases());
  };

  const windowQuery = resolveWindow(windowPreset, customStart, customEnd);
  const viewQuery: ViewQuery = {
    ...windowQuery,
    source: source || undefined,
    sort,
    order,
  };
  const rangeQuery: ViewQuery = { ...windowQuery, source: source || undefined };

  const meta = useQuery({
    queryKey: ["meta", rangeQuery],
    queryFn: () => fetchMeta(rangeQuery),
    refetchInterval: HOUR_MS,
  });
  const overview = useQuery({
    queryKey: ["overview", viewQuery],
    queryFn: () => fetchOverview(viewQuery),
    refetchInterval: HOUR_MS,
  });
  const trends = useQuery({
    queryKey: ["trends", rangeQuery, windowPreset],
    queryFn: () =>
      fetchTrends({ ...rangeQuery, granularity: windowPreset === "all" ? "month" : "day" }),
    refetchInterval: HOUR_MS,
  });

  const chartOption: EChartsOption = useMemo(() => {
    const days = trends.data?.days ?? [];
    const monthly = windowPreset === "all";
    return {
      grid: { left: 2, right: 2, top: 8, bottom: 2 },
      xAxis: { type: "category", data: days.map((d) => d.day), show: false },
      yAxis: { type: "value", show: false },
      tooltip: { trigger: "axis" },
      series: [
        {
          name: "按量消耗 (CNY)",
          type: monthly ? "bar" : "line",
          // 成本未计价的日子是 null,折线必须断口,补 0 等于画一条假的下降。
          data: days.map((d) => d.estimated_cost),
          connectNulls: false,
          showSymbol: false,
          smooth: true,
          barMaxWidth: 22,
          itemStyle: { color: "#3b82f6" },
          lineStyle: { color: "#3b82f6", width: 2 },
          areaStyle: monthly ? undefined : { color: "#3b82f6", opacity: 0.15 },
        },
      ],
    };
  }, [trends.data, windowPreset]);

  if (meta.isLoading || overview.isLoading) return <LoadingBlock />;
  if (meta.isError) return <ErrorBlock error={meta.error} />;
  if (overview.isError) return <ErrorBlock error={overview.error} />;
  if (!meta.data || !overview.data) return null;

  const { data: m } = meta;
  const { data: o } = overview;

  // 搜索是唯一的客户端过滤:只筛显示行,不重算任何合计。
  const needle = search.trim().toLowerCase();
  const visibleModels = needle
    ? o.by_model.filter((row) => {
        const key = `${row.source}|${row.provider_id}|${row.model_id}`;
        const alias = aliases[key] ?? "";
        return (
          row.model_id.toLowerCase().includes(needle) ||
          alias.toLowerCase().includes(needle) ||
          row.provider_id.toLowerCase().includes(needle)
        );
      })
    : o.by_model;

  const exportHref = `/api/export${viewQueryString(viewQuery)}`;
  const hitRate = o.cache_hit_rate;
  const costDelta = o.delta?.estimated_cost.change_rate;
  const requestDelta = o.delta?.request_count.change_rate;

  const buyoutSub =
    o.buyout_total === null
      ? "价格表中没有买断行"
      : o.buyout_total === 0
        ? "免费套餐"
        : "已付清";

  return (
    <div className="@container space-y-8">
      <header className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">AI 用量总览</h1>
          <p className="mt-1 whitespace-nowrap text-xs text-zinc-500">
            数据范围 {formatDateTime(m.first_request_at)} 至 {formatDateTime(m.last_request_at)}
            <span className="mx-2 text-zinc-700">·</span>数据源 {m.source_id}
            <span className="mx-2 text-zinc-700">·</span>统计生成于 {formatDateTime(m.generated_at)}
          </p>
        </div>
        <div className="flex flex-col items-end gap-2">
          <Segmented value={windowPreset} options={WINDOW_OPTIONS} onChange={switchWindow} />
          {windowPreset === "custom" && (
            <div className="flex items-center gap-2 text-xs text-zinc-500">
              <input
                type="date"
                value={customStart ?? ""}
                onChange={(e) => setParams({ start: e.target.value })}
                className="rounded-md border border-zinc-800 bg-zinc-950 px-2 py-1 text-xs text-zinc-200"
              />
              <span>→</span>
              <input
                type="date"
                value={customEnd ?? ""}
                onChange={(e) => setParams({ end: e.target.value })}
                className="rounded-md border border-zinc-800 bg-zinc-950 px-2 py-1 text-xs text-zinc-200"
              />
            </div>
          )}
        </div>
      </header>

      {/* Hero 主指标卡:两笔钱里的「正在烧的钱」。右侧是同窗口的成本趋势
          (定长窗口=按日折线,全部=按月柱状;未计价处断口不补 0)。 */}
      <section className="flex flex-wrap items-stretch justify-between gap-6 rounded-2xl border border-zinc-800 bg-zinc-900 px-8 py-6">
        <div className="min-w-0">
          <p className="text-sm text-zinc-500">按量消耗 (CNY)</p>
          <p
            className={
              o.estimated_cost === null
                ? "mt-2 text-4xl font-bold tracking-tight"
                : "mt-2 whitespace-nowrap text-6xl font-bold tracking-tight tabular-nums"
            }
          >
            {formatCost(o.estimated_cost)}
          </p>
          <div className="mt-2">
            <DeltaBadge rate={costDelta} upIsGood={false} showDirection />
          </div>
          {/* 设计稿 2:18:口径说明比正文淡一档(#a1a1aa = 翻转后的 zinc-600),
              不与 header 说明行(zinc-500)同级。措辞含「缓存写」是 D4 纠正,别抄回画布旧文案。 */}
          <p className="mt-3 text-xs text-zinc-600">
            估算口径:输入 + 输出 + 缓存写 + 缓存读 四档分别乘价求和,不包含已结清金额
          </p>
        </div>
        <div className="min-h-[96px] w-full max-w-[360px] self-center">
          <EChart option={chartOption} height={120} />
        </div>
      </section>

      {/* 未计价渠道提醒(D6):挂在 Hero 正下方,先解释成本列为什么有空。 */}
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

      {/* 5 张 KPI 卡按容器宽度分档:≥1100px 一行五张 → 3+2 → 2 列。token 卡的辅助行
          放未缩写的原始数;请求卡与缓存卡挂环比/命中率。 */}
      <div className="grid grid-cols-5 gap-4 @max-[1100px]:grid-cols-3 @max-[640px]:grid-cols-2">
        <KpiCard
          label="总请求次数"
          value={o.request_count.toLocaleString("zh-CN")}
          sub={<DeltaBadge rate={requestDelta} upIsGood />}
        />
        <KpiCard
          label="累计 Token (输入+输出+缓存)"
          value={formatTokens(o.total_tokens)}
          sub={<span>{`${o.total_tokens.toLocaleString("zh-CN")} tokens`}</span>}
        />
        <KpiCard
          label="缓存读 Token"
          value={formatTokens(o.cache_read_tokens)}
          sub={
            /* 辅助行只放命中率(设计稿 2:37=#10b981 绿色):带原始 token 数会
               超出卡片宽度;大数已由卡面 value 呈现,不重复。 */
            hitRate === null || hitRate === undefined ? null : (
              <span className="font-medium text-emerald-500">
                {`缓存命中率 ${(hitRate * 100).toFixed(1)}%(按 token 计)`}
              </span>
            )
          }
        />
        <KpiCard
          label="输出 Token"
          value={formatTokens(o.output_tokens)}
          sub={<span>{`${o.output_tokens.toLocaleString("zh-CN")} tokens`}</span>}
        />
        {/* 两笔钱里的「已经付掉的钱」,与 Hero 的按量消耗分列展示、永不相加。 */}
        <KpiCard
          label="实购支出 (CNY)"
          value={o.buyout_total === null ? "未填" : formatCost(o.buyout_total)}
          sub={<span>{buyoutSub}</span>}
        />
      </div>

      <section>
        <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
          <div className="flex items-baseline gap-3">
            <h2 className="text-lg font-semibold">按模型明细</h2>
            <p className="text-xs text-zinc-500">
              共 {o.by_model.length} 个模型 · 按
              {sort === "estimated_cost" ? "成本" : sort === "request_count" ? "请求数" : "Token 用量"}
              {order === "desc" ? "降序" : "升序"}
            </p>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            {/* 来源 chips 来自 T18 的 meta.sources:不可用来源置灰并带原因,
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
              {(m.sources ?? []).map((ref) =>
                ref.available ? (
                  <button
                    key={ref.id}
                    type="button"
                    onClick={() => setParams({ source: ref.id })}
                    title={ref.id}
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
            <input
              type="search"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="搜索模型或别名"
              className="w-48 rounded-lg border border-zinc-800 bg-zinc-950 px-3 py-1.5 text-xs text-zinc-200 placeholder:text-zinc-600"
            />
            <a
              href={exportHref}
              download
              title="导出当前视图的按模型明细(Markdown)"
              className="rounded-lg border border-zinc-800 bg-zinc-900/60 px-3 py-1.5 text-xs text-zinc-300 transition-colors hover:bg-zinc-800 hover:text-zinc-100"
            >
              导出 MD
            </a>
          </div>
        </div>
        <ModelTable
          models={visibleModels}
          aliases={aliases}
          onAlias={handleAlias}
          sort={sort}
          order={order}
          onSort={handleSort}
          totals={o.totals}
          modelCount={o.by_model.length}
        />
      </section>

      <footer className="flex items-center justify-between border-t border-zinc-800 pt-4 text-xs text-zinc-500">
        <span>数据更新于 {formatDateTime(m.generated_at)} · 每小时自动刷新一次</span>
        <span>zlens v{m.version}</span>
      </footer>
    </div>
  );
}

/** Hero 下的一张 KPI 卡:标签在上、大数字居中、辅助行(原始 token 数/环比/命中率)在底。 */
function KpiCard({
  label,
  value,
  sub,
}: {
  label: string;
  value: string;
  sub?: ReactNode;
}) {
  return (
    <div className="rounded-xl border border-zinc-800 bg-zinc-900 px-5 py-4">
      <p className="whitespace-nowrap text-xs text-zinc-500">{label}</p>
      <p className="mt-2 whitespace-nowrap text-3xl font-semibold tracking-tight tabular-nums">
        {value}
      </p>
      {sub && <p className="mt-1 whitespace-nowrap text-xs text-zinc-500">{sub}</p>}
    </div>
  );
}
