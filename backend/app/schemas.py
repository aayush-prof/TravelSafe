"""
Pydantic response schemas – the browser-facing API contract.

These are *presentation* DTOs: they carry plain-language labels, not the
model's internal values. Raw confidences, impact units, weights, flags,
matched keywords, cache metadata and provider error strings stay on the
server (logs and ``/api/methodology``).
"""

from __future__ import annotations

from datetime import datetime
from typing import Dict, List, Literal, Optional

from pydantic import BaseModel, Field

DataState = Literal["live", "cached", "stale", "sample", "unavailable"]
Level = Literal["low", "guarded", "elevated", "high", "insufficient"]
CoverageState = Literal["good", "limited", "insufficient"]
DataMode = Literal["live", "sample", "none"]


class ErrorResponse(BaseModel):
    detail: str


class ProviderInfo(BaseModel):
    news_providers: List[str]
    weather_configured: bool
    data_mode: Literal["auto", "live", "sample"]
    sample_cities: List[str]


class HealthResponse(BaseModel):
    status: Literal["ok"]
    version: str
    methodology_version: str
    time: datetime
    providers: ProviderInfo
    cache: Dict[str, int]


class CityInfo(BaseModel):
    name: str
    slug: str
    region: Literal["India", "International"]
    country: str
    area: str
    has_sample_data: bool
    aliases: List[str]


class PersonaInfo(BaseModel):
    id: str
    name: str
    description: str


class CitiesResponse(BaseModel):
    cities: List[CityInfo]
    personas: List[PersonaInfo]
    default_city: str
    default_persona: str


SourceState = Literal["available", "stale", "broader_region", "no_data", "unavailable", "not_configured",
                      "not_applicable", "sample"]
FactorLevel = Literal["low", "guarded", "elevated", "high", "unknown"]


class SourceStatusOut(BaseModel):
    key: str
    name: str
    kind: str
    state: SourceState
    provider: Optional[str] = Field(description="Friendly provider name, e.g. 'Open-Meteo'")
    updated_at: Optional[datetime]
    message: str = Field("", description="Plain-language note, empty when everything is normal")
    used_for: List[str] = Field(default_factory=list, description="Factors this source feeds")
    resolution: str = Field("", description="Geographic resolution in plain words")
    attribution: str = ""


class EventOut(BaseModel):
    id: str
    title: str
    summary: Optional[str]
    url: Optional[str]
    source: str
    sources: List[str]
    report_count: int = Field(description="Articles about this incident that were merged")
    category: str
    category_label: str
    subtype_label: Optional[str]
    severity: Literal["severe", "serious", "minor", "none", "positive"]
    severity_label: str
    confidence_label: str
    location_label: str
    published_at: Optional[datetime]
    age_hours: Optional[float]
    status: Literal["counted", "not_counted", "context"]
    status_note: str
    notes: List[str]
    origin: Literal["live", "sample"]


class AssessmentOut(BaseModel):
    index: Optional[float] = Field(description="-10..+10; higher = fewer adverse signals; null if insufficient")
    level: Level
    label: str
    summary: str


class CategoryOut(BaseModel):
    category: str
    label: str
    level: Level
    persona_level: Level
    persona_note: Optional[str]
    note: str
    incidents: int
    highlights: List[str]


class CoverageOut(BaseModel):
    state: CoverageState
    label: str
    summary: str
    reasons: List[str]
    factors_assessed: int
    factors_total: int


class EvidenceOut(BaseModel):
    text: str
    kind: Literal["news", "measurement", "forecast", "official_alert", "feed_event", "model"]
    source: str
    when: Optional[datetime]
    url: Optional[str]
    severity: Optional[str]


class FactorOut(BaseModel):
    key: str
    label: str
    definition: str
    assessed: bool
    level: FactorLevel
    persona_level: FactorLevel
    persona_note: Optional[str]
    intensity: Optional[int] = Field(description="0–100 concern intensity for charts; null when not assessed")
    persona_intensity: Optional[int]
    summary: str
    evidence: List[EvidenceOut]
    sources: List[str]
    time_window: str
    geo_match: str
    updated_at: Optional[datetime]
    reliability: Literal["good", "limited", "none"] = Field(description="How dependable the evidence is")
    reliability_note: str
    contribution: Optional[float] = Field(description="Share of the overall signal (0–1); null when not assessed")
    raised_by_alert: bool


