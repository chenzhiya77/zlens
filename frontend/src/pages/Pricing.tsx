import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";

import { ErrorBlock, LoadingBlock } from "../components/states";
import { aliasKey, displayName, getAliases, parseModelKey } from "../lib/alias";
import type { ExtractedPrice, ExtractResult, ModelPrice } from "../lib/api";
import { extractPricing, fetchMeta, fetchOverview, fetchPricing, savePricing } from "../lib/api";
import { formatCost, formatTokens } from "../lib/format";

export const PRICE_FIELDS = ["input", "output", "cache_read", "cache_write"] as const;

/**
 * The editing state carries one more value than the wire type: a unit price is
 * either a number or 留空(null). 留空 means 「我不知道这个渠道多少钱」; 0 means
 * 「这个渠道按量免费」 and is a real price. They must never collapse into each
 * other — a row read as 0-priced is charged into the overview total as nothing,
 * which understates spend while looking fully priced.
 *
 * The backend has no per-row null: 未定价 is the key being absent from `models`
 * (cost.py `price_for` → None → tokens-only). So 留空 turns into 「不写这一行」 at
 * save time, which is the whole point of the nullable field.
 */
interface EditableRow {
  input: number | null;
  output: number | null;
  cache_read: number | null;
  cache_write: number | null;
  buyout_amount: number | null;
}

const EMPTY_ROW: EditableRow = {
  input: null,
  output: null,
  cache_read: null,
  cache_write: null,
  buyout_amount: null,
};

/** 填过任意一档(含 0)即已定价;四档全空 = 未定价,保存时不落库。 */
const isPriced = (row: EditableRow) => PRICE_FIELDS.some((field) => row[field] !== null);

/** 已落库却四档全 0:看着「有价格」,实际把总览合计算小了 —— 迁移条要揪出的就是它。 */
const isZeroPriced = (row: EditableRow) => PRICE_FIELDS.every((field) => row[field] === 0);

// A row that only carries a buyout amount still has to be written, because 买断支出
// is summed from stored rows. The wire type has no null unit price, so such a row
// goes out as 0-priced — the one place where 留空 cannot survive the round trip.
const toWire = (row: EditableRow): ModelPrice => ({
  input: row.input ?? 0,
  output: row.output ?? 0,
  cache_read: row.cache_read ?? 0,
  cache_write: row.cache_write ?? 0,
  buyout_amount: row.buyout_amount,
});

