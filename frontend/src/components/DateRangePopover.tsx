/** 自定义日期区间的悬浮面板:绝对定位挂在最近定位祖先(控制行)的下缘右角,
    弹出/收起不改变页面高度(总览与运行质量页共用,T27)。选中对应预设期间
    保持展开,切走即收起,无需开合状态。 */
export default function DateRangePopover({
  start,
  end,
  onStart,
  onEnd,
}: {
  start?: string;
  end?: string;
  onStart: (value: string) => void;
  onEnd: (value: string) => void;
}) {
  const inputClass =
    "rounded-md border border-zinc-800 bg-zinc-950 px-2 py-1 text-xs text-zinc-200";
  return (
    <div className="absolute right-0 top-full z-20 mt-2 flex items-center gap-2 rounded-lg border border-zinc-800 bg-zinc-900 p-3 text-xs text-zinc-500 shadow-xl">
      <input
        type="date"
        value={start ?? ""}
        onChange={(e) => onStart(e.target.value)}
        className={inputClass}
      />
      <span>→</span>
      <input
        type="date"
        value={end ?? ""}
        onChange={(e) => onEnd(e.target.value)}
        className={inputClass}
      />
    </div>
  );
}