class CriticalAlertOut(BaseModel):
    factor: str
    title: str
    detail: str
    source: str
    level: Literal["guarded", "elevated", "high"]
    when: Optional[datetime]
    url: Optional[str]


class TimelineDay(BaseModel):
    date: str
    crime: int
    civil: int
    transport: int
    disaster: int
    weather: int


class TimelineOut(BaseModel):
    available: bool
    reason: str
    days: List[TimelineDay]


class WeatherNowOut(BaseModel):
    available: bool
    provider: Optional[str]
    temperature_c: Optional[float]
    condition: Optional[str]
    group: Optional[str]
    message: str


class AirNowOut(BaseModel):
    measured: bool
    category: Optional[str]
    station: Optional[str]
    distance_km: Optional[float]
    pm25: Optional[float]
    modelled_category: Optional[str]
    message: str


class KeyFactorOut(BaseModel):
    category: str
    level: Level
    text: str


class PeriodOut(BaseModel):
    start: datetime
    end: datetime
    days: int


class PrecautionsOut(BaseModel):
    dos: List[str]
    donts: List[str]
    basis: str


class OverviewResponse(BaseModel):
    city: CityInfo
    persona: PersonaInfo
    as_of: datetime
    updated_at: Optional[datetime] = Field(description="Most recent successful fetch across sources")
    data_mode: DataMode
    period: PeriodOut
    latest_report_at: Optional[datetime]
    sources: List[SourceStatusOut]
    coverage: CoverageOut
    general: AssessmentOut
    personalized: AssessmentOut
    persona_explanation: str
    factors: List[FactorOut]
    critical_alerts: List[CriticalAlertOut]
    key_factors: List[KeyFactorOut]
    stable_signals: List[str]
    recent_events: List[EventOut]
    total_reports: int
    timeline: TimelineOut
    weather_now: WeatherNowOut
    air_now: AirNowOut
    precautions: PrecautionsOut
    disclaimer: str


class EventsResponse(BaseModel):
    city: str
    as_of: datetime
    data_mode: DataMode
    sources: List[SourceStatusOut]
    total: int
    page: int
    page_size: int
    total_reports: int
    category_counts: Dict[str, int]
    items: List[EventOut]


class WeatherCurrentOut(BaseModel):
    temperature_c: Optional[float]
    feels_like_c: Optional[float]
    condition: str
    group: str
    humidity_pct: Optional[float]
    wind_kmh: Optional[float]
    wind_dir_deg: Optional[float]
    wind_gust_kmh: Optional[float]
    precipitation_mm: Optional[float]
    visibility_km: Optional[float]
    pressure_hpa: Optional[float]
    clouds_pct: Optional[float]
    sunrise_local: Optional[str]
    sunset_local: Optional[str]
    observed_at: Optional[datetime]


class WeatherHourOut(BaseModel):
    time: datetime
    temp_c: Optional[float]
    precip_mm: Optional[float]
    precip_prob: Optional[float]


class WeatherDayOut(BaseModel):
    date: str
    condition: str
    temp_min_c: Optional[float]
    temp_max_c: Optional[float]
    precip_mm: Optional[float]
    precip_prob: Optional[float]
    wind_max_kmh: Optional[float]


class WeatherAlertOut(BaseModel):
    event: str
    issued_by: str
    start: Optional[str]
    end: Optional[str]
    description: str


class WeatherConditionsOut(BaseModel):
    available: bool
    level: FactorLevel
    factors: List[str]
    forecast_hazards: List[str]


class WeatherResponse(BaseModel):
    city: str
    timezone: str = Field(description="IANA time zone of the city, for local times")
    data_mode: DataMode
    status: Literal["available", "stale", "unavailable"]
    reason: str = Field(description="Plain-language reason when unavailable")
    provider: Optional[str]
    attribution: str
    fallback_used: bool
    updated_at: Optional[datetime]
    source: SourceStatusOut
    alerts_source: SourceStatusOut
    current: Optional[WeatherCurrentOut]
    hourly: List[WeatherHourOut]
    hourly_step_hours: int
    daily: List[WeatherDayOut]
    alerts: Optional[List[WeatherAlertOut]] = Field(description="null = not checked/unavailable, [] = none active")
    alerts_message: str
    conditions: WeatherConditionsOut
    advice: List[str]
    news_events: List[EventOut]
    factor: FactorOut
    note: str


