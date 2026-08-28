import { useState } from "react";

import { aliasKey, displayName } from "../lib/alias";
import type { ModelUsageSummary } from "../lib/api";
import { formatCost, formatTokens } from "../lib/format";

// Shared per-model breakdown table (overview + models views).
// Units: token columns count tokens; the cost column is CNY (per price table).
// The overview passes onAlias to render an editable "别名" column; other pages
// only display the alias (defaulting to the raw model id).
export default function ModelTable({
  models,
  aliases = {},
  onAlias,
}: {
  models: ModelUsageSummary[];
  aliases?: Record<string, string>;
  onAlias?: (key: string, value: string) => void;
}) {
  return (
    <>
      <p className="mb-2 text-xs text-zinc-600">
        单位：token 列为 tokens；输入 / 输出 / 缓存写 / 缓存读 四列互斥、相加即总计，其中「输入」只算
        <span className="text-zinc-500">未命中缓存</span>
        的部分（缓存命中的 token 只按缓存档计价一次）；成本列按价格表折算人民币 ¥
      </p>
      {/* 表格比栏宽时在自己的壳里横滚:此前 w-full 表格的最小宽由内容决定,
          压窄页面会穿过容器顶出文档级横向滚动。 */}
      <div className="overflow-x-auto">
      <table className="w-full min-w-[820px] text-sm">
      <thead>
        <tr className="border-b border-zinc-800 text-left text-xs text-zinc-500">
          <th className="py-2 pr-4 font-medium">来源</th>
          <th className="py-2 pr-4 font-medium">模型</th>
          {onAlias && <th className="py-2 pr-4 font-medium">别名</th>}
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
        {models.map((row) => {
          const key = aliasKey(row.source, row.provider_id, row.model_id);
          return (
          <tr key={key} className="border-b border-zinc-800/60">
            <td className="py-2 pr-4">
              <span className="rounded bg-zinc-800 px-1.5 py-0.5 font-mono text-[11px] text-zinc-400">
                {row.source}
              </span>
            </td>
            <td className="py-2 pr-4 font-mono text-xs text-zinc-300" title={row.model_id}>
              {onAlias ? row.model_id : displayName(aliases, row.source, row.provider_id, row.model_id)}
            </td>
            {onAlias && (
              <td className="py-2 pr-4">
                <AliasInput
                  stored={aliases[key] ?? ""}
                  placeholder={row.model_id}
                  onChange={(value) => onAlias(key, value)}
                />
              </td>
            )}
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
              {row.estimated_cost === null ? (
                <span className="rounded bg-zinc-800 px-1.5 py-0.5 text-xs text-zinc-400">未计价</span>
              ) : (
                formatCost(row.estimated_cost)
              )}
            </td>
          </tr>
          );
        })}
      </tbody>
    </table>
      </div>
    </>
  );
}

/**
 * The box must hold exactly what the user typed. The alias store normalizes on
 * write (trim, and drop the entry when the value equals the default model id),
 * so feeding that normalized value straight back would blank the box mid-typing
 * — e.g. "kimi-k3-官方" passes through "kimi-k3" and gets wiped. The draft is
 * local; it only re-syncs with the store when the field loses focus.
 */
function AliasInput({
  stored,
  placeholder,
  onChange,
}: {
  stored: string;
  placeholder: string;
  onChange: (value: string) => void;
}) {
  const [draft, setDraft] = useState(stored);
  return (
    <input
      value={draft}
      onChange={(e) => {
        setDraft(e.target.value);
        onChange(e.target.value);
      }}
      onBlur={() => setDraft(stored)}
      placeholder={placeholder}
      className="w-40 rounded-md border border-zinc-800 bg-zinc-950 px-2 py-1 font-mono text-xs text-zinc-200"
    />
  );
}
