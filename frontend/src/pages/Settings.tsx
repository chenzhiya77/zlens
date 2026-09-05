import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";

import { ErrorBlock, LoadingBlock } from "../components/states";
import {
  captureCreditRates,
  fetchCreditRates,
  fetchVlmSettings,
  saveVlmSettings,
  testVlm,
} from "../lib/api";
import { formatDateTime } from "../lib/format";
import {
  ACCENT_OPTIONS,
  getAccent,
  getMode,
  setAccent,
  setMode,
  type AccentId,
  type ThemeMode,
} from "../lib/theme";

/**
 * VLM settings page: the model used to read price screenshots. API keys are
 * secrets — they are stored only in the gitignored local config file and the
 * API never echoes them back.
 */
export default function Settings() {
  const queryClient = useQueryClient();
  const query = useQuery({ queryKey: ["vlm-settings"], queryFn: fetchVlmSettings });
  const ratesQuery = useQuery({ queryKey: ["credit-rates"], queryFn: fetchCreditRates });

  const [baseUrl, setBaseUrl] = useState("");
  const [model, setModel] = useState("");
  const [apiKey, setApiKey] = useState("");
  const [result, setResult] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [mode, setModeState] = useState<ThemeMode>(getMode());
  const [accent, setAccentState] = useState<AccentId>(getAccent());

  useEffect(() => {
    if (query.data) {
      setBaseUrl(query.data.base_url);
      setModel(query.data.model);
    }
  }, [query.data]);

  const saveMutation = useMutation({
    mutationFn: () =>
      saveVlmSettings({
        base_url: baseUrl || undefined,
        model: model || undefined,
        api_key: apiKey || undefined, // empty = keep stored key; never send it back
      }),
    onSuccess: () => {
      setApiKey("");
      setResult("已保存（密钥仅存本机配置文件）");
      setError(null);
      void queryClient.invalidateQueries({ queryKey: ["vlm-settings"] });
    },
  });

  const testMutation = useMutation({
    mutationFn: () => testVlm(),
    onSuccess: (data) => {
      setResult(data.ok ? `连接成功：${data.reply}` : "连接测试未返回成功");
      setError(null);
    },
    onError: (err) => {
      setError(err instanceof Error ? err.message : "连接测试失败");
      setResult(null);
    },
  });

  const ratesMutation = useMutation({
    mutationFn: captureCreditRates,
    onSuccess: () => {
      setError(null);
      void queryClient.invalidateQueries({ queryKey: ["credit-rates"] });
    },
    onError: (err) => {
      setError(err instanceof Error ? err.message : "抓取失败");
    },
  });

  const handleTest = () => {
    if (!query.data?.api_key_configured) {
      setError("尚未配置 VLM API Key：请先填写并保存 VLM 配置，再测试连接。");
      setResult(null);
      return;
    }
    testMutation.mutate();
  };

  if (query.isLoading) return <LoadingBlock />;
  if (query.isError) return <ErrorBlock error={query.error} />;

  return (
    <div className="max-w-2xl space-y-6">
      <div className="rounded-xl border border-zinc-800/80 bg-zinc-900 p-5">
        <div className="space-y-5">
          <div>
            <label className="mb-1.5 block text-xs text-zinc-500">
              外观（当前主题偏深，可切换浅色）
            </label>
            <div className="flex gap-2">
              {(["dark", "light"] as const).map((m) => (
                <button
                  key={m}
                  type="button"
                  onClick={() => {
                    setModeState(m);
                    setMode(m);
                  }}
                  className={`rounded-md border px-3 py-1.5 text-xs transition-colors ${
                    mode === m
                      ? "border-sky-500/70 bg-sky-500/10 text-sky-400"
                      : "border-zinc-700/70 text-zinc-500 hover:border-zinc-600 hover:text-zinc-300"
                  }`}
                >
                  {m === "dark" ? "深色（默认）" : "浅色"}
                </button>
              ))}
            </div>
          </div>
          <div>
            <label className="mb-1.5 block text-xs text-zinc-500">主题色</label>
            <div className="flex items-center gap-2.5">
              {ACCENT_OPTIONS.map((option) => (
                <button
                  key={option.id}
                  type="button"
                  title={option.label}
                  aria-label={option.label}
                  aria-pressed={accent === option.id}
                  onClick={() => {
                    setAccentState(option.id);
                    setAccent(option.id);
                  }}
                  className={`h-7 w-7 rounded-full transition-transform hover:scale-110 ${
                    accent === option.id
                      ? "ring-2 ring-sky-400 ring-offset-2 ring-offset-zinc-900"
                      : "ring-1 ring-zinc-700 ring-offset-0"
                  }`}
                  style={{ backgroundColor: option.swatch }}
                />
              ))}
              <span className="text-xs text-zinc-400">
                {ACCENT_OPTIONS.find((option) => option.id === accent)?.label ??
                  "天蓝"}
              </span>
            </div>
          </div>
          <p className="text-xs text-zinc-600">
            外观与主题色保存在本机浏览器（localStorage），选择后立即生效、所有页面同步，无需保存。
          </p>
        </div>
      </div>

      <p className="text-xs text-zinc-500">
        配置用于识别价格截图的视觉语言模型（VLM），走 OpenAI 兼容接口。API Key 属于秘密：
        只写入本机 gitignored 配置文件，接口从不回显；识别结果始终只作预填，由你确认后保存。
      </p>

      <div className="rounded-xl border border-zinc-800/80 bg-zinc-900 p-5">
        <div className="space-y-4">
          <div>
            <label className="mb-1 block text-xs text-zinc-500">Base URL</label>
            <input
              value={baseUrl}
              onChange={(e) => setBaseUrl(e.target.value)}
              placeholder="https://api.siliconflow.cn/v1"
              className="w-full rounded-md border border-zinc-800 bg-zinc-950 px-3 py-2 text-sm text-zinc-200"
            />
          </div>
          <div>
            <label className="mb-1 block text-xs text-zinc-500">模型</label>
            <input
              value={model}
              onChange={(e) => setModel(e.target.value)}
              placeholder="Qwen/Qwen3-VL-30B-A3B-Instruct"
              className="w-full rounded-md border border-zinc-800 bg-zinc-950 px-3 py-2 text-sm text-zinc-200"
            />
          </div>
          <div>
            <label className="mb-1 block text-xs text-zinc-500">
              API Key（留空表示保持现有密钥，不修改）
            </label>
            <input
              type="password"
              value={apiKey}
              onChange={(e) => setApiKey(e.target.value)}
              placeholder={query.data?.api_key_configured ? "••••••••（已配置，留空保持不变）" : "sk-…"}
              className="w-full rounded-md border border-zinc-800 bg-zinc-950 px-3 py-2 text-sm text-zinc-200"
            />
          </div>
        </div>

        <div className="mt-5 flex items-center gap-3">
          <button
            type="button"
            onClick={() => saveMutation.mutate()}
            disabled={saveMutation.isPending}
            className="rounded-md bg-sky-600 px-4 py-1.5 text-xs font-medium text-white hover:bg-sky-500 disabled:opacity-50"
          >
            保存 VLM 配置
          </button>
          <button
            type="button"
            onClick={handleTest}
            disabled={testMutation.isPending}
            className="rounded-md border border-zinc-800 px-4 py-1.5 text-xs text-zinc-300 hover:bg-zinc-800 disabled:opacity-40"
          >
            测试连接
          </button>
          <span className="text-xs text-zinc-500">
            已配置密钥：{query.data?.api_key_configured ? "是" : "否"}
          </span>
        </div>

        {result && <p className="mt-4 text-xs text-emerald-400">{result}</p>}
        {error && <p className="mt-4 text-xs text-rose-400">{error}</p>}
      </div>

      {!query.data?.api_key_configured && (
        <div className="rounded-lg border border-amber-800/50 bg-amber-950/30 px-5 py-3">
          <p className="text-sm text-amber-200">
            尚未配置 VLM API Key，价格截图识别暂不可用（可配置后使用）。
          </p>
        </div>
      )}

      {/* 计价系数快照(v3 T34):从本机客户端缓存抓厂商倍率。非官方口径、
          纯展示与誊抄,永不参与金额计算——按钮是用户显式动作,只写一个本地文件。 */}
      <div className="rounded-xl border border-zinc-800/80 bg-zinc-900 p-5">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h2 className="text-sm font-medium text-zinc-200">计价系数快照</h2>
            <p className="mt-1 text-xs text-zinc-500">
              从本机 Qoder IDE / Trae CN 的客户端缓存抓取各档位扣分倍率。
              <span className="text-amber-400/90">非官方口径,只用于展示与誊抄,永不参与金额计算</span>;
              只读白名单计价字段,凭据类字段与 secret:// 键一律不碰。
            </p>
          </div>
          <button
            type="button"
            onClick={() => ratesMutation.mutate()}
            disabled={ratesMutation.isPending}
            className="shrink-0 rounded-md bg-sky-600 px-4 py-1.5 text-xs font-medium text-white hover:bg-sky-500 disabled:opacity-50"
          >
            {ratesMutation.isPending ? "正在抓取…" : "抓取一次"}
          </button>
        </div>

        {ratesQuery.data?.captured_at == null ? (
          <p className="mt-4 text-xs text-zinc-600">还没有抓取过快照。</p>
        ) : (
          <div className="mt-4 space-y-3">
            <p className="text-xs text-zinc-500">
              抓取于 {formatDateTime(ratesQuery.data.captured_at)} · 来源{" "}
              {ratesQuery.data.source} · 共 {ratesQuery.data.entries.length} 档
            </p>
            {ratesQuery.data.warnings.length > 0 && (
              <div className="space-y-1 rounded-lg border border-amber-500/40 bg-amber-500/10 px-3 py-2 text-xs">
                {ratesQuery.data.warnings.map((w) => (
                  <p key={w.model_id} className="text-amber-300">
                    ⚠ {w.model_id}:{w.message}
                  </p>
                ))}
              </div>
            )}
            <div className="overflow-x-auto">
              <table className="w-full min-w-[560px] text-sm">
                <thead>
                  <tr className="border-b border-zinc-800 text-left text-xs text-zinc-500">
                    <th className="py-2 pr-4 font-medium">档位</th>
                    <th className="py-2 pr-4 font-medium">显示名</th>
                    <th className="py-2 pr-4 text-right font-medium">扣分倍率</th>
                    <th className="py-2 pr-4 text-right font-medium">原价倍率</th>
                    <th className="py-2 pr-4 text-right font-medium">最大输入</th>
                    <th className="py-2 font-medium">活动</th>
                  </tr>
                </thead>
                <tbody>
                  {ratesQuery.data.entries.map((entry) => (
                    <tr key={entry.model_id} className="border-b border-zinc-800/60">
                      <td className="py-1.5 pr-4 font-mono text-xs text-zinc-300">
                        {entry.model_id}
                      </td>
                      <td className="py-1.5 pr-4 text-xs text-zinc-400">
                        {entry.display_name ?? "—"}
                      </td>
                      <td className="py-1.5 pr-4 text-right font-mono text-xs tabular-nums text-zinc-200">
                        {entry.price_factor ?? "—"}
                      </td>
                      <td className="py-1.5 pr-4 text-right font-mono text-xs tabular-nums text-zinc-500">
                        {entry.original_price_factor ?? "—"}
                      </td>
                      <td className="py-1.5 pr-4 text-right font-mono text-xs tabular-nums text-zinc-500">
                        {entry.max_input_tokens?.toLocaleString("zh-CN") ?? "—"}
                      </td>
                      <td className="py-1.5 text-xs text-zinc-500">{entry.promotion ?? "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <p className="text-[10px] text-zinc-600">
              来源文件:{ratesQuery.data.provenance.join(" ; ")}
            </p>
          </div>
        )}
        {ratesMutation.isError && (
          <p className="mt-4 text-xs text-rose-400">
            {ratesMutation.error instanceof Error ? ratesMutation.error.message : "抓取失败"}
          </p>
        )}
      </div>
    </div>
  );
}