class AirReadingOut(BaseModel):
    parameter: str
    label: str
    value: float
    unit: str
    observed_at: Optional[datetime]


class AirTrendOut(BaseModel):
    time: datetime
    pm25: Optional[float]


class MeasuredAirOut(BaseModel):
    station: str
    distance_km: float
    category: Optional[str]
    driver: Optional[str]
    observed_at: Optional[datetime]
    readings: List[AirReadingOut]
    trend: List[AirTrendOut]
    attribution: str


class ModelledAirOut(BaseModel):
    pm25: Optional[float]
    pm10: Optional[float]
    us_aqi: Optional[float]
    category: Optional[str]
    observed_at: Optional[datetime]
    trend: List[AirTrendOut]
    attribution: str


class AirQualityResponse(BaseModel):
    city: str
    data_mode: DataMode
    measured: Optional[MeasuredAirOut]
    modelled: Optional[ModelledAirOut]
    sources: List[SourceStatusOut]
    factor: FactorOut
    note: str


class HazardOut(BaseModel):
    source: str
    hazard: str
    title: str
    when: datetime
    distance_km: Optional[float]
    severity: Literal["severe", "serious", "minor", "none"]
    alert_level: Optional[str]
    near_city: bool
    relevance: str
    url: Optional[str]
    magnitude: Optional[float]


class DisastersResponse(BaseModel):
    city: str
    data_mode: DataMode
    events: List[HazardOut]
    context: List[HazardOut]
    sources: List[SourceStatusOut]
    factor: FactorOut
    news_events: List[EventOut]
    note: str


class CoverageResponse(BaseModel):
    city: str
    data_mode: DataMode
    coverage: CoverageOut
    sources: List[SourceStatusOut]
    factors: List[FactorOut]
    updated_at: Optional[datetime]


class TrendWeek(BaseModel):
    week_start: datetime
    count: int


class TrendOut(BaseModel):
    available: bool
    reason: str
    weeks: List[TrendWeek]


class BreakdownOut(BaseModel):
    available: bool
    reason: str
    items: List[Dict[str, int | str]]


class CrimeResponse(BaseModel):
    city: str
    as_of: datetime
    data_mode: DataMode
    sources: List[SourceStatusOut]
    coverage: CoverageOut
    explanation: str
    factor: FactorOut
    incidents_counted: int
    articles_counted: int
    events: List[EventOut]
    not_counted: List[EventOut]
    breakdown: BreakdownOut
    trend: TrendOut
    supplementary: List[EventOut]
    supplementary_note: str


class FactOut(BaseModel):
    label: str
    value: str
    note: str = ""


class EmergencyOut(BaseModel):
    service: str
    number: str


class InsightsResponse(BaseModel):
    city: CityInfo
    persona: PersonaInfo
    status: Literal["available", "unavailable"]
    message: str
    title: Optional[str]
    description: Optional[str]
    summary: Optional[str]
    about: List[str]
    image_url: Optional[str]
    article_url: Optional[str]
    facts: List[FactOut]
    facts_source: str
    climate: Optional[str]
    transport: Optional[str]
    local_time: Optional[str]
    emergency: List[EmergencyOut]
    emergency_note: str
    persona_priority: str
    persona_tips: List[str]
    source: SourceStatusOut


class RefreshResponse(BaseModel):
    city: str
    cleared: int


class MethodologyResponse(BaseModel):
    version: str
    summary: List[str]
    formulas: Dict[str, str]
    parameters: Dict[str, object]
    levels: Dict[str, str]
    limitations: List[str]


class ProviderDiagnostic(BaseModel):
    provider: str
    purpose: str
    state: Literal["configured", "not_configured", "enabled", "disabled", "no_key_needed"]
    key_variable: Optional[str] = Field(description="Name of the environment variable that supplied the key (never its value)")
    note: str = ""


class ConfigIssueOut(BaseModel):
    code: str
    message: str


class DiagnosticsResponse(BaseModel):
    env_files: List[str]
    providers: List[ProviderDiagnostic]
    issues: List[ConfigIssueOut]


class ProviderTestOut(BaseModel):
    provider: str
    ok: bool
    kind: Optional[str]
    http_status: Optional[int]
    message: str


class ProviderTestResponse(BaseModel):
    city: str
    results: List[ProviderTestOut]
    weather_used: Optional[str]


class ReadinessResponse(BaseModel):
    ready: bool
    checks: Dict[str, bool]
