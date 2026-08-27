import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";

import type { ModelPrice } from "../lib/api";
import { fetchMeta, fetchPricing, savePricing } from "../lib/api";
import { ErrorBlock, LoadingBlock } from "../components/states";

const EMPTY_PRICE: ModelPrice = { input: 0, output: 0, cache_read: 0, cache_write: 0 };

export default function Pricing() {
  const queryClient = useQueryClient();
  const tableQuery = useQuery({ queryKey: ["pricing"], queryFn: fetchPricing });
  const metaQuery = useQuery({ queryKey: ["meta"], queryFn: fetchMeta });

  const [rows, setRows] = useState<Record<string, ModelPrice>>({});
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  useEffect(() => {
    if (tableQuery.data) {
      const merged: Record<string, ModelPrice> = {};
      for (const [id, price] of Object.entries(tableQuery.data.models)) {
        merged[id] = { ...EMPTY_PRICE, ...price };
      }
      for (const model of metaQuery.data?.unpriced_models ?? []) {
        if (!(model in merged)) merged[model] = { ...EMPTY_PRICE };
      }
      setRows(merged);
    }
  }, [tableQuery.data, metaQuery.data]);

  const saveMutation = useMutation({
    mutationFn: () =>
      savePricing({
        version: tableQuery.data?.version ?? 1,
        models: Object.fromEntries(
          Object.entries(rows).filter(([id]) => id.trim() !== ""),
        ),
      }),
    onSuccess: () => {
      setNotice("价格已保存，总览与各视图成本已按新价格重算");
      setError(null);
      void queryClient.invalidateQueries();
    },
  });

  if (tableQuery.isLoading || metaQuery.isLoading) return <LoadingBlock />;
  if (tableQuery.isError) return <ErrorBlock error={tableQuery.error} />;
  if (metaQuery.isError) return <ErrorBlock error={metaQuery.error} />;

  const update = (id: string, field: keyof ModelPrice, value: string) => {
    const num = Number(value);
    setRows((prev) => ({
      ...prev,
      [id]: { ...prev[id]!, [field]: Number.isFinite(num) ? num : 0 },
    }));
  };

  const save = () => {
    const bad = Object.entries(rows).filter(
      ([id, p]) => id.trim() === "" || [p.input, p.output, p.cache_read, p.cache_write].some((v) => v < 0),
    );
    if (bad.length > 0) {
      setError(`以下条目无效：${bad.map(([id]) => id || "(空模型名)").join("、")}`);
      return;
    }
    saveMutation.mutate();
  };

  return (
    <div className="space-y-8">
      <p className="text-xs text-zinc-500">
        价格基准：<span className="text-zinc-300">USD / 1M tokens</span>（每百万 tokens 的美元价）。
        没有价格的模型只显示 token、不折算金额；全部模型有价后总览总额才会出现。
      </p>

      {(metaQuery.data?.unpriced_models.length ?? 0) > 0 && (
        <div className="rounded-lg border border-amber-800/50 bg-amber-950/30 px-5 py-3">
          <p className="text-sm text-amber-200">
            以下模型尚无价格（下方已自动补空行，可手填或截图识别）：
            {metaQuery.data!.unpriced_models.map((model) => (
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

      <div className="rounded-xl border border-zinc-800/80 bg-zinc-900/40 p-5">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-zinc-800 text-left text-xs text-zinc-500">
              <th className="py-2 pr-4 font-medium">模型</th>
              <th className="py-2 pr-4 text-right font-medium">输入 (USD/1M)</th>
              <th className="py-2 pr-4 text-right font-medium">输出 (USD/1M)</th>
              <th className="py-2 pr-4 text-right font-medium">缓存读 (USD/1M)</th>
              <th className="py-2 pr-4 text-right font-medium">缓存写 (USD/1M)</th>
              <th className="py-2 text-right font-medium">操作</th>
            </tr>
          </thead>
          <tbody>
            {Object.entries(rows).map(([id, price]) => (
              <tr key={id} className="border-b border-zinc-900">
                <td className="py-2 pr-4">
                  <input
                    value={id}
                    onChange={(e) => {
                      const next: Record<string, ModelPrice> = {};
                      for (const [oldId, p] of Object.entries(rows)) {
                        next[oldId === id ? e.target.value : oldId] = p;
                      }
                      setRows(next);
                    }}
                    className="w-52 rounded-md border border-zinc-800 bg-zinc-950 px-2 py-1 font-mono text-xs text-zinc-200"
                  />
                </td>
                {(["input", "output", "cache_read", "cache_write"] as const).map((field) => (
                  <td key={field} className="py-2 pr-4 text-right">
                    <input
                      type="number"
                      step="any"
                      min="0"
                      value={price[field]}
                      onChange={(e) => update(id, field, e.target.value)}
                      className="w-24 rounded-md border border-zinc-800 bg-zinc-950 px-2 py-1 text-right text-xs tabular-nums text-zinc-200"
                    />
                  </td>
                ))}
                <td className="py-2 text-right">
                  <button
                    type="button"
                    onClick={() => setRows((prev) => {
                      const next = { ...prev };
                      delete next[id];
                      return next;
                    })}
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
            onClick={() => setRows((prev) => ({ ...prev, "": { ...EMPTY_PRICE } }))}
            className="rounded-md border border-zinc-800 px-3 py-1.5 text-xs text-zinc-300 hover:bg-zinc-800"
          >
            + 新增模型
          </button>
          <button
            type="button"
            onClick={save}
            disabled={saveMutation.isPending}
            className="rounded-md bg-sky-600 px-4 py-1.5 text-xs font-medium text-white hover:bg-sky-500 disabled:opacity-50"
          >
            保存价格表
          </button>
          {error && <span className="text-xs text-rose-400">{error}</span>}
          {notice && <span className="text-xs text-emerald-400">{notice}</span>}
        </div>
      </div>
    </div>
  );
}