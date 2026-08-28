// Per-model display aliases, edited in the overview table and consumed by every
// view. Local-first like the theme prefs: stored in this browser only.

const KEY = "zlens.model-aliases";

export function aliasKey(source: string, providerId: string, modelId: string): string {
  return `${source}|${providerId}|${modelId}`;
}

export interface ChannelKey {
  source: string;
  providerId: string;
  modelId: string;
}

/**
 * Parse a canonical channel key (backend model_key). Null when the string is not
 * a triple — e.g. a legacy bare model id left behind in pricing.json.
 */
export function parseModelKey(key: string): ChannelKey | null {
  const parts = key.split("|");
  if (parts.length !== 3 || parts.some((part) => part.trim() === "")) return null;
  return { source: parts[0]!, providerId: parts[1]!, modelId: parts[2]! };
}

export function getAliases(): Record<string, string> {
  try {
    return JSON.parse(localStorage.getItem(KEY) ?? "{}") as Record<string, string>;
  } catch {
    return {};
  }
}

/** Empty or same-as-default clears the entry, so the store only holds real overrides. */
export function setAlias(key: string, alias: string, defaultName: string): void {
  const all = getAliases();
  const value = alias.trim();
  if (value === "" || value === defaultName) delete all[key];
  else all[key] = value;
  localStorage.setItem(KEY, JSON.stringify(all));
}

export function displayName(
  aliases: Record<string, string>,
  source: string,
  providerId: string,
  modelId: string,
): string {
  return aliases[aliasKey(source, providerId, modelId)]?.trim() || modelId;
}

/** Names colliding within one view get a short provider suffix so rows stay tellable apart. */
export function disambiguate(names: string[], providerIds: string[]): string[] {
  const count = new Map<string, number>();
  for (const name of names) count.set(name, (count.get(name) ?? 0) + 1);
  return names.map((name, i) =>
    count.get(name)! > 1 ? `${name} ·${providerIds[i]!.slice(0, 4)}` : name,
  );
}
