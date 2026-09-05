// Display formatters. Token counts use Chinese units (万/亿) per the visual
// baseline borrowed from the ZCode usage panel. Money is CNY (the app's base).

export function formatTokens(n: number): string {
  if (Math.abs(n) >= 100_000_000) return `${(n / 100_000_000).toFixed(2)} 亿`;
  if (Math.abs(n) >= 10_000) return `${(n / 10_000).toFixed(1)} 万`;
  return n.toLocaleString("zh-CN");
}

export function formatCost(amount: number | null): string {
  if (amount === null) return "未计价";
  return `¥${amount.toFixed(2)}`;
}

/** 积分不是钱:不带 ¥,恒两位小数(上游可达 9 位,仅展示层取 2 位)。 */
export function formatCredits(credits: number | null): string {
  if (credits === null) return "—";
  return credits.toLocaleString("zh-CN", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

export function formatDateTime(iso: string | null): string {
  if (iso === null) return "—";
  const d = new Date(iso);
  const pad = (v: number) => String(v).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`;
}
