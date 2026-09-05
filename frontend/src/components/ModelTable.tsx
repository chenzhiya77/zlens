import { Fragment, useState } from "react";
import { useQuery } from "@tanstack/react-query";

import { aliasKey, displayName } from "../lib/alias";
import { modelColor } from "../lib/chart";
import { fetchPricing, type ModelUsageSummary, type OverviewTotals, type SortColumn } from "../lib/api";
import { formatCost, formatCredits, formatTokens } from "../lib/format";

/** 买断价的三档:— 是「不是买断行」(价格表里留空),¥0.00 是真零(免费套餐),
 *  金额是已付清的钱。它与成本列永不相加——付出去的钱和烧掉的钱是两个问题。 */
function BuyoutText({ amount }: { amount: number | null }) {
  if (amount === null) {
    return <span className="text-zinc-600">—</span>;
  }
  if (amount === 0) {
    return <span className="text-zinc-600">{formatCost(amount)}</span>;
  }
  return <span>{formatCost(amount)}</span>;
}

/** 积分列的两档表情:null 是「该来源不报积分」(— 变暗),数值含真 0(混元免费行)
 * 都如实显示两位小数;它属于第三笔账,与成本列永不相加。 */
function CreditsText({ credits }: { credits: number | null }) {
  if (credits === null) {
    return <span className="text-zinc-600">—</span>;
  }
  return <span>{formatCredits(credits)}</span>;
}

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
  creditTotal,
  buyoutTotal,
  groupBySource = false,
}: {
  models: ModelUsageSummary[];
  aliases?: Record<string, string>;
  onAlias?: (key: string, value: string) => void;
  sort?: SortColumn;
  order?: string;
  onSort?: (column: SortColumn) => void;
  totals?: OverviewTotals | null;
  modelCount?: number;
  creditTotal?: number | null;
  /** 买断支出合计(后端算),只进合计行;null = 价格表没有买断行。 */
  buyoutTotal?: number | null;
  /** 按来源(使用的 agent)分组渲染,组头可折叠(价格表分组头同款形式)。 */
  groupBySource?: boolean;
}) {
  const labelSpan = onAlias ? 3 : 2;
  const [collapsedSources, setCollapsedSources] = useState<Set<string>>(new Set());
  // 买断价挂在价格表的渠道行上(用量行不带),按渠道键取;与「现总价」一样
  // 只读后端,不在前端重算。
  const pricingQuery = useQuery({ queryKey: ["pricing"], queryFn: fetchPricing });
  const buyoutByKey = new Map<string, number | null>();
  for (const [key, price] of Object.entries(pricingQuery.data?.models ?? {})) {
    buyoutByKey.set(key, price.buyout_amount);
  }

  // 分组渲染(v3 用户反馈):总览明细按来源分列——不同 agent 的账并排看,组头
  // 可折叠。组间按当前排序键的组内合计降序(排序语义在分组下依然成立),组内
  // 维持传入顺序;搜索过滤已在调用方完成,组头计数是过滤后的口径。
  const sourceGroups = (() => {
    if (!groupBySource) return [];
    const map = new Map<string, ModelUsageSummary[]>();
    for (const row of models) {
      const bucket = map.get(row.source);
      if (bucket) bucket.push(row);
      else map.set(row.source, [row]);
    }
    const metricSum = (rows: ModelUsageSummary[]) => {
      if (sort === "estimated_cost") return rows.reduce((s, r) => s + (r.estimated_cost ?? 0), 0);
      if (sort === "request_count") return rows.reduce((s, r) => s + r.request_count, 0);
      return rows.reduce((s, r) => s + r.total_tokens, 0);
    };
    return [...map.entries()]
      .map(([source, rows]) => ({ source, rows }))
      .sort((a, b) => metricSum(b.rows) - metricSum(a.rows));
  })();

  const toggleSource = (source: string) =>
    setCollapsedSources((prev) => {
      const next = new Set(prev);
      if (next.has(source)) next.delete(source);
      else next.add(source);
      return next;
    });

  const groupHeader = (source: string, rows: ModelUsageSummary[], index: number) => {
    const collapsed = collapsedSources.has(source);
    const sum = (pick: (r: ModelUsageSummary) => number) =>
      rows.reduce((s, r) => s + pick(r), 0);
    const creditRows = rows.filter((r) => r.credits !== null);
    // 分组头是「组级合计行」:数字与数据列逐列对齐(同合计行),左格是来源与折叠开关。
    // 组内数字只在本组内合计——积分单位 per-source,不跨组相加。
    return (
      <tr
        key={`group:${source}`}
        onClick={() => toggleSource(source)}
        title={collapsed ? "点击展开该 agent 的明细" : "点击折叠该 agent 的明细"}
        className={`cursor-pointer border-y border-zinc-700 bg-zinc-800/90 text-xs ${
          collapsed ? "" : "border-b-zinc-700"
        }`}
      >
        <td colSpan={labelSpan} className="py-2 pl-4 pr-4">
          <span className="flex items-center gap-2">
            <span
              className="h-2.5 w-2.5 shrink-0 rounded-full"
              style={{ backgroundColor: modelColor(index) }}
            />
            <span className="font-semibold text-zinc-100">{source}</span>
            <span className="text-zinc-500">{rows.length} 个模型</span>
            <span className="font-mono text-[10px] text-zinc-600">
              {collapsed ? "▸ 展开" : "▾ 折叠"}
            </span>
          </span>
        </td>
        <td className="py-2 pr-4 text-right tabular-nums text-zinc-300">
          {sum((r) => r.request_count).toLocaleString("zh-CN")}
        </td>
        <td className="py-2 pr-4 text-right tabular-nums text-zinc-300">
          {formatTokens(sum((r) => r.input_tokens))}
        </td>
        <td className="py-2 pr-4 text-right tabular-nums text-zinc-300">
          {formatTokens(sum((r) => r.output_tokens))}
        </td>
        <td
          className={`py-2 pr-4 text-right tabular-nums ${
            sum((r) => r.cache_creation_tokens) === 0 ? "text-zinc-600" : "text-zinc-300"
          }`}
        >
          {formatTokens(sum((r) => r.cache_creation_tokens))}
        </td>
        <td className="py-2 pr-4 text-right tabular-nums text-zinc-300">
          {formatTokens(sum((r) => r.cache_read_tokens))}
        </td>
        <td className="py-2 pr-4 text-right tabular-nums font-medium text-zinc-200">
          {formatTokens(sum((r) => r.total_tokens))}
        </td>
        <td className="py-2 pr-4 text-right tabular-nums">
          <BuyoutText
            amount={
              rows.some((r) => buyoutByKey.get(aliasKey(r.source, r.provider_id, r.model_id)) !== null)
                ? sum(
                    (r) =>
                      buyoutByKey.get(aliasKey(r.source, r.provider_id, r.model_id)) ?? 0,
                  )
                : null
            }
          />
        </td>
        <td className="py-2 pr-4 text-right tabular-nums">
          <CostText cost={sum((r) => r.estimated_cost ?? 0)} />
        </td>
        <td className="py-2 pr-4 text-right tabular-nums">
          <CreditsText credits={creditRows.length ? sum((r) => r.credits ?? 0) : null} />
        </td>
      </tr>
    );
  };

  const renderRow = (row: ModelUsageSummary) => {
    const key = aliasKey(row.source, row.provider_id, row.model_id);
    return (
      <tr key={key} className="border-b border-zinc-800/60">
        <td className="py-2 pl-4 pr-4">
          <span className="rounded bg-zinc-800 px-1.5 py-0.5 font-mono text-[11px] text-zinc-400">
            {row.source}
          </span>
        </td>
        <td className="py-2 pr-4 font-mono text-xs text-zinc-300" title={row.model_id}>
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
        <td className="py-2 pr-4 text-right tabular-nums">{formatTokens(row.input_tokens)}</td>
        <td className="py-2 pr-4 text-right tabular-nums">{formatTokens(row.output_tokens)}</td>
        <td
          className={`py-2 pr-4 text-right tabular-nums ${
            row.cache_creation_tokens === 0 ? "text-zinc-600" : ""
          }`}
        >
          {formatTokens(row.cache_creation_tokens)}
        </td>
        <td className="py-2 pr-4 text-right tabular-nums">{formatTokens(row.cache_read_tokens)}</td>
        <td className="py-2 pr-4 text-right tabular-nums font-medium">
          {formatTokens(row.total_tokens)}
        </td>
        <td
          className="py-2 pr-4 text-right tabular-nums"
          title="为该渠道一次性买断/套餐付的钱(人民币)；— 表示不是买断行"
        >
          <BuyoutText amount={buyoutByKey.get(key) ?? null} />
        </td>
        <td className="py-2 pr-4 text-right tabular-nums">
          <CostText cost={row.estimated_cost} />
        </td>
        <td
          className="py-2 pr-4 text-right tabular-nums"
          title="第三笔账:该来源上报的实扣积分(与 token 成本互不折算);— 表示该来源不报积分"
        >
          <CreditsText credits={row.credits} />
        </td>
      </tr>
    );
  };

  return (
    /* 表格卡片(设计稿 2:61):白底圆角卡包住表头/数据行/合计行,表头的浅色
       条(#fafafa)只有落在卡片里才看得见——直接坐在页面底上会与页面同色。
       口径说明不放页面上,导出文件的文件头里已带同一份(T22)。 */
    <div className="overflow-hidden rounded-xl border border-zinc-800 bg-zinc-900">
      {/* 表格比栏宽时在自己的壳里横滚:此前 w-full 表格的最小宽由内容决定,
          压窄页面会穿过容器顶出文档级横向滚动。 */}
      <div className="overflow-x-auto">
        <table className="w-full min-w-[900px] text-sm">
          <thead>
              <tr className="border-b border-zinc-800 bg-zinc-950 text-left text-xs text-zinc-500">
                <th className="py-2 pl-4 pr-4 font-medium">来源</th>
                <th className="py-2 pr-4 font-medium">模型</th>
                {onAlias && <th className="py-2 pr-4 font-medium">别名</th>}
                {/* 积分列插在总计与成本之间(与数据行/合计行/Projects 页同序):
                    Fragment 让它在可排序的列序列里占位而不参与排序。 */}
                {SORTABLE_COLUMNS.map((col) => (
                  <Fragment key={col.key}>
                    {col.key === "estimated_cost" && (
                      <th
                        className="py-2 pr-4 text-right font-medium"
                        title="为该渠道一次性买断/套餐付的钱(人民币)，在价格表的「买断价」列维护；— 表示不是买断行，与成本永不相加"
                      >
                        买断价 ¥
                      </th>
                    )}
                    <SortableTh
                      column={col.key}
                      label={col.label}
                      sort={sort}
                      order={order}
                      onSort={onSort}
                    />
                    {col.key === "estimated_cost" && (
                      <th
                        className="py-2 pr-4 text-right font-medium"
                        title="第三笔账:来源上报的实扣积分(原价/折扣差额与标价值见总览卡片);— 表示该来源不报积分"
                      >
                        积分
                      </th>
                    )}
                  </Fragment>
                ))}
              </tr>
          </thead>
          <tbody>
            {groupBySource
              ? sourceGroups.flatMap(({ source, rows }, index) => [
                  groupHeader(source, rows, index),
                  ...(collapsedSources.has(source) ? [] : rows.map(renderRow)),
                ])
              : models.map(renderRow)}
          </tbody>
          {totals && (
            <tfoot>
              <tr className="border-t border-zinc-700 bg-zinc-800/40 text-sm">
                <td colSpan={labelSpan} className="py-2 pl-4 pr-4 text-xs text-zinc-500">
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
                <td className="py-2 pr-4 text-right tabular-nums">
                  <BuyoutText amount={buyoutTotal ?? null} />
                </td>
                <td className="py-2 pr-4 text-right tabular-nums">
                  <CostText cost={totals.estimated_cost} />
                </td>
                <td className="py-2 pr-4 text-right tabular-nums">
                  <CreditsText credits={creditTotal ?? null} />
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
