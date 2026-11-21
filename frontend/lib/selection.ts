import type { CitiesResponse } from "./types";

export type SearchParams = Record<string, string | string[] | undefined>;

export function first(v: string | string[] | undefined): string | undefined {
  return Array.isArray(v) ? v[0] : v;
}

export function list(v: string | string[] | undefined): string[] {
  if (!v) return [];
  return Array.isArray(v) ? v : [v];
}

/** Resolve the selected city and persona from the URL, falling back to defaults. */
export function resolveSelection(sp: SearchParams, meta: CitiesResponse | null) {
  const cityParam = first(sp.city);
  const personaParam = first(sp.persona);
  const city =
    meta?.cities.find((c) => c.name.toLowerCase() === cityParam?.toLowerCase() || c.slug === cityParam)?.name ??
    meta?.default_city ??
    cityParam ??
    "Delhi";
  const persona = meta?.personas.some((p) => p.id === personaParam)
    ? (personaParam as string)
    : (meta?.default_persona ?? "student");
  return { city, persona };
}
