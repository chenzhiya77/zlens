import { useState } from "react";

import type { SourceRef } from "../lib/api";

/** 来源(agent)下拉选择器:chips 行在来源一多就放不下,收进下拉(T27 后的
    用户反馈)。不可用来源仍要列出——置灰并带原因,消失会让人以为那段用量
    从来不存在(T18 的既定规则)。点选项或菜单外任意处关闭。 */
export default function SourceSelect({
  sources,
  value,
  onChange,
}: {
  sources: SourceRef[];
  /** "" = 全部(合并口径)。 */
  value: string;
  onChange: (source: string | null) => void;
}) {
  const [open, setOpen] = useState(false);
  const pick = (source: string | null) => {
    onChange(source);
    setOpen(false);
  };
  const itemClass = (selected: boolean) =>
    `flex w-full items-center justify-between rounded-md px-3 py-1.5 text-left text-xs transition-colors ${
      selected
        ? "bg-zinc-700/80 text-zinc-100"
        : "text-zinc-400 hover:bg-zinc-800 hover:text-zinc-200"
    }`;
  return (
    <div className="relative">
      <button
        type="button"
        aria-haspopup="listbox"
        aria-expanded={open}
        onClick={() => setOpen((cur) => !cur)}
        className="inline-flex items-center gap-2 rounded-lg border border-zinc-800 bg-zinc-900/60 px-3 py-1.5 text-xs text-zinc-300 transition-colors hover:border-zinc-700"
      >
        <span className="text-zinc-500">来源</span>
        {value === "" ? "全部" : value}
        <span className="font-mono text-[10px] text-zinc-500">{open ? "▴" : "▾"}</span>
      </button>
      {open && (
        <>
          {/* 透明遮罩:点菜单外任意处关闭;z 序低于菜单。 */}
          <div className="fixed inset-0 z-10" onClick={() => setOpen(false)} />
          <div
            role="listbox"
            className="absolute right-0 top-full z-20 mt-2 max-h-72 w-44 overflow-y-auto rounded-lg border border-zinc-800 bg-zinc-900 p-1 shadow-xl"
          >
            <button type="button" role="option" aria-selected={value === ""} onClick={() => pick(null)} className={itemClass(value === "")}>
              全部
              <span className="text-[10px] text-zinc-500">合并口径</span>
            </button>
            {sources.map((ref) =>
              ref.available ? (
                <button
                  key={ref.id}
                  type="button"
                  role="option"
                  aria-selected={value === ref.id}
                  onClick={() => pick(ref.id)}
                  className={itemClass(value === ref.id)}
                >
                  {ref.id}
                  {value === ref.id && <span className="text-[10px] text-emerald-500">✓</span>}
                </button>
              ) : (
                <div
                  key={ref.id}
                  title={`不可用:${ref.error ?? "未知原因"}`}
                  className="flex cursor-not-allowed items-center justify-between rounded-md px-3 py-1.5 text-xs text-zinc-600"
                >
                  <span className="line-through">{ref.id}</span>
                  <span className="text-[10px]">不可用</span>
                </div>
              ),
            )}
          </div>
        </>
      )}
    </div>
  );
}
