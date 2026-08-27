import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";

import { fetchVlmSettings, saveVlmSettings, testVlm } from "../lib/api";
import { ErrorBlock, LoadingBlock } from "../components/states";

/**
 * VLM settings page: the model used to read price screenshots. API keys are
 * secrets — they are stored only in the gitignored local config file and the
 * API never echoes them back.
 */
export default function Settings() {
  const queryClient = useQueryClient();
  const query = useQuery({ queryKey: ["vlm-settings"], queryFn: fetchVlmSettings });

  const [baseUrl, setBaseUrl] = useState("");
  const [model, setModel] = useState("");
  const [apiKey, setApiKey] = useState("");
  const [result, setResult] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

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
      <p className="text-xs text-zinc-500">
        配置用于识别价格截图的视觉语言模型（VLM），走 OpenAI 兼容接口。API Key 属于秘密：
        只写入本机 gitignored 配置文件，接口从不回显；识别结果始终只作预填，由你确认后保存。
      </p>

      <div className="rounded-xl border border-zinc-800/80 bg-zinc-900/40 p-5">
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
    </div>
  );
}