// Everything stored and displayed here is CNY — one currency, one state, no
// per-row labels to keep straight. The only conversion is automatic and happens
// on the way in: a recognised $ screenshot is folded at the user's own rate before
// it lands in the row. A hand-copied dollar price is folded by the human, in the
// number they type — zlens never guesses which rows are dollars, and a rate typed
// later must not quietly rewrite prices that were already CNY on purpose.
//
// Rows are keyed per channel ('source|provider_id|model_id', backend model_key), so
// the same model served through two channels is priced twice, never merged. A
// channel missing from the table is tokens-only. Row identity comes from the data —
// it is displayed, not typed, because a hand-written key can never match a usage
// row. Extraction only pre-fills the armed row; saving is always a human decision.
export default function Pricing() {
  const queryClient = useQueryClient();
  const tableQuery = useQuery({ queryKey: ["pricing"], queryFn: fetchPricing });
  const metaQuery = useQuery({ queryKey: ["meta"], queryFn: () => fetchMeta() });
  // 「现总价」is derived, never stored: it is the same per-channel cost the overview
  // shows, read from the same endpoint, so editing a price here and the overview's
  // figure can never disagree.
  const usageQuery = useQuery({ queryKey: ["overview"], queryFn: () => fetchOverview() });
  const [aliases] = useState(() => getAliases());

  const [rows, setRows] = useState<Record<string, EditableRow>>({});
  const [fx, setFx] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [extracting, setExtracting] = useState(false);
  // Which row the next pasted screenshot targets: a screenshot is always
  // armed per channel, so recognition pre-fills that row only ("互不影响").
  const [pastingFor, setPastingFor] = useState<string | null>(null);
  // 待补价 is the bulk of the table and carries no numbers; it starts folded so the
  // page opens on the channels that already have a price.
  const [showUnpriced, setShowUnpriced] = useState(false);
  // 视图筛选(画布④′):全部 = 分组队列原样;已定价 / 待补价 = 只渲染该组。
  const [viewFilter, setViewFilter] = useState<"all" | "priced" | "unpriced">("all");
  // 规则说明弹层(画布⑦):文字墙收进 ? 入口,一条规则不删。
  const [rulesOpen, setRulesOpen] = useState(false);
  // 脏计数快照(画布⑥):上次装载 / 保存成功时的 fx 与逐行值;保存按钮的
  // 「N 处未保存改动」由它与当前编辑态 diff 得出,替代「改完请保存」教学句。
  const [savedState, setSavedState] = useState<{ fx: string; rows: Record<string, EditableRow> }>({
    fx: "",
    rows: {},
  });
  const rowsRef = useRef(rows);
  rowsRef.current = rows;

  const fxValue = fx.trim() === "" || !Number.isFinite(Number(fx)) ? null : Number(fx);

  // Channel key -> what this row's unit prices currently add up to (null = the
  // channel has no unit price yet, or no usage has been seen for it). Tokens ride
  // along because 待补价 is ordered by what is actually burning.
  const costByKey = new Map<string, number | null>();
  const tokensByKey = new Map<string, number>();
  for (const m of usageQuery.data?.by_model ?? []) {
    const key = aliasKey(m.source, m.provider_id, m.model_id);
    costByKey.set(key, m.estimated_cost);
    tokensByKey.set(key, m.total_tokens);
  }

  const normId = (s: string) => s.trim().toLowerCase().replace(/\s+/g, " ");
  const lastSegment = (s: string) => normId(s.split("/").pop() ?? "");

  const matchesModel = (rowModelId: string, modelId: string) => {
    const a = normId(rowModelId);
    const b = normId(modelId);
    if (!a || !b) return false;
    if (a === b) return true;
    return lastSegment(rowModelId) !== "" && lastSegment(rowModelId) === lastSegment(modelId);
  };

  const nameOf = (key: string) => {
    const channel = parseModelKey(key);
    return channel
      ? displayName(aliases, channel.source, channel.providerId, channel.modelId)
      : key;
  };

  // Merge recognised numbers into the row, folding $ → ¥ first so only the newly
  // recognised fields are converted (the row's existing values are already CNY).
  const mergedPrice = (base: EditableRow, m: ExtractedPrice, rate: number | null) => {
    const fold = (value: number | null) =>
      value === null ? null : Math.round(value * (rate ?? 1) * 1e4) / 1e4;
    return {
      input: fold(m.input) ?? base.input,
      output: fold(m.output) ?? base.output,
      cache_read: fold(m.cache_read) ?? base.cache_read,
      cache_write: fold(m.cache_write) ?? base.cache_write,
      // Recognition reads unit prices only; a plan amount already entered stays put.
      buyout_amount: base.buyout_amount,
    };
  };

  // Apply recognition to one row only: the screenshot must actually contain this
  // channel's model name, otherwise every other row stays untouched and the user
  // is told what the screenshot held instead.
  const applyExtraction = (targetKey: string, result: ExtractResult) => {
    const channel = parseModelKey(targetKey);
    const recognized = result.models;
    if (!channel) {
      setError("这一行的键不是 source|provider_id|model_id 三元组，无法对应任何用量，请删除该行");
      setNotice(null);
      return;
    }
    if (recognized.length === 0) {
      setError("截图里没有识别到任何模型价格，请确认粘贴的是单价表格截图");
      setNotice(null);
      return;
    }
    const isUsd = result.currency === "usd";
    if (isUsd && fxValue === null) {
      setError(
        "截图是美元价，但汇率还没填 —— 请先在上方填「1 美元 = ? 人民币」再重新识别，zlens 不替你猜汇率",
      );
      setNotice(null);
      return;
    }
    const hit = recognized.find((m) => m.model_id && matchesModel(channel.modelId, m.model_id));
    if (!hit) {
      const names = recognized.map((m) => m.model_id || "(未命名)").join("、");
      setError(
        `截图未识别到「${channel.modelId}」的单价（图中识别到：${names}），请粘贴该渠道自己的截图`,
      );
      setNotice(null);
      return;
    }
    const base = rowsRef.current[targetKey] ?? EMPTY_ROW;
    const next = mergedPrice(base, hit, isUsd ? fxValue : null);
    setRows((prev) => ({ ...prev, [targetKey]: next }));
    const folded = isUsd
      ? `，截图为美元价，已按 1 USD = ${fxValue} 折算：` +
        PRICE_FIELDS.filter((field) => hit[field] !== null)
          .map((field) => `$${hit[field]}→¥${next[field]}`)
          .join("、")
      : result.currency === null
        ? "，截图未标明币种，按人民币原样预填（未乘任何汇率）；若图中其实是美元价，请自行按汇率改这四个数字"
        : "";
    setNotice(`已识别「${channel.modelId}」价格${folded}，只预填了本行，请核对后保存`);
    setError(null);
  };

  // Load the stored price table plus every channel that exists but has no price yet.
  // A channel absent from pricing.json loads blank, never as 0.
  useEffect(() => {
    if (!tableQuery.data || !metaQuery.data) return;
    const merged: Record<string, EditableRow> = {};
    for (const [key, price] of Object.entries(tableQuery.data.models)) {
      merged[key] = { ...EMPTY_ROW, ...price };
    }
    for (const key of metaQuery.data.unpriced_models) {
      if (!(key in merged)) merged[key] = { ...EMPTY_ROW };
    }
    setRows(merged);
    setFx(tableQuery.data.fx_usd_cny?.toString() ?? "");
    setSavedState({ fx: tableQuery.data.fx_usd_cny?.toString() ?? "", rows: merged });
  }, [tableQuery.data, metaQuery.data]);

  // A pasted screenshot only ever targets the armed row: click that row's paste
  // window first, then Ctrl/Cmd+V the price screenshot for that channel.
  useEffect(() => {
    if (pastingFor === null) return;
    const onPaste = (event: ClipboardEvent) => {
      const item = [...(event.clipboardData?.items ?? [])].find((i) =>
        i.type.startsWith("image/"),
      );
      const file = item?.getAsFile();
      if (!file) return;
      event.preventDefault();
      setExtracting(true);
      const reader = new FileReader();
      reader.onload = () => {
        const dataUrl = String(reader.result ?? "");
        const base64 = dataUrl.includes(",") ? dataUrl.split(",")[1]! : dataUrl;
        // The VLM only ever sees a model name, so focus on the model segment.
        extractPricing(base64, parseModelKey(pastingFor)?.modelId)
          .then((result) => applyExtraction(pastingFor, result))
          .catch((err) => {
            setError(err instanceof Error ? err.message : "识别失败");
            setNotice(null);
          })
          .finally(() => setExtracting(false));
      };
      reader.readAsDataURL(file);
    };
    window.addEventListener("paste", onPaste);
    return () => window.removeEventListener("paste", onPaste);
  }, [pastingFor]);

  const saveMutation = useMutation({
    mutationFn: () =>
      savePricing({
        version: tableQuery.data?.version ?? 1,
        fx_usd_cny: fxValue,
        models: Object.fromEntries(
          Object.entries(rows)
            .filter(
              ([key, row]) =>
                key.trim() !== "" && (isPriced(row) || row.buyout_amount !== null),
            )
            .map(([key, row]) => [key, toWire(row)]),
        ),
      }),
    onSuccess: () => {
      setNotice("价格表已保存，成本已按新价格重算");
      setError(null);
      setSavedState({ fx, rows: rowsRef.current });
      void queryClient.invalidateQueries();
    },
  });

  const update = (key: string, field: (typeof PRICE_FIELDS)[number], value: string) => {
    const num = Number(value);
    setRows((prev) => ({
      ...prev,
      [key]: {
        ...(prev[key] ?? EMPTY_ROW),
        [field]: value.trim() === "" || !Number.isFinite(num) ? null : num,
      },
    }));
  };

  // An empty buyout field means "this row is not a buyout" — keep it null instead of
  // turning it into a 0 that would read as a free plan.
  const updateBuyout = (key: string, value: string) => {
    const num = Number(value);
    setRows((prev) => ({
      ...prev,
      [key]: {
        ...(prev[key] ?? EMPTY_ROW),
        buyout_amount: value.trim() === "" || !Number.isFinite(num) ? null : num,
      },
    }));
  };

  // Rows already persisted with four 0s: they read as priced, so the overview total
  // counts them as free spend. Clearing them back to 留空 is the fix, but a row that
  // also carries a buyout amount must keep its row — paid money cannot vanish just
  // because its metered price is being corrected.
  const zeroPricedKeys = Object.entries(rows)
    .filter(
      ([key, row]) =>
        parseModelKey(key) !== null && isZeroPriced(row) && row.buyout_amount === null,
    )
    .map(([key]) => key);
  const zeroPricedWithBuyout = Object.entries(rows).filter(
    ([key, row]) =>
      parseModelKey(key) !== null && isZeroPriced(row) && row.buyout_amount !== null,
  ).length;

  const migrateZeroPriced = () => {
    const keys = new Set(zeroPricedKeys);
    setRows((prev) =>
      Object.fromEntries(
        Object.entries(prev).map(([key, row]) => [key, keys.has(key) ? { ...EMPTY_ROW } : row]),
      ),
    );
    setNotice(`已把 ${keys.size} 行改为未定价（保存后生效）：它们只展示 token，不再冒充 0 价`);
    setError(null);
  };

  if (tableQuery.isLoading || metaQuery.isLoading) return <LoadingBlock />;
  if (tableQuery.isError) return <ErrorBlock error={tableQuery.error} />;
  if (metaQuery.isError) return <ErrorBlock error={metaQuery.error} />;

  const legacyCount = Object.keys(rows).filter((key) => !parseModelKey(key)).length;

  // 队列而不是网格:已定价按金额降序常显,待补价按用量降序默认折叠 ——
  // 值得补价的那一行,就是正在烧 token 的那一行。
  const entries = Object.entries(rows);
  const byCost = (a: [string, EditableRow], b: [string, EditableRow]) =>
    (costByKey.get(b[0]) ?? -1) - (costByKey.get(a[0]) ?? -1) ||
    nameOf(a[0]).localeCompare(nameOf(b[0]));
  const byTokens = (a: [string, EditableRow], b: [string, EditableRow]) =>
    (tokensByKey.get(b[0]) ?? 0) - (tokensByKey.get(a[0]) ?? 0) ||
    nameOf(a[0]).localeCompare(nameOf(b[0]));
  const pricedRows = entries
    .filter(([key, row]) => parseModelKey(key) !== null && isPriced(row))
    .sort(byCost);
  const unpricedRows = entries
    .filter(([key, row]) => parseModelKey(key) !== null && !isPriced(row))
    .sort(byTokens);
  const legacyRows = entries.filter(([key]) => parseModelKey(key) === null);
  const unpricedTokens = unpricedRows.reduce((sum, [key]) => sum + (tokensByKey.get(key) ?? 0), 0);
  const pricedTotal = pricedRows.reduce((sum, [key]) => sum + (costByKey.get(key) ?? 0), 0);

  const groupRow = (
    label: string,
    summary: string,
    toggle?: () => void,
    open?: boolean,
  ) => (
    <tr>
      <td colSpan={10} className="bg-zinc-950/50 p-0">
        {/* 吸附必须落在 max-content 宽度的子元素上:整格与表格同宽,sticky 推不动它,
            窄屏横滚时分组标题会滚出可视区并被吸附列盖住。 */}
        <div className="sticky left-0 w-max max-w-full py-1.5 pl-5 pr-5">
          {toggle ? (
            <button
              type="button"
              onClick={toggle}
              className="flex items-baseline gap-2 text-left text-[11px] text-zinc-500 hover:text-zinc-300"
            >
              <span className="w-3 font-mono text-zinc-600">{open ? "▾" : "▸"}</span>
              <span className="font-medium text-zinc-400">{label}</span>
              <span className="text-zinc-600">{summary}</span>
            </button>
          ) : (
            <div className="flex items-baseline gap-2 text-[11px]">
              <span className="font-medium text-zinc-400">{label}</span>
              <span className="text-zinc-600">{summary}</span>
            </div>
          )}
        </div>
      </td>
    </tr>
  );

  const renderRow = ([key, price]: [string, EditableRow]) => {
    const channel = parseModelKey(key);
    const cost = costByKey.get(key);
    const costHint = !isPriced(price)
      ? "该行未定价：只展示 token，不折算金额"
      : cost === undefined
        ? "该渠道还没有用量记录"
        : cost === null
          ? "该行未填单价，无法折算"
          : "按已保存的单价估算，与总览同源";
    return (
      <tr key={key} className="border-b border-zinc-800/60">
        <td className="sticky left-0 z-10 bg-zinc-900 py-2 pl-5 pr-2">
          {channel ? (
            <span className="rounded bg-zinc-800 px-1.5 py-0.5 font-mono text-[11px] text-zinc-400">
              {channel.source}
            </span>
          ) : (
            <span className="font-mono text-[11px] text-zinc-600">—</span>
          )}
        </td>
        <td className="sticky left-28 z-10 border-r border-zinc-800/60 bg-zinc-900 py-2 pr-4">
          {channel ? (
            <div
              className="truncate font-mono text-xs text-zinc-200"
              title={`${key}\n模型 ${channel.modelId} · 渠道 ${channel.providerId}`}
            >
              {nameOf(key)}
            </div>
          ) : (
            <div className="min-w-0">
              <div className="truncate font-mono text-xs text-amber-300" title={key}>
                {key}
              </div>
              <div className="truncate text-[10px] text-amber-400/80">
                旧格式键：匹配不到渠道，请删除
              </div>
            </div>
          )}
        </td>
        <td className="py-2 pr-4">
          <button
            type="button"
            onClick={() => {
              setPastingFor((cur) => (cur === key ? null : key));
              setError(null);
              setNotice(null);
            }}
            title="点击后把该行设为识别目标，再在本页按 Ctrl+V（macOS 为 ⌘V）粘贴该渠道单价截图；识别结果只预填这一行"
            className={`whitespace-nowrap rounded-md border border-dashed px-3 py-1 text-[11px] font-mono transition-colors ${
              pastingFor === key
                ? "border-sky-500/80 bg-sky-500/10 text-sky-400"
                : "border-zinc-600 text-zinc-500 hover:border-sky-500/70 hover:text-sky-400"
            }`}
          >
            {pastingFor === key
              ? extracting
                ? "正在识别…"
                : "Ctrl+V 粘贴"
              : "粘贴截图识别"}
          </button>
        </td>
        {PRICE_FIELDS.map((field) => (
          <td key={field} className="py-2 pr-4 text-right">
            <input
              type="number"
              step="any"
              min="0"
              value={price[field] ?? ""}
              onChange={(e) => update(key, field, e.target.value)}
              title={
                price[field] === null
                  ? "未填 —— 四档都留空的行视为未定价，只展示 token；敲 0 才是「按量免费」"
                  : `${price[field]} ¥ / 1M tokens`
              }
              className={`w-full rounded-md border bg-zinc-950 px-2 py-1 text-right text-xs tabular-nums text-zinc-200 ${
                price[field] === null ? "border-dashed border-zinc-700" : "border-zinc-800"
              }`}
            />
          </td>
        ))}
        <td className="py-2 pr-4 text-right">
          <input
            type="number"
            step="any"
            min="0"
            value={price.buyout_amount ?? ""}
            onChange={(e) => updateBuyout(key, e.target.value)}
            placeholder="—"
            title="一次性买断/套餐付款金额（人民币），留空表示这行不是买断；不参与按量计算"
            className="w-full rounded-md border border-zinc-800 bg-zinc-950 px-2 py-1 text-right text-xs tabular-nums text-zinc-200"
          />
        </td>
        <td
          className="w-20 py-2 pr-4 text-right text-xs tabular-nums text-zinc-400"
          title={costHint}
        >
          {cost === null || cost === undefined ? "—" : formatCost(cost)}
        </td>
        <td className="py-2 pr-5 text-right">
          <button
            type="button"
            onClick={() =>
              setRows((prev) => {
                const updated = { ...prev };
                delete updated[key];
                return updated;
              })
            }
            className="rounded-md px-2 py-1 text-xs text-zinc-500 hover:bg-zinc-800 hover:text-zinc-300"
          >
            删除
          </button>
        </td>
      </tr>
    );
  };

  // ⑥ 脏计数:与快照逐行比较,行键的增 / 删 / 改各算一处,fx 变更单独算一处。
  // 行对象编辑时总是整体替换,逐行 JSON 比较即逐字段比较,与键序无关。
  const dirtyCount = (() => {
    let count = 0;
    const keys = new Set([...Object.keys(rows), ...Object.keys(savedState.rows)]);
    for (const key of keys) {
      if (JSON.stringify(rows[key]) !== JSON.stringify(savedState.rows[key])) count += 1;
    }
    if (fx !== savedState.fx) count += 1;
    return count;
  })();

  return (
    <div className="space-y-4">
      {/* 页头(画布⑦):一行摘要 + ? 弹层。界面已表达的不变量不再用文字墙复述,
          但弹层完整收纳——规则一条不删,README / AGENTS 仍是事实源。 */}
      <div className="relative flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold tracking-tight">价格表</h1>
          <p className="mt-1 text-xs text-zinc-500">
            人民币 ¥ / 1M tokens · 一行一个渠道 ·{" "}
            <span className="text-zinc-300">四档全留空 = 未定价</span> · 用到的渠道都有价后总览总额
            才会出现
          </p>
        </div>
        <button
          type="button"
          aria-label="计价规则说明"
          aria-expanded={rulesOpen}
          onClick={() => setRulesOpen((cur) => !cur)}
          className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full border border-zinc-800 text-xs text-zinc-500 hover:border-zinc-700 hover:text-zinc-300"
        >
          ?
        </button>
        {rulesOpen && (
          <>
            <div className="fixed inset-0 z-10" onClick={() => setRulesOpen(false)} />
            <div className="absolute right-0 top-full z-20 mt-2 w-[560px] space-y-3 rounded-xl border border-zinc-800 bg-zinc-900 p-4 text-xs leading-relaxed text-zinc-500 shadow-xl">
              <p>
                <span className="font-medium text-zinc-300">计价。</span>
                价格基准:人民币 ¥ / 1M tokens(应用内只存人民币,行上不标币种)。一行一个渠道:
                同一个模型经不同渠道提供时价格可以不同,互不合并。四档全留空 = 未定价,该渠道只显示
                token、不折算金额;敲 0 才是「按量免费」。两笔钱分开记:现总价 = 已保存单价 ×
                该渠道用量(与总览同源,保存后刷新);买断价是你为套餐一次性付过的钱,不进按量计算、
                只汇总成总览的「买断支出」,两者永不相加。
              </p>
              <p>
                <span className="font-medium text-zinc-300">美元与汇率。</span>
                美元价在录入时折成人民币:识别到截图上是 $ 会按「1 美元 = ? 人民币」折算后再预填
                (汇率没填则拒绝预填,不替你猜市场价);截图没写币种就按人民币原样填、不乘任何汇率。
                手工抄的美元价请自己换算成人民币再填——zlens 认不出你敲的数字是美元还是人民币,
                所以不做行内折算,免得把本来就是人民币的行乘一遍汇率。汇率只在录入期使用,不参与
                成本计算。
              </p>
              <p>
                <span className="font-medium text-zinc-300">识别与渠道行。</span>
                每个渠道一行一个识别窗口:点击该行的「粘贴截图识别」,再在本页 Ctrl/Cmd+V 粘贴
                <em className="not-italic text-zinc-300">该渠道</em>的单价截图,识别结果只预填这一行、
                互不影响(请逐项核对后保存)。渠道行由用量自动列出,无需手工新建;行内只显示名字
                (有别名用别名),同名渠道去总览「别名」列起名区分,悬停行名可看完整
                source|provider_id|model_id 键。
              </p>
            </div>
          </>
        )}
      </div>

      {zeroPricedKeys.length > 0 && (
        <div className="flex items-center gap-3 rounded-lg border border-amber-500/40 bg-amber-500/10 px-3 py-2 text-xs">
          <span className="text-amber-300">
            {zeroPricedKeys.length} 个渠道已落库但四档全是 0 —— 它们会被当成「有价格」，
            把总览的合计金额算小。改成未定价后只展示 token。
          </span>
          {zeroPricedWithBuyout > 0 && (
            <span className="shrink-0 text-amber-400/70">
              另有 {zeroPricedWithBuyout} 行四档为 0 但带买断额，保留不动。
            </span>
          )}
          <button
            type="button"
            onClick={migrateZeroPriced}
            className="ml-auto shrink-0 rounded-md border border-amber-500/60 px-3 py-1 text-amber-300 hover:bg-amber-500/15"
          >
            全部改为未定价
          </button>
        </div>
      )}

      <div className="rounded-xl border border-zinc-800/80 bg-zinc-900 pt-5">
        <div className="mb-4 flex flex-wrap items-center justify-between gap-2 px-5 text-xs text-zinc-400">
          <div className="flex items-center gap-2">
            <label htmlFor="fx">汇率 1 美元 =</label>
            <input
              id="fx"
              type="number"
              step="any"
              min="0"
              value={fx}
              onChange={(e) => setFx(e.target.value)}
              placeholder="未设置"
              className="w-24 rounded-md border border-zinc-800 bg-zinc-950 px-2 py-1 text-right text-xs tabular-nums text-zinc-200"
            />
            <span className="text-zinc-500">
              人民币；只用来折算识别到的美元截图，不参与成本计算
            </span>
          </div>
          {/* 视图筛选(画布④′):计数与分组头一致;旧格式键归入待补价——它们同样
              等着人处理。筛选只决定渲染哪些组,不碰任何数据。 */}
          <div className="flex items-center gap-1.5">
            <span className="text-zinc-600">视图</span>
            {(
              [
                ["all", `全部 ${pricedRows.length + unpricedRows.length + legacyRows.length}`],
                ["priced", `已定价 ${pricedRows.length}`],
                ["unpriced", `待补价 ${unpricedRows.length + legacyRows.length}`],
              ] as const
            ).map(([key, label]) => (
              <button
                key={key}
                type="button"
                onClick={() => setViewFilter(key)}
                className={`rounded-md border px-2.5 py-1 transition-colors ${
                  viewFilter === key
                    ? "border-sky-500/40 bg-sky-500/10 text-sky-400"
                    : "border-zinc-800 text-zinc-400 hover:text-zinc-200"
                }`}
              >
                {label}
              </button>
            ))}
          </div>
        </div>

        {/* 卡片宽度不再被表格顶穿:表格在自己的壳里横滚,列宽固定(table-fixed),
            价格列均分剩下的宽度,收到 min-w 底线后才出现壳内滚动条。
            来源与渠道名各自成列(与总览/按项目同构),两列一起吸附在左侧——
            横滚时仍然认得出这一行是给谁定价。 */}
        <div className="overflow-x-auto">
          <table className="w-full min-w-[920px] table-fixed text-sm">
            <thead>
              <tr className="border-b border-zinc-800 text-left text-xs text-zinc-500">
                <th className="sticky left-0 z-10 w-28 bg-zinc-900 py-2 pl-5 pr-2 font-medium">
                  来源
                </th>
                <th
                  className="sticky left-28 z-10 w-56 border-r border-zinc-800/60 bg-zinc-900 py-2 pr-4 font-medium"
                  title="行名悬停可看完整渠道键;同名渠道请在总览「别名」列起名区分"
                >
                  渠道名
                </th>
                <th
                  className="w-28 py-2 pr-4 font-medium"
                  title="识别到截图上是美元价，会按上方「1 美元 = ? 人民币」自动折成人民币再预填（汇率没填则拒绝预填）；截图没写币种就按人民币原样填。手工抄的美元价请自己换算后填人民币数字"
                >
                  识别<span className="ml-1 font-mono text-[10px] text-zinc-600">($→¥)</span>
                </th>
                <th className="py-2 pr-4 text-right font-medium">输入 /1M</th>
                <th className="py-2 pr-4 text-right font-medium">输出 /1M</th>
                <th className="py-2 pr-4 text-right font-medium">缓存读 /1M</th>
                <th className="py-2 pr-4 text-right font-medium">缓存写 /1M</th>
                <th
                  className="py-2 pr-4 text-right font-medium"
                  title="为这个渠道一次性买断/买套餐付的钱（人民币）。留空表示这行不是买断；它不参与按量计算，只汇总成总览的「买断支出」"
                >
                  买断价 ¥
                </th>
                <th
                  className="w-20 py-2 pr-4 text-right font-medium"
                  title="按已保存的本行单价 × 该渠道已发生的用量算出，与总览同源、不可编辑（改完单价请保存）。— 表示该行还没有单价，或该渠道还没有用量"
                >
                  现总价
                </th>
                <th className="w-16 py-2 pr-5 text-right font-medium">操作</th>
              </tr>
            </thead>
            <tbody>
              {viewFilter !== "unpriced" &&
                pricedRows.length > 0 &&
                groupRow("已定价", `${pricedRows.length} 个渠道 · 合计 ${formatCost(pricedTotal)}`)}
              {viewFilter !== "unpriced" && pricedRows.map(renderRow)}
              {viewFilter !== "priced" &&
                unpricedRows.length > 0 &&
                groupRow(
                  "待补价",
                  `${unpricedRows.length} 个渠道未定价 · 合计 ${formatTokens(unpricedTokens)} tokens 未折算${
                    viewFilter === "all" && !showUnpriced ? " · 点击展开" : ""
                  }`,
                  viewFilter === "all" ? () => setShowUnpriced((cur) => !cur) : undefined,
                  viewFilter !== "all",
                )}
              {(viewFilter === "unpriced" || (viewFilter === "all" && showUnpriced)) &&
                unpricedRows.map(renderRow)}
              {viewFilter !== "priced" &&
                legacyRows.length > 0 &&
                groupRow("旧格式键", `${legacyRows.length} 行匹配不到渠道`)}
              {viewFilter !== "priced" && legacyRows.map(renderRow)}
            </tbody>
          </table>
        </div>

        {/* 底部操作条(画布⑤⑥):左「两笔钱」并排、永不相加,数字全部来自
            /api/overview(未计价/未填如实显示,不重算);右保存带脏计数,
            「改完单价请保存才会刷新」由「N 处未保存改动」状态替代。 */}
        <div className="mt-4 flex flex-wrap items-center gap-x-4 gap-y-2 border-t border-zinc-800/80 px-5 py-4">
          <div className="flex items-baseline gap-2">
            <span className="text-xs text-zinc-500">按量消耗</span>
            <span className="text-sm font-medium tabular-nums text-zinc-200">
              {usageQuery.data?.totals == null
                ? "—"
                : usageQuery.data.totals.estimated_cost === null
                  ? "未计价"
                  : formatCost(usageQuery.data.totals.estimated_cost)}
            </span>
            <span className="mx-1 h-4 w-px bg-zinc-800" />
            <span className="text-xs text-zinc-500">买断支出</span>
            <span className="text-sm font-medium tabular-nums text-zinc-200">
              {usageQuery.data == null
                ? "—"
                : usageQuery.data.buyout_total === null
                  ? "未填"
                  : usageQuery.data.buyout_total === 0
                    ? "¥0.00 · 免费套餐"
                    : formatCost(usageQuery.data.buyout_total)}
            </span>
            <span className="text-[10px] text-zinc-600">两笔钱永不相加</span>
          </div>
          <div className="ml-auto flex flex-wrap items-center gap-3">
            {legacyCount > 0 && (
              <button
                type="button"
                onClick={() =>
                  setRows((prev) =>
                    Object.fromEntries(Object.entries(prev).filter(([key]) => parseModelKey(key))),
                  )
                }
                title="旧的价格表以裸 model_id 为键，匹配不到任何渠道；清除后保存即可只保留渠道行"
                className="rounded-md border border-amber-500/50 px-3 py-1.5 text-xs text-amber-400 hover:bg-amber-500/10"
              >
                清除 {legacyCount} 行旧格式键
              </button>
            )}
            {extracting && <span className="text-xs text-zinc-500">正在调用 VLM 识别截图…</span>}
            {saveMutation.isError && (
              <span className="text-xs text-rose-400">
                {saveMutation.error instanceof Error ? saveMutation.error.message : "保存失败"}
              </span>
            )}
            {error && <span className="text-xs text-rose-400">{error}</span>}
            {notice && <span className="text-xs text-emerald-400">{notice}</span>}
            {dirtyCount > 0 && (
              <span className="text-xs text-amber-400">{dirtyCount} 处未保存改动</span>
            )}
            <button
              type="button"
              onClick={() => saveMutation.mutate()}
              disabled={saveMutation.isPending || extracting}
              className="rounded-md bg-sky-600 px-4 py-1.5 text-xs font-medium text-white hover:bg-sky-500 disabled:opacity-50"
            >
              {dirtyCount > 0 ? `保存 ${dirtyCount} 处改动` : "保存价格表"}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
