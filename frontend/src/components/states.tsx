import { ApiError } from "../lib/api";

export function LoadingBlock({ text = "读取本地数据库…" }: { text?: string }) {
  return <p className="text-sm text-zinc-500">{text}</p>;
}

export function EmptyBlock({ text = "该范围内暂无数据" }: { text?: string }) {
  return (
    <div className="rounded-xl border border-dashed border-zinc-800 px-8 py-14 text-center">
      <p className="text-sm text-zinc-500">{text}</p>
    </div>
  );
}

export function ErrorBlock({ error }: { error: Error }) {
  const code = error instanceof ApiError ? error.code : "unknown";
  const friendly =
    code === "source_unavailable"
      ? "找不到 ZCode 本地数据库,请确认本机已安装并使用过 ZCode。"
      : code === "schema_incompatible"
        ? "ZCode 数据库结构与 zlens 预期不一致(可能升级过),本视图暂时无法展示。"
        : error.message;
  return (
    <div className="rounded-lg border border-amber-800/50 bg-amber-950/30 px-5 py-4">
      <p className="text-sm text-amber-200">{friendly}</p>
      <p className="mt-1 text-xs text-amber-500/70">错误码:{code}</p>
    </div>
  );
}
