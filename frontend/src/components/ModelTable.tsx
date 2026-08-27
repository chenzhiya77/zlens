import type { ModelUsageSummary } from "../lib/api";
import { formatCost, formatTokens } from "../lib/format";

// Shared per-model breakdown table (overview + models views).
export default function ModelTable({ models }: { models: ModelUsageSummary[] }) {
  return (
    <table className="w-full text-sm">
      <thead>
        <tr className="border-b border-zinc-800 text-left text-xs text-zinc-500">
          <th className="py-2 pr-4 font-medium">来源</th>
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
        {models.map((row) => (
          <tr key={`${row.provider_id}/${row.model_id}`} className="border-b border-zinc-900">
            <td className="py-2 pr-4">
              <span className="rounded bg-zinc-800 px-1.5 py-0.5 font-mono text-[11px] text-zinc-400">
                {row.source}
              </span>
            </td>
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
                <span className="rounded bg-zinc-800 px-1.5 py-0.5 text-xs text-zinc-400">未计价</span>
              ) : (
                formatCost(row.estimated_cost_usd)
              )}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
