// Display formatters. Token counts use Chinese units (万/亿) per the visual
// baseline borrowed from the ZCode usage panel.

export function formatTokens(n: number): string {
  if (Math.abs(n) >= 100_000_000) return `${(n / 100_000_000).toFixed(2)} 亿`;
  if (Math.abs(n) >= 10_000) return `${(n / 10_000).toFixed(1)} 万`;
  return n.toLocaleString("zh-CN");
}

export function formatCost(usd: number | null): string {
  if (usd === null) return "未计价";
  return `$${usd.toFixed(2)}`;
}

export function formatDateTime(iso: string | null): string {
  if (iso === null) return "—";
  const d = new Date(iso);
  const pad = (v: number) => String(v).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`;
}
