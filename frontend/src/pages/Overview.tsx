import { useQuery } from "@tanstack/react-query";
import { useState } from "react";

import ModelTable from "../components/ModelTable";
import { ErrorBlock, LoadingBlock } from "../components/states";
import { displayName, getAliases, parseModelKey, setAlias } from "../lib/alias";
import { fetchMeta, fetchOverview } from "../lib/api";
import { formatDateTime, formatCost, formatTokens } from "../lib/format";

// 视觉结构照 Ardot 设计稿 719793184410961「AI用量总览-优化版」(T23):
// Header → Hero 主指标卡 → 未计价提醒 → 5 张 KPI 卡 → 按模型明细表 → 页脚。
// 颜色全部走 zinc token,明暗两主题自动成立,不硬编码设计稿的十六进制值。
// 环比位与缓存命中率本阶段刻意留空(T16/T21 落地前不渲染占位数字)。

/** Hero 下的一张 KPI 卡:标签在上、大数字居中、辅助行(原始 token 数/语义提示)在底。 */
function KpiCard({ label, value, sub }: { label: string; value: string; sub?: string }) {
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

export default function Overview() {
  const meta = useQuery({ queryKey: ["meta"], queryFn: fetchMeta });
  const overview = useQuery({ queryKey: ["overview"], queryFn: fetchOverview });
  const [aliases, setAliasesState] = useState<Record<string, string>>(() => getAliases());

  const handleAlias = (key: string, value: string) => {
    setAlias(key, value, key.split("|")[2] ?? "");
    setAliasesState(getAliases());
  };

  if (meta.isLoading || overview.isLoading) return <LoadingBlock />;
  if (meta.isError) return <ErrorBlock error={meta.error} />;
  if (overview.isError) return <ErrorBlock error={overview.error} />;
  if (!meta.data || !overview.data) return null;

  const { data: m } = meta;
  const { data: o } = overview;

  const buyoutSub =
    o.buyout_total === null
      ? "价格表中没有买断行"
      : o.buyout_total === 0
        ? "免费套餐"
        : "已付清";

  return (
    <div className="@container space-y-8">
      <header>
        <h1 className="text-2xl font-bold tracking-tight">AI 用量总览</h1>
        <p className="mt-1 whitespace-nowrap text-xs text-zinc-500">
          数据范围 {formatDateTime(m.first_request_at)} 至 {formatDateTime(m.last_request_at)}
          <span className="mx-2 text-zinc-700">·</span>数据源 {m.source_id}
          <span className="mx-2 text-zinc-700">·</span>统计生成于 {formatDateTime(m.generated_at)}
        </p>
      </header>

      {/* Hero 主指标卡:两笔钱里的「正在烧的钱」。环比位等 T16 落地后再渲染。 */}
      <section className="rounded-2xl border border-zinc-800 bg-zinc-900 px-8 py-6">
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
        <p className="mt-3 text-xs text-zinc-500">
          估算口径:输入 + 输出 + 缓存写 + 缓存读 四档分别乘价求和,不包含已结清金额
        </p>
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
          放未缩写的原始数,大数与原始数互相校对;命中率/环比留空等 T16/T21。 */}
      <div className="grid grid-cols-5 gap-4 @max-[1100px]:grid-cols-3 @max-[640px]:grid-cols-2">
        <KpiCard
          label="总请求次数"
          value={o.request_count.toLocaleString("zh-CN")}
        />
        <KpiCard
          label="累计 Token (输入+输出+缓存)"
          value={formatTokens(o.total_tokens)}
          sub={`${o.total_tokens.toLocaleString("zh-CN")} tokens`}
        />
        <KpiCard
          label="缓存读 Token"
          value={formatTokens(o.cache_read_tokens)}
          sub={`${o.cache_read_tokens.toLocaleString("zh-CN")} tokens`}
        />
        <KpiCard
          label="输出 Token"
          value={formatTokens(o.output_tokens)}
          sub={`${o.output_tokens.toLocaleString("zh-CN")} tokens`}
        />
        {/* 两笔钱里的「已经付掉的钱」,与 Hero 的按量消耗分列展示、永不相加。 */}
        <KpiCard
          label="实购支出 (CNY)"
          value={o.buyout_total === null ? "未填" : formatCost(o.buyout_total)}
          sub={buyoutSub}
        />
      </div>

      <section>
        <div className="mb-3 flex items-baseline gap-3">
          <h2 className="text-lg font-semibold">按模型明细</h2>
          <p className="text-xs text-zinc-500">
            共 {o.by_model.length} 个模型 · 按 Token 用量降序
          </p>
        </div>
        <ModelTable models={o.by_model} aliases={aliases} onAlias={handleAlias} />
      </section>

      <footer className="flex items-center justify-between border-t border-zinc-800 pt-4 text-xs text-zinc-500">
        <span>数据更新于 {formatDateTime(m.generated_at)}</span>
        <span>zlens v{m.version}</span>
      </footer>
    </div>
  );
}
