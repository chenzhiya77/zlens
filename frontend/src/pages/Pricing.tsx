import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";

import { ErrorBlock, LoadingBlock } from "../components/states";
import { aliasKey, displayName, getAliases, parseModelKey } from "../lib/alias";
import type { ExtractedPrice, ExtractResult, ModelPrice } from "../lib/api";
import { extractPricing, fetchMeta, fetchOverview, fetchPricing, savePricing } from "../lib/api";
import { formatCost } from "../lib/format";

export const PRICE_FIELDS = ["input", "output", "cache_read", "cache_write"] as const;

const EMPTY_PRICE: ModelPrice = {
  input: 0,
  output: 0,
  cache_read: 0,
  cache_write: 0,
  buyout_amount: null,
};

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
  const metaQuery = useQuery({ queryKey: ["meta"], queryFn: fetchMeta });
  // 「现总价」is derived, never stored: it is the same per-channel cost the overview
  // shows, read from the same endpoint, so editing a price here and the overview's
  // figure can never disagree.
  const usageQuery = useQuery({ queryKey: ["overview"], queryFn: fetchOverview });
  const [aliases] = useState(() => getAliases());

  const [rows, setRows] = useState<Record<string, ModelPrice>>({});
  const [fx, setFx] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [extracting, setExtracting] = useState(false);
  // Which row the next pasted screenshot targets: a screenshot is always
  // armed per channel, so recognition pre-fills that row only ("互不影响").
  const [pastingFor, setPastingFor] = useState<string | null>(null);
  const rowsRef = useRef(rows);
  rowsRef.current = rows;

  const fxValue = fx.trim() === "" || !Number.isFinite(Number(fx)) ? null : Number(fx);

  // Channel key -> what this row's unit prices currently add up to (null = the
  // channel has no unit price yet, or no usage has been seen for it).
  const costByKey = new Map<string, number | null>(
    (usageQuery.data?.by_model ?? []).map((m) => [
      aliasKey(m.source, m.provider_id, m.model_id),
      m.estimated_cost,
    ]),
  );

  const normId = (s: string) => s.trim().toLowerCase().replace(/\s+/g, " ");
  const lastSegment = (s: string) => normId(s.split("/").pop() ?? "");

  const matchesModel = (rowModelId: string, modelId: string) => {
    const a = normId(rowModelId);
    const b = normId(modelId);
    if (!a || !b) return false;
    if (a === b) return true;
    return lastSegment(rowModelId) !== "" && lastSegment(rowModelId) === lastSegment(modelId);
  };

  // Merge recognised numbers into the row, folding $ → ¥ first so only the newly
  // recognised fields are converted (the row's existing values are already CNY).
  const mergedPrice = (base: ModelPrice, m: ExtractedPrice, rate: number | null) => {
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
    const base = rowsRef.current[targetKey] ?? EMPTY_PRICE;
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
  useEffect(() => {
    if (!tableQuery.data || !metaQuery.data) return;
    const merged: Record<string, ModelPrice> = {};
    for (const [key, price] of Object.entries(tableQuery.data.models)) {
      merged[key] = { ...EMPTY_PRICE, ...price };
    }
    for (const key of metaQuery.data.unpriced_models) {
      if (!(key in merged)) merged[key] = { ...EMPTY_PRICE };
    }
    setRows(merged);
    setFx(tableQuery.data.fx_usd_cny?.toString() ?? "");
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
            .filter(([key]) => key.trim() !== "")
            .map(([key, price]) => [key, { ...EMPTY_PRICE, ...price }]),
        ),
      }),
    onSuccess: () => {
      setNotice("价格表已保存，成本已按新价格重算");
      setError(null);
      void queryClient.invalidateQueries();
    },
  });

  const update = (key: string, field: (typeof PRICE_FIELDS)[number], value: string) => {
    const num = Number(value);
    setRows((prev) => ({
      ...prev,
      [key]: {
        ...(prev[key] ?? EMPTY_PRICE),
        [field]: Number.isFinite(num) ? num : 0,
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
        ...(prev[key] ?? EMPTY_PRICE),
        buyout_amount: value.trim() === "" || !Number.isFinite(num) ? null : num,
      },
    }));
  };

  if (tableQuery.isLoading || metaQuery.isLoading) return <LoadingBlock />;
  if (tableQuery.isError) return <ErrorBlock error={tableQuery.error} />;
  if (metaQuery.isError) return <ErrorBlock error={metaQuery.error} />;

  const legacyCount = Object.keys(rows).filter((key) => !parseModelKey(key)).length;

  return (
    <div className="space-y-6">
      <p className="text-xs text-zinc-500">
        价格基准：<span className="text-zinc-300">人民币 ¥ / 1M tokens</span>
        （应用内只存人民币，行上不标币种）。一行一个渠道：同一个模型经不同渠道提供时价格
        可以不同，互不合并。没有价格的渠道只显示 token、不折算金额；全部渠道有价后总览总额
        才会出现。两笔钱分开记：<span className="text-zinc-300">现总价</span>
        是按已保存单价 × 该渠道用量算出的消耗（与总览同源，改完单价请保存才会刷新）；
        <span className="text-zinc-300">买断价 ¥</span>
        是你为套餐一次性付过的钱，不进按量计算、只汇总成总览的「买断支出」，两者永不相加。
        <span className="mx-2 text-zinc-700">|</span>
        <span className="text-zinc-400">
          美元价在录入时就折成人民币：识别到截图上是 $ 会按上方「1 美元 = ? 人民币」折算后再
          预填（汇率没填则拒绝预填，不替你猜市场价），截图没写币种就按人民币原样填、不乘任何汇率。
          手工抄的美元价请自己换算成人民币再填——zlens 认不出你敲的数字是美元还是人民币，所以不做
          行内折算，免得把本来就是人民币的行乘一遍汇率。每个渠道一行一个识别窗口：点击
          该行的「粘贴截图识别」，再在本页 Ctrl/Cmd+V 粘贴
          <em className="not-italic text-zinc-300">该渠道</em>的单价截图，识别结果只预填这一行、
          互不影响（请逐项核对后保存）。渠道行由用量自动列出，无需手工新建；行内只显示名字
          （有别名用别名），同名渠道去总览「别名」列起名区分，悬停行名可看完整
          source|provider_id|model_id 键。
        </span>
      </p>

      <div className="rounded-xl border border-zinc-800/80 bg-zinc-900 py-5">
        <div className="mb-4 flex items-center gap-2 px-5 text-xs text-zinc-400">
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
            {Object.entries(rows).map(([key, price]) => {
              const channel = parseModelKey(key);
              const name = channel
                ? displayName(aliases, channel.source, channel.providerId, channel.modelId)
                : "";
              const cost = costByKey.get(key);
              const costHint =
                cost === undefined
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
                        {name}
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
                        value={price[field]}
                        onChange={(e) => update(key, field, e.target.value)}
                        title={`${price[field]} ¥ / 1M tokens`}
                        className="w-full rounded-md border border-zinc-800 bg-zinc-950 px-2 py-1 text-right text-xs tabular-nums text-zinc-200"
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
            })}
          </tbody>
        </table>
        </div>

        <div className="mt-4 flex items-center gap-3 px-5">
          <button
            type="button"
            onClick={() => saveMutation.mutate()}
            disabled={saveMutation.isPending || extracting}
            className="rounded-md bg-sky-600 px-4 py-1.5 text-xs font-medium text-white hover:bg-sky-500 disabled:opacity-50"
          >
            保存价格表
          </button>
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
        </div>
      </div>
    </div>
  );
}
