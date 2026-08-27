import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";

import { ErrorBlock, LoadingBlock } from "../components/states";
import type { ExtractResult, ModelPrice } from "../lib/api";
import { extractPricing, fetchMeta, fetchPricing, savePricing } from "../lib/api";

export const PRICE_FIELDS = ["input", "output", "cache_read", "cache_write"] as const;

const EMPTY_PRICE: ModelPrice = { input: 0, output: 0, cache_read: 0, cache_write: 0 };

// Prices are USD per 1M tokens, per model and per tier (input / output /
// cache read / cache write). A model missing from the table is tokens-only.
// Screenshot extraction only pre-fills the form — saving is always a human
// decision (an unparsed/wrong screenshot must never write bad prices).
export default function Pricing() {
  const queryClient = useQueryClient();
  const tableQuery = useQuery({ queryKey: ["pricing"], queryFn: fetchPricing });
  const metaQuery = useQuery({ queryKey: ["meta"], queryFn: fetchMeta });

  const [rows, setRows] = useState<Record<string, ModelPrice>>({});
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [extracting, setExtracting] = useState(false);
  // Which row the next pasted screenshot targets: a screenshot is always
  // armed per model, so recognition pre-fills that row only ("互不影响").
  const [pastingFor, setPastingFor] = useState<string | null>(null);
  const rowsRef = useRef(rows);
  rowsRef.current = rows;

  const normId = (s: string) => s.trim().toLowerCase();
  const lastSegment = (s: string) => normId(s.trim().split("/").pop() ?? "");

  const matchesModel = (rowId: string, modelId: string) => {
    const a = normId(rowId).replace(/\s+/g, " ");
    const b = normId(modelId).replace(/\s+/g, " ");
    if (!a || !b) return false;
    if (a === b) return true;
    const sa = lastSegment(rowId).replace(/\s+/g, " ");
    return sa !== "" && sa === lastSegment(modelId).replace(/\s+/g, " ");
  };

  const mergedPrice = (base: ModelPrice, m: ExtractResult["models"][number]) => ({
    input: m.input ?? base.input,
    output: m.output ?? base.output,
    cache_read: m.cache_read ?? base.cache_read,
    cache_write: m.cache_write ?? base.cache_write,
  });

  // Apply recognition to one row only: a placeholder row adopts the first
  // recognized model (which creates the row); a real row is filled only when
  // the screenshot actually contains its id — other rows stay untouched.
  const applyExtraction = (targetId: string, result: ExtractResult) => {
    const recognized = result.models;
    const prev = rowsRef.current;
    if (recognized.length === 0) {
      setError("截图里没有识别到任何模型价格，请确认粘贴的是单价表格截图");
      setNotice(null);
      return;
    }
    const isPlaceholder = targetId.trim() === "" || targetId === "new-model";
    if (isPlaceholder) {
      const existing = new Set(Object.keys(prev).map(normId));
      const adopt =
        recognized.find((m) => m.model_id && !existing.has(normId(m.model_id))) ??
        recognized[0];
      if (!adopt?.model_id) {
        setError("截图未识别到模型名，无法新建行，请手动填写或新建后重试");
        setNotice(null);
        return;
      }
      const next = { ...prev };
      delete next[targetId];
      next[adopt.model_id] = mergedPrice(EMPTY_PRICE, adopt);
      setRows(next);
      setNotice(`已识别「${adopt.model_id}」并新建该行，请核对后保存`);
      setError(null);
      return;
    }
    const hit = recognized.find((m) => m.model_id && matchesModel(targetId, m.model_id));
    if (!hit) {
      const names = recognized.map((m) => m.model_id || "(未命名)").join("、");
      setError(`截图未识别到「${targetId}」的单价（图中识别到：${names}），请粘贴该模型自己的截图`);
      setNotice(null);
      return;
    }
    setRows({ ...prev, [targetId]: mergedPrice(prev[targetId] ?? EMPTY_PRICE, hit) });
    setNotice(`已识别「${targetId}」价格，只预填了本行，请核对后保存`);
    setError(null);
  };

  // Load the stored price table plus any models that exist but have no price yet.
  useEffect(() => {
    if (!tableQuery.data || !metaQuery.data) return;
    const merged: Record<string, ModelPrice> = {};
    for (const [modelId, price] of Object.entries(tableQuery.data.models)) {
      merged[modelId] = { ...EMPTY_PRICE, ...price };
    }
    for (const modelId of metaQuery.data.unpriced_models) {
      if (!(modelId in merged)) merged[modelId] = { ...EMPTY_PRICE };
    }
    setRows(merged);
  }, [tableQuery.data, metaQuery.data]);

  // A pasted screenshot only ever targets the armed row: click a row's paste
  // window first, then Ctrl/Cmd+V the price screenshot for that model. The
  // recognition result pre-fills that one row; other rows stay untouched.
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
        extractPricing(base64, pastingFor)
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
        models: Object.fromEntries(
          Object.entries(rows)
            .filter(([modelId]) => modelId.trim() !== "")
            .map(([modelId, price]) => [modelId, { ...EMPTY_PRICE, ...price }]),
        ),
      }),
    onSuccess: () => {
      setNotice("价格表已保存，成本已按新价格重算");
      setError(null);
      void queryClient.invalidateQueries();
    },
  });

  const update = (modelId: string, field: (typeof PRICE_FIELDS)[number], value: string) => {
    const num = Number(value);
    setRows((prev) => ({
      ...prev,
      [modelId]: {
        ...(prev[modelId] ?? EMPTY_PRICE),
        [field]: Number.isFinite(num) ? num : 0,
      },
    }));
  };

  if (tableQuery.isLoading || metaQuery.isLoading) return <LoadingBlock />;
  if (tableQuery.isError) return <ErrorBlock error={tableQuery.error} />;
  if (metaQuery.isError) return <ErrorBlock error={metaQuery.error} />;

  return (
    <div className="space-y-6">
      <p className="text-xs text-zinc-500">
        价格基准：<span className="text-zinc-300">USD / 1M tokens</span>（每百万 token 的美元价）。
        没有价格的模型只显示 token、不折算金额；全部模型有价后总览总额才会出现。
        <span className="mx-2 text-zinc-700">|</span>
        <span className="text-zinc-400">
          每个模型一行一个识别窗口：点击该行的「粘贴截图识别」，再在本页
          Ctrl/Cmd+V 粘贴<em className="not-italic text-zinc-300">该模型</em>的单价截图，
          识别结果只预填这一行、互不影响（请逐项核对后保存；新模型行会按截图自动起名）。
        </span>
      </p>

      <div className="rounded-xl border border-zinc-800/80 bg-zinc-900/40 p-5">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-zinc-800 text-left text-xs text-zinc-500">
              <th className="py-2 pr-4 font-medium">模型</th>
              <th className="py-2 pr-4 font-medium">识别</th>
              <th className="py-2 pr-4 text-right font-medium">输入 (USD/1M)</th>
              <th className="py-2 pr-4 text-right font-medium">输出 (USD/1M)</th>
              <th className="py-2 pr-4 text-right font-medium">缓存读 (USD/1M)</th>
              <th className="py-2 pr-4 text-right font-medium">缓存写 (USD/1M)</th>
              <th className="py-2 text-right font-medium">操作</th>
            </tr>
          </thead>
          <tbody>
            {Object.entries(rows).map(([modelId, price]) => (
              <tr key={modelId} className="border-b border-zinc-900">
                <td className="py-2 pr-4">
                  <input
                    value={modelId}
                    onChange={(e) => {
                      const next = e.target.value;
                      setRows((prev) => {
                        const updated: Record<string, ModelPrice> = {};
                        for (const [id, p] of Object.entries(prev)) {
                          updated[id === modelId ? next : id] = p;
                        }
                        return updated;
                      });
                    }}
                    className="w-64 rounded-md border border-zinc-800 bg-zinc-950 px-2 py-1 font-mono text-xs text-zinc-200"
                  />
                </td>
                <td className="py-2 pr-4">
                  <button
                    type="button"
                    onClick={() => {
                      setPastingFor((cur) => (cur === modelId ? null : modelId));
                      setError(null);
                      setNotice(null);
                    }}
                    title="点击后把该行设为识别目标，再在本页 Ctrl/Cmd+V 粘贴该模型单价截图；识别结果只预填这一行"
                    className={`rounded-md border border-dashed px-3 py-1 text-[11px] font-mono transition-colors ${
                      pastingFor === modelId
                        ? "border-sky-500/80 bg-sky-500/10 text-sky-400"
                        : "border-zinc-600 text-zinc-500 hover:border-sky-500/70 hover:text-sky-400"
                    }`}
                  >
                    {pastingFor === modelId
                      ? extracting
                        ? "正在识别…"
                        : "已就绪：Ctrl/Cmd+V 粘贴"
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
                      onChange={(e) => update(modelId, field, e.target.value)}
                      className="w-24 rounded-md border border-zinc-800 bg-zinc-950 px-2 py-1 text-right text-xs tabular-nums text-zinc-200"
                    />
                  </td>
                ))}
                <td className="py-2 text-right">
                  <button
                    type="button"
                    onClick={() =>
                      setRows((prev) => {
                        const updated = { ...prev };
                        delete updated[modelId];
                        return updated;
                      })
                    }
                    className="rounded-md px-2 py-1 text-xs text-zinc-500 hover:bg-zinc-800 hover:text-zinc-300"
                  >
                    删除
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>

        <div className="mt-4 flex items-center gap-3">
          <button
            type="button"
            onClick={() => setRows((prev) => ({ ...prev, ["new-model"]: { ...EMPTY_PRICE } }))}
            className="rounded-md border border-zinc-800 px-3 py-1.5 text-xs text-zinc-300 hover:bg-zinc-800"
          >
            + 新增模型
          </button>
          <button
            type="button"
            onClick={() => saveMutation.mutate()}
            disabled={saveMutation.isPending || extracting}
            className="rounded-md bg-sky-600 px-4 py-1.5 text-xs font-medium text-white hover:bg-sky-500 disabled:opacity-50"
          >
            保存价格表
          </button>
          {extracting && <span className="text-xs text-zinc-500">正在调用 VLM 识别截图…</span>}
          {error && <span className="text-xs text-rose-400">{error}</span>}
          {notice && <span className="text-xs text-emerald-400">{notice}</span>}
        </div>
      </div>
    </div>
  );
}