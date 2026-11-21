// Response types mirroring backend/app/schemas.py (presentation DTOs).

export type SourceState =
  | "available"
  | "stale"
  | "broader_region"
  | "no_data"
  | "unavailable"
  | "not_configured"
  | "not_applicable"
  | "sample";
export type Level = "low" | "guarded" | "elevated" | "high" | "insufficient";
export type FactorLevel = "low" | "guarded" | "elevated" | "high" | "unknown";
export type CoverageState = "good" | "limited" | "insufficient";
export type DataMode = "live" | "sample" | "none";
export type Severity = "severe" | "serious" | "minor" | "none" | "positive";
export type FactorKey = "crime" | "civil" | "transport" | "disaster" | "weather" | "environment";

export interface CityInfo {
  name: string;
  slug: string;
  region: "India" | "International";
  country: string;
  area: string;
  has_sample_data: boolean;
  aliases: string[];
}

export interface PersonaInfo {
  id: string;
  name: string;
  description: string;
}

export interface CitiesResponse {
  cities: CityInfo[];
  personas: PersonaInfo[];
  default_city: string;
  default_persona: string;
}

export interface SourceStatus {
  key: string;
  name: string;
  kind: string;
  state: SourceState;
  provider: string | null;
  updated_at: string | null;
  message: string;
  used_for: string[];
  resolution: string;
  attribution: string;
}

export interface EventItem {
  id: string;
  title: string;
  summary: string | null;
  url: string | null;
  source: string;
  sources: string[];
  report_count: number;
  category: string;
  category_label: string;
  subtype_label: string | null;
  severity: Severity;
  severity_label: string;
  confidence_label: string;
  location_label: string;
  published_at: string | null;
  age_hours: number | null;
  status: "counted" | "not_counted" | "context";
  status_note: string;
  notes: string[];
  origin: "live" | "sample";
}

export interface Assessment {
  index: number | null;
  level: Level;
  label: string;
  summary: string;
}

export interface Coverage {
  state: CoverageState;
  label: string;
  summary: string;
  reasons: string[];
  factors_assessed: number;
  factors_total: number;
}

export interface Evidence {
  text: string;
  kind: "news" | "measurement" | "forecast" | "official_alert" | "feed_event" | "model";
  source: string;
  when: string | null;
  url: string | null;
  severity: string | null;
}

export interface Factor {
  key: FactorKey;
  label: string;
  definition: string;
  assessed: boolean;
  level: FactorLevel;
  persona_level: FactorLevel;
  persona_note: string | null;
  intensity: number | null;
  persona_intensity: number | null;
  summary: string;
  evidence: Evidence[];
  sources: string[];
  time_window: string;
  geo_match: string;
  updated_at: string | null;
  reliability: "good" | "limited" | "none";
  reliability_note: string;
  contribution: number | null;
  raised_by_alert: boolean;
}

export interface CriticalAlert {
  factor: string;
  title: string;
  detail: string;
  source: string;
  level: "guarded" | "elevated" | "high";
  when: string | null;
  url: string | null;
}

export interface KeyFactor {
  category: string;
  level: Level;
  text: string;
}

export interface TimelineDay {
  date: string;
  crime: number;
  civil: number;
  transport: number;
  disaster: number;
  weather: number;
}

export interface Overview {
  city: CityInfo;
  persona: PersonaInfo;
  as_of: string;
  updated_at: string | null;
  data_mode: DataMode;
  period: { start: string; end: string; days: number };
  latest_report_at: string | null;
  sources: SourceStatus[];
  coverage: Coverage;
  general: Assessment;
  personalized: Assessment;
  persona_explanation: string;
  factors: Factor[];
  critical_alerts: CriticalAlert[];
  key_factors: KeyFactor[];
  stable_signals: string[];
  recent_events: EventItem[];
  total_reports: number;
  timeline: { available: boolean; reason: string; days: TimelineDay[] };
  weather_now: {
    available: boolean;
    provider: string | null;
    temperature_c: number | null;
    condition: string | null;
    group: string | null;
    message: string;
  };
  air_now: {
    measured: boolean;
    category: string | null;
    station: string | null;
    distance_km: number | null;
    pm25: number | null;
    modelled_category: string | null;
    message: string;
  };
  precautions: { dos: string[]; donts: string[]; basis: string };
  disclaimer: string;
}

