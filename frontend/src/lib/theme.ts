// Theme preferences (appearance mode + accent color). zlens is local-first, so
// these live in the browser (localStorage) instead of the backend config file;
// initTheme() runs at startup and every page picks the values up immediately.

import { useSyncExternalStore } from "react";

export const ACCENT_OPTIONS = [
  { id: "sky", label: "天蓝", swatch: "#38bdf8" },
  { id: "cyan", label: "青色", swatch: "#22d3ee" },
  { id: "emerald", label: "翡翠", swatch: "#34d399" },
  { id: "violet", label: "靛紫", swatch: "#a78bfa" },
  { id: "amber", label: "琥珀", swatch: "#fbbf24" },
  { id: "rose", label: "玫红", swatch: "#fb7185" },
] as const;

export type AccentId = (typeof ACCENT_OPTIONS)[number]["id"];
export type ThemeMode = "dark" | "light";

const ACCENT_KEY = "zlens.theme.accent";
const MODE_KEY = "zlens.theme.mode";

export function getAccent(): AccentId {
  const value = localStorage.getItem(ACCENT_KEY) ?? "";
  return ACCENT_OPTIONS.some((option) => option.id === value) ? (value as AccentId) : "sky";
}

export function getMode(): ThemeMode {
  return localStorage.getItem(MODE_KEY) === "light" ? "light" : "dark";
}

function applyTheme(accent: AccentId, mode: ThemeMode): void {
  const root = document.documentElement;
  root.setAttribute("data-accent", accent);
  root.setAttribute("data-mode", mode);
}

/** Startup hook: restore the saved theme before the first render paints. */
export function initTheme(): void {
  applyTheme(getAccent(), getMode());
}

export function setAccent(accent: AccentId): void {
  localStorage.setItem(ACCENT_KEY, accent);
  applyTheme(accent, getMode());
  emit();
}

export function setMode(mode: ThemeMode): void {
  localStorage.setItem(MODE_KEY, mode);
  applyTheme(getAccent(), mode);
  emit();
}

// ECharts paints on a canvas and can't read the CSS variables that flip the
// Tailwind palette, so chart options need the active mode as plain values.
const listeners = new Set<() => void>();

function emit(): void {
  for (const listener of listeners) listener();
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

/** React hook: re-renders the caller whenever mode / accent changes. */
export function useTheme(): { mode: ThemeMode; accent: AccentId } {
  const mode = useSyncExternalStore(subscribe, getMode);
  const accent = useSyncExternalStore(subscribe, getAccent);
  return { mode, accent };
}