// Server-side API client. All data comes from the FastAPI backend; no scoring
// or explanation logic lives in the frontend.
import "server-only";

import type {
  AirQualityResponse,
  CitiesResponse,
  CrimeResponse,
  DisastersResponse,
  EventsResponse,
  InsightsResponse,
  MethodologyResponse,
  Overview,
  WeatherResponse,
} from "./types";

// Server-side only. No API keys ever reach the frontend: the backend holds them.
const BASE = (process.env.API_BASE_URL ?? process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8000").replace(
  /\/$/,
  "",
);

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number | null,
    readonly kind: "unreachable" | "http" | "shape",
  ) {
    super(message);
    this.name = "ApiError";
  }
}

function isRecord(v: unknown): v is Record<string, unknown> {
  return typeof v === "object" && v !== null && !Array.isArray(v);
}

/** Minimal runtime check that the response has the fields the UI depends on. */
function expectShape<T>(data: unknown, keys: string[], what: string): T {
  if (!isRecord(data)) throw new ApiError(`Unexpected ${what} response from the API.`, null, "shape");
  const missing = keys.filter((k) => !(k in data));
  if (missing.length) {
    console.error(`[api] ${what} response missing fields: ${missing.join(", ")}`);
    throw new ApiError(`The ${what} information came back incomplete.`, null, "shape");
  }
  return data as T;
}

async function get(path: string, params?: Record<string, string | string[] | undefined>): Promise<unknown> {
  const url = new URL(BASE + path);
  for (const [k, v] of Object.entries(params ?? {})) {
    if (v === undefined || v === "") continue;
    if (Array.isArray(v)) v.forEach((x) => url.searchParams.append(k, x));
    else url.searchParams.set(k, v);
  }
  let res: Response;
  try {
    res = await fetch(url, { cache: "no-store", signal: AbortSignal.timeout(30_000) });
  } catch {
    throw new ApiError(
      "The TravelSafe service isn't responding right now.",
      null,
      "unreachable",
    );
  }
  if (!res.ok) {
    let detail = "";
    try {
      const body: unknown = await res.json();
      if (isRecord(body) && typeof body.detail === "string") detail = body.detail;
    } catch {
      /* body was not JSON; keep status text */
    }
    console.error(`[api] ${path} -> HTTP ${res.status} ${detail}`);
    const friendly =
      res.status === 404
        ? "That city isn't supported."
        : res.status === 422
          ? "Some of the selected options aren't valid."
          : "Something went wrong while loading this page.";
    throw new ApiError(friendly, res.status, "http");
  }
  return res.json();
}

const cityPath = (city: string) => `/api/cities/${encodeURIComponent(city)}`;

export async function getCities(): Promise<CitiesResponse> {
  return expectShape(await get("/api/cities"), ["cities", "personas", "default_city", "default_persona"], "cities");
}

export async function getOverview(city: string, persona: string): Promise<Overview> {
  return expectShape(
    await get(`${cityPath(city)}/overview`, { persona }),
    ["city", "general", "personalized", "coverage", "factors", "critical_alerts", "sources", "timeline", "precautions"],
    "overview",
  );
}

export interface EventQuery {
  category?: string;
  q?: string;
  severity?: string;
  days?: string;
  status?: string;
  sort?: string;
  page?: string;
}

export async function getEvents(city: string, persona: string, query: EventQuery): Promise<EventsResponse> {
  return expectShape(
    await get(`${cityPath(city)}/events`, { persona, page_size: "20", ...query }),
    ["items", "total", "category_counts"],
    "events",
  );
}

export async function getWeather(city: string, persona: string): Promise<WeatherResponse> {
  return expectShape(
    await get(`${cityPath(city)}/weather`, { persona }),
    ["status", "source", "conditions", "factor", "hourly", "daily"],
    "weather",
  );
}

export async function getAirQuality(city: string, persona: string): Promise<AirQualityResponse> {
  return expectShape(await get(`${cityPath(city)}/air-quality`, { persona }), ["sources", "factor"], "air quality");
}

export async function getDisasters(city: string, persona: string): Promise<DisastersResponse> {
  return expectShape(await get(`${cityPath(city)}/disasters`, { persona }), ["events", "context", "factor"], "hazards");
}

export async function getCrime(city: string, persona: string): Promise<CrimeResponse> {
  return expectShape(await get(`${cityPath(city)}/crime`, { persona }), ["events", "trend", "factor", "breakdown"], "crime");
}

export async function getInsights(city: string, persona: string): Promise<InsightsResponse> {
  return expectShape(
    await get(`${cityPath(city)}/insights`, { persona }),
    ["status", "facts", "emergency", "persona_tips", "source"],
    "insights",
  );
}

export async function getMethodology(): Promise<MethodologyResponse> {
  return expectShape(await get("/api/methodology"), ["summary", "limitations"], "methodology");
}

/** Ask the backend to forget cached data for a city (used by Refresh and Try again). */
export async function refreshCityData(city: string): Promise<boolean> {
  try {
    const res = await fetch(`${BASE}${cityPath(city)}/refresh`, { method: "POST", cache: "no-store" });
    if (!res.ok) console.error(`[api] refresh ${city} -> HTTP ${res.status}`);
    return res.ok;
  } catch (e) {
    console.error("[api] refresh failed", e);
    return false;
  }
}