export interface EventsResponse {
  city: string;
  as_of: string;
  data_mode: DataMode;
  sources: SourceStatus[];
  total: number;
  page: number;
  page_size: number;
  total_reports: number;
  category_counts: Record<string, number>;
  items: EventItem[];
}

export interface WeatherCurrent {
  temperature_c: number | null;
  feels_like_c: number | null;
  condition: string;
  group: string;
  humidity_pct: number | null;
  wind_kmh: number | null;
  wind_dir_deg: number | null;
  wind_gust_kmh: number | null;
  precipitation_mm: number | null;
  visibility_km: number | null;
  pressure_hpa: number | null;
  clouds_pct: number | null;
  sunrise_local: string | null;
  sunset_local: string | null;
  observed_at: string | null;
}

export interface WeatherHour {
  time: string;
  temp_c: number | null;
  precip_mm: number | null;
  precip_prob: number | null;
}

export interface WeatherDay {
  date: string;
  condition: string;
  temp_min_c: number | null;
  temp_max_c: number | null;
  precip_mm: number | null;
  precip_prob: number | null;
  wind_max_kmh: number | null;
}

export interface WeatherResponse {
  city: string;
  timezone: string;
  data_mode: DataMode;
  status: "available" | "stale" | "unavailable";
  reason: string;
  provider: string | null;
  attribution: string;
  fallback_used: boolean;
  updated_at: string | null;
  source: SourceStatus;
  alerts_source: SourceStatus;
  current: WeatherCurrent | null;
  hourly: WeatherHour[];
  hourly_step_hours: number;
  daily: WeatherDay[];
  alerts: { event: string; issued_by: string; start: string | null; end: string | null; description: string }[] | null;
  alerts_message: string;
  conditions: { available: boolean; level: FactorLevel; factors: string[]; forecast_hazards: string[] };
  advice: string[];
  news_events: EventItem[];
  factor: Factor;
  note: string;
}

export interface AirTrendPoint {
  time: string;
  pm25: number | null;
}

export interface AirQualityResponse {
  city: string;
  data_mode: DataMode;
  measured: {
    station: string;
    distance_km: number;
    category: string | null;
    driver: string | null;
    observed_at: string | null;
    readings: { parameter: string; label: string; value: number; unit: string; observed_at: string | null }[];
    trend: AirTrendPoint[];
    attribution: string;
  } | null;
  modelled: {
    pm25: number | null;
    pm10: number | null;
    us_aqi: number | null;
    category: string | null;
    observed_at: string | null;
    trend: AirTrendPoint[];
    attribution: string;
  } | null;
  sources: SourceStatus[];
  factor: Factor;
  note: string;
}

export interface Hazard {
  source: string;
  hazard: string;
  title: string;
  when: string;
  distance_km: number | null;
  severity: "severe" | "serious" | "minor" | "none";
  alert_level: string | null;
  near_city: boolean;
  relevance: string;
  url: string | null;
  magnitude: number | null;
}

export interface DisastersResponse {
  city: string;
  data_mode: DataMode;
  events: Hazard[];
  context: Hazard[];
  sources: SourceStatus[];
  factor: Factor;
  news_events: EventItem[];
  note: string;
}

export interface CrimeResponse {
  city: string;
  as_of: string;
  data_mode: DataMode;
  sources: SourceStatus[];
  coverage: Coverage;
  explanation: string;
  factor: Factor;
  incidents_counted: number;
  articles_counted: number;
  events: EventItem[];
  not_counted: EventItem[];
  breakdown: { available: boolean; reason: string; items: { label: string; count: number }[] };
  trend: { available: boolean; reason: string; weeks: { week_start: string; count: number }[] };
  supplementary: EventItem[];
  supplementary_note: string;
}

export interface InsightsResponse {
  city: CityInfo;
  persona: PersonaInfo;
  status: "available" | "unavailable";
  message: string;
  title: string | null;
  description: string | null;
  summary: string | null;
  about: string[];
  image_url: string | null;
  article_url: string | null;
  facts: { label: string; value: string; note: string }[];
  facts_source: string;
  climate: string | null;
  transport: string | null;
  local_time: string | null;
  emergency: { service: string; number: string }[];
  emergency_note: string;
  persona_priority: string;
  persona_tips: string[];
  source: SourceStatus;
}

export interface MethodologyResponse {
  version: string;
  summary: string[];
  formulas: Record<string, string>;
  parameters: Record<string, unknown>;
  levels: Record<string, string>;
  limitations: string[];
}
