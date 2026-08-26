import { useQuery } from "@tanstack/react-query";

import { ApiError, fetchMeta, fetchOverview } from "../lib/api";
import { formatCost, formatDateTime, formatTokens } from "../lib/format";

function Kpi({
  value,
  label,
  hint,
}: {
  value: string;
  label: string;
  hint?: string;
}) {
  return (
    <div className="flex-1 px-6 py-4 first:pl-0 last:pr-0">
      <div className="flex items-baseline gap-2">
        <span className="text-3xl font-semibold tracking-tight tabular-nums">{value}</span>
        {hint && <span className="text-xs text-zinc-500">{hint}</span>}
      </div>
      <p className="mt-1 text-sm text-zinc-500">{label}</p>
    </div>
  );
}

function LoadingBlock({ text }: { text: string }) {
  return <p className="text-sm text-zinc-500">{text}</p>;
}

function ErrorBlock({ error }: { error: Error }) {
  const code = error instanceof ApiError ? error.code : "unknown";
  const friendly =
    code === "source_unavailable"
      ? "找不到 ZCode 本地数据库,请确认本机已安装并使用过 ZCode。"
      : code === "schema_incompatible"
        ? "ZCode 数据库结构与 zlens 预期不一致(可能升级过),本视图暂时无法展示。"
        : error.message;
  return (
    <div className="rounded-lg border border-amber-800/50 bg-amber-950/30 px-5 py-4">
      <p className="text-sm text-amber-200">{friendly}</p>
      <p className="mt-1 text-xs text-amber-500/70">错误码:{code}</p>
    </div>
  );
}

export default function Overview() {
  const meta = useQuery({ queryKey: ["meta"], queryFn: fetchMeta });
  const overview = useQuery({ queryKey: ["overview"], queryFn: fetchOverview });

  if (meta.isLoading || overview.isLoading) return <LoadingBlock text="读取本地数据库…" />;
  if (meta.isError) return <ErrorBlock error={meta.error} />;
  if (overview.isError) return <ErrorBlock error={overview.error} />;
  if (!meta.data || !overview.data) return null;

  const { data: m } = meta;
  const { data: o } = overview;

  return (
    <div className="space-y-8">
      <p className="text-xs text-zinc-500">
        数据范围 {formatDateTime(m.first_request_at)} → {formatDateTime(m.last_request_at)}
        <span className="mx-2 text-zinc-700">|</span>
        统计生成于 {formatDateTime(m.generated_at)}
      </p>

      <div className="flex divide-x divide-zinc-800/80 rounded-xl border border-zinc-800/80 bg-zinc-900/40">
        <Kpi value={o.request_count.toLocaleString("zh-CN")} label="模型请求次数" />
        <Kpi value={formatTokens(o.total_tokens)} label="累计 Token" />
        <Kpi
          value={formatCost(o.estimated_cost_usd)}
          label="估算成本"
          hint={o.estimated_cost_usd === null ? "未配置价格" : "估算值"}
        />
        <Kpi
          value={formatTokens(o.cache_read_tokens)}
          label="缓存读 Token"
          hint="省钱大户"
        />
        <Kpi value={formatTokens(o.output_tokens)} label="输出 Token" />
      </div>

      {m.unpriced_models.length > 0 && (
        <div className="rounded-lg border border-zinc-800 bg-zinc-900/40 px-5 py-3">
          <p className="text-sm text-zinc-400">
            未计价模型(价格表中没有,仅显示 token):
            {m.unpriced_models.map((model) => (
              <span
                key={model}
                className="ml-2 inline-block rounded bg-zinc-800 px-2 py-0.5 font-mono text-xs text-zinc-300"
              >
                {model}
              </span>
            ))}
          </p>
        </div>
      )}

      <section>
        <h2 className="mb-3 text-sm font-medium text-zinc-400">按模型明细</h2>
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-zinc-800 text-left text-xs text-zinc-500">
              <th className="py-2 pr-4 font-medium">模型</th>
              <th className="py-2 pr-4 text-right font-medium">请求</th>
              <th className="py-2 pr-4 text-right font-medium">输入</th>
              <th className="py-2 pr-4 text-right font-medium">输出</th>
              <th className="py-2 pr-4 text-right font-medium">缓存写</th>
              <th className="py-2 pr-4 text-right font-medium">缓存读</th>
              <th className="py-2 pr-4 text-right font-medium">总计</th>
              <th className="py-2 text-right font-medium">成本(估算)</th>
            </tr>
          </thead>
          <tbody>
            {o.by_model.map((row) => (
              <tr key={`${row.provider_id}/${row.model_id}`} className="border-b border-zinc-900">
                <td className="py-2 pr-4 font-mono text-xs text-zinc-300">{row.model_id}</td>
                <td className="py-2 pr-4 text-right tabular-nums">
                  {row.request_count.toLocaleString("zh-CN")}
                </td>
                <td className="py-2 pr-4 text-right tabular-nums">{formatTokens(row.input_tokens)}</td>
                <td className="py-2 pr-4 text-right tabular-nums">{formatTokens(row.output_tokens)}</td>
                <td className="py-2 pr-4 text-right tabular-nums">
                  {formatTokens(row.cache_creation_tokens)}
                </td>
                <td className="py-2 pr-4 text-right tabular-nums">
                  {formatTokens(row.cache_read_tokens)}
                </td>
                <td className="py-2 pr-4 text-right tabular-nums font-medium">
                  {formatTokens(row.total_tokens)}
                </td>
                <td className="py-2 text-right tabular-nums">
                  {row.estimated_cost_usd === null ? (
                    <span className="rounded bg-zinc-800 px-1.5 py-0.5 text-xs text-zinc-400">
                      未计价
                    </span>
                  ) : (
                    formatCost(row.estimated_cost_usd)
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
