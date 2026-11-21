// Presentation helpers: turn API values into consistent, friendly text.
import type { FactorLevel, Level, SourceState } from "./types";

export const PUBLIC_API_BASE = (process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8000").replace(/\/$/, "");

export const LEVEL_TEXT: Record<Level | FactorLevel, string> = {
  low: "Low",
  guarded: "Guarded",
  elevated: "Elevated",
  high: "High",
  insufficient: "Not enough data",
  unknown: "Not assessed",
};

export const STATE_TEXT: Record<SourceState, string> = {
  available: "Available",
  stale: "Last update",
  broader_region: "Wider area",
  no_data: "No local data",
  unavailable: "Unavailable",
  not_configured: "Not set up",
  not_applicable: "Not used",
  sample: "Sample data",
};

/** Badge variant for a level. "insufficient" and "unknown" share the slate style. */
export function levelVariant(l: Level | FactorLevel): "low" | "guarded" | "elevated" | "high" | "unknown" {
  return l === "insufficient" ? "unknown" : l;
}

export const LEVEL_COLOR: Record<"low" | "guarded" | "elevated" | "high" | "unknown", string> = {
  low: "var(--level-low)",
  guarded: "var(--level-guarded)",
  elevated: "var(--level-elevated)",
  high: "var(--level-high)",
  unknown: "var(--level-unknown)",
};

export function relative(hours: number | null | undefined): string {
  if (hours === null || hours === undefined || Number.isNaN(hours)) return "Date unknown";
  if (hours < 1) return "Less than an hour ago";
  if (hours < 24) return `${Math.round(hours)} hour${Math.round(hours) === 1 ? "" : "s"} ago`;
  const d = Math.round(hours / 24);
  return `${d} day${d === 1 ? "" : "s"} ago`;
}

export function since(iso: string | null | undefined, now = Date.now()): string {
  if (!iso) return "";
  const t = new Date(iso).getTime();
  if (Number.isNaN(t)) return "";
  const mins = Math.max(0, Math.round((now - t) / 60000));
  if (mins < 2) return "just now";
  if (mins < 60) return `${mins} minutes ago`;
  const h = Math.round(mins / 60);
  if (h < 48) return `${h} hour${h === 1 ? "" : "s"} ago`;
  return `${Math.round(h / 24)} days ago`;
}

export function date(iso: string | null | undefined, opts: { time?: boolean; year?: boolean } = {}): string {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  return d.toLocaleString("en-GB", {
    day: "numeric",
    month: "short",
    ...(opts.year === false ? {} : { year: "numeric" }),
    ...(opts.time ? { hour: "2-digit", minute: "2-digit", timeZone: "UTC", timeZoneName: "short" } : { timeZone: "UTC" }),
  });
}

export function weekday(isoDate: string): string {
  const d = new Date(`${isoDate}T12:00:00Z`);
  if (Number.isNaN(d.getTime())) return isoDate;
  return d.toLocaleDateString("en-GB", { weekday: "short", day: "numeric", month: "short", timeZone: "UTC" });
}

export function num(v: unknown, unit = "", digits = 0): string | null {
  if (typeof v !== "number" || Number.isNaN(v)) return null;
  return `${v.toFixed(digits)}${unit}`;
}

export function signed(n: number | null | undefined): string {
  if (n === null || n === undefined) return "";
  const v = Math.abs(n).toFixed(1);
  return n > 0 ? `+${v}` : n < 0 ? `−${v}` : "0.0";
}

export function plural(n: number, word: string, pluralWord = `${word}s`): string {
  return `${n} ${n === 1 ? word : pluralWord}`;
}

export function placeLine(region: string, area: string, country: string): string {
  return region === "India" ? `${area}, India` : country;
}

export function withParams(path: string, city: string, persona: string, extra?: Record<string, string>): string {
  return `${path}?${new URLSearchParams({ city, persona, ...extra }).toString()}`;
}
