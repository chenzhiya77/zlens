import { useState } from "react";

import { aliasKey, displayName } from "../lib/alias";
import type { ModelUsageSummary, OverviewTotals, SortColumn } from "../lib/api";
import { formatCost, formatTokens } from "../lib/format";

// Shared per-model breakdown table (overview + models views).
// Units: token columns count tokens; the cost column is CNY (per price table).
// The overview passes onAlias to render an editable "别名" column; other pages
// only display the alias (defaulting to the raw model id).
// T24: when onSort is given the seven numeric headers become sortable buttons
// with an arrow indicator; totals renders the 「全部合计」 footer row — both are
 // backend-owned semantics, this component only renders what it receives.

const SORTABLE_COLUMNS: { key: SortColumn; label: string }[] = [
  { key: "request_count", label: "请求" },
  { key: "input_tokens", label: "输入" },
  { key: "output_tokens", label: "输出" },
  { key: "cache_creation_tokens", label: "缓存写" },
  { key: "cache_read_tokens", label: "缓存读" },
  { key: "total_tokens", label: "总计" },
  { key: "estimated_cost", label: "成本(估算)" },
];

function SortableTh({
  column,
  label,
  sort,
  order,
  onSort,
}: {
  column: SortColumn;
  label: string;
  sort?: SortColumn;
  order?: string;
  onSort?: (column: SortColumn) => void;
}) {
  if (!onSort) {
    return <th className="py-2 pr-4 text-right font-medium">{label}</th>;
  }
  const active = sort === column;
  const arrow = active ? (order === "asc" ? "▲" : "▼") : "⇅";
  return (
    <th className="py-2 pr-4 text-right font-medium">
      <button
        type="button"
        onClick={() => onSort(column)}
        title={`按${label}排序`}
        className={`inline-flex items-center gap-1 transition-colors hover:text-zinc-200 ${
          active ? "text-zinc-100" : "text-zinc-500"
        }`}
      >
        {label}
        <span className="text-[10px] leading-none">{arrow}</span>
      </button>
    </th>
  );
}

/** 成本列的三种表情(设计稿数据行/合计行):未计价是不知道(徽章),0 是事实但
 * 不值得强调(变暗 zinc-600,light 翻转后 #a1a1aa 与画布一致),真金白银才上
 * 设计稿的红 #f04545。 */
function CostText({ cost }: { cost: number | null }) {
  if (cost === null) {
    return (
      <span className="rounded bg-zinc-800 px-1.5 py-0.5 text-xs text-zinc-400">未计价</span>
    );
  }
  if (cost === 0) {
    return <span className="text-zinc-600">{formatCost(cost)}</span>;
  }
  return <span className="font-medium text-[#f04545]">{formatCost(cost)}</span>;
}

export default function ModelTable({
  models,
  aliases = {},
  onAlias,
  sort,
  order,
  onSort,
  totals,
  modelCount,
}: {
  models: ModelUsageSummary[];
  aliases?: Record<string, string>;
  onAlias?: (key: string, value: string) => void;
  sort?: SortColumn;
  order?: string;
  onSort?: (column: SortColumn) => void;
  totals?: OverviewTotals | null;
  modelCount?: number;
}) {
  const labelSpan = onAlias ? 3 : 2;
  return (
    /* 表格卡片(设计稿 2:61):白底圆角卡包住表头/数据行/合计行,表头的浅色
       条(#fafafa)只有落在卡片里才看得见——直接坐在页面底上会与页面同色。
       口径说明不放页面上,导出文件的文件头里已带同一份(T22)。 */
    <div className="overflow-hidden rounded-xl border border-zinc-800 bg-zinc-900">
      {/* 表格比栏宽时在自己的壳里横滚:此前 w-full 表格的最小宽由内容决定,
          压窄页面会穿过容器顶出文档级横向滚动。 */}
      <div className="overflow-x-auto">
        <table className="w-full min-w-[820px] text-sm">
          <thead>
            <tr className="border-b border-zinc-800 bg-zinc-950 text-left text-xs text-zinc-500">
              <th className="py-2 pr-4 font-medium">来源</th>
              <th className="py-2 pr-4 font-medium">模型</th>
              {onAlias && <th className="py-2 pr-4 font-medium">别名</th>}
              {SORTABLE_COLUMNS.map((col) => (
                <SortableTh
                  key={col.key}
                  column={col.key}
                  label={col.label}
                  sort={sort}
                  order={order}
                  onSort={onSort}
                />
              ))}
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
                  <td
                    className="py-2 pr-4 font-mono text-xs text-zinc-300"
                    title={row.model_id}
                  >
                    {onAlias
                      ? row.model_id
                      : displayName(aliases, row.source, row.provider_id, row.model_id)}
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
                  <td className="py-2 pr-4 text-right tabular-nums">
                    {formatTokens(row.input_tokens)}
                  </td>
                  <td className="py-2 pr-4 text-right tabular-nums">
                    {formatTokens(row.output_tokens)}
                  </td>
                  <td
                    className={`py-2 pr-4 text-right tabular-nums ${
                      row.cache_creation_tokens === 0 ? "text-zinc-600" : ""
                    }`}
                  >
                    {formatTokens(row.cache_creation_tokens)}
                  </td>
                  <td className="py-2 pr-4 text-right tabular-nums">
                    {formatTokens(row.cache_read_tokens)}
                  </td>
                  <td className="py-2 pr-4 text-right tabular-nums font-medium">
                    {formatTokens(row.total_tokens)}
                  </td>
                  <td className="py-2 text-right tabular-nums">
                    <CostText cost={row.estimated_cost} />
                  </td>
                </tr>
              );
            })}
          </tbody>
          {totals && (
            <tfoot>
              <tr className="border-t border-zinc-700 bg-zinc-800/40 text-sm">
                <td colSpan={labelSpan} className="py-2 pr-4 text-xs text-zinc-500">
                  全部合计 · 共 {modelCount ?? models.length} 个模型
                </td>
                <td className="py-2 pr-4 text-right tabular-nums">
                  {totals.request_count.toLocaleString("zh-CN")}
                </td>
                <td className="py-2 pr-4 text-right tabular-nums">
                  {formatTokens(totals.input_tokens)}
                </td>
                <td className="py-2 pr-4 text-right tabular-nums">
                  {formatTokens(totals.output_tokens)}
                </td>
                <td
                  className={`py-2 pr-4 text-right tabular-nums ${
                    totals.cache_creation_tokens === 0 ? "text-zinc-600" : ""
                  }`}
                >
                  {formatTokens(totals.cache_creation_tokens)}
                </td>
                <td className="py-2 pr-4 text-right tabular-nums">
                  {formatTokens(totals.cache_read_tokens)}
                </td>
                <td className="py-2 pr-4 text-right tabular-nums font-medium">
                  {formatTokens(totals.total_tokens)}
                </td>
                <td className="py-2 text-right tabular-nums">
                  <CostText cost={totals.estimated_cost} />
                </td>
              </tr>
            </tfoot>
          )}
        </table>
      </div>
    </div>
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
