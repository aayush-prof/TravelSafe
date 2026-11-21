"""Health, cities, personas and methodology endpoints."""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Query, Request

from core.config import (APP_VERSION, CITY_COORDINATES, DEFAULT_CITY, DEFAULT_PERSONA, METHODOLOGY_VERSION,
                         SUPPORTED_CITIES, config_issues, resolve_city, settings)
from core.env import env_files_found, key_variable
from core.environment_service import fetch_air, fetch_hazards
from core.factors import FACTOR_DEFINITIONS, FACTOR_LABELS, OVERALL_LABELS as FACTOR_OVERALL_LABELS, RELEVANCE
from core.news_client import sample_cities
from core.pipeline import cache_stats
from core.scoring_params import LEVEL_LABELS, PARAMS
from core.weather_service import fetch_weather

from ..schemas import (CitiesResponse, ConfigIssueOut, DiagnosticsResponse, HealthResponse, MethodologyResponse,
                       PersonaInfo, ProviderDiagnostic, ProviderInfo, ProviderTestOut, ProviderTestResponse,
                       ReadinessResponse)
from ..serializers import all_personas, city_info

router = APIRouter(prefix="/api", tags=["meta"])


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(
        status="ok", version=APP_VERSION, methodology_version=METHODOLOGY_VERSION,
        time=datetime.now(timezone.utc),
        providers=ProviderInfo(news_providers=settings.news_providers,
                               weather_configured=settings.any_weather_provider,
                               data_mode=settings.data_mode,  # type: ignore[arg-type]
                               sample_cities=sample_cities(settings)),
        cache=cache_stats(),
    )


@router.get("/ready", response_model=ReadinessResponse)
def ready() -> ReadinessResponse:
    """Readiness: configuration loaded, city data present, at least one source per core factor possible."""
    checks = {
        "cities_loaded": bool(SUPPORTED_CITIES) and all(c in CITY_COORDINATES for c in SUPPORTED_CITIES),
        "news_source_available": bool(settings.news_providers) or bool(sample_cities(settings)),
        "weather_source_enabled": settings.any_weather_provider,
        "hazard_source_enabled": settings.usgs_enabled or settings.gdacs_enabled,
    }
    return ReadinessResponse(ready=all(checks.values()), checks=checks)


def _state(configured: bool) -> str:
    return "configured" if configured else "not_configured"


@router.get("/diagnostics/providers", response_model=DiagnosticsResponse, tags=["diagnostics"])
def diagnostics() -> DiagnosticsResponse:
    """Which providers are set up and likely configuration mistakes. Reports variable and file
    names only; key values are never returned or logged."""
    s = settings
    rows = [
        ProviderDiagnostic(provider="OpenWeatherMap", purpose="Current weather, forecast, official alerts (One Call 3.0)",
                           state=_state(s.weather_configured), key_variable=s.openweather_key_name,  # type: ignore[arg-type]
                           note="" if s.weather_configured else "Optional. Open-Meteo is used without a key."),
        ProviderDiagnostic(provider="Open-Meteo", purpose="Weather fallback and modelled air quality",
                           state="enabled" if s.open_meteo_enabled else "disabled", key_variable=None,
                           note="No key needed. Set OPEN_METEO_ENABLED=false to turn off."),
        ProviderDiagnostic(provider="OpenAQ", purpose="Measured air quality (stations)",
                           state=_state(bool(s.openaq_api_key)), key_variable=key_variable("openaq"),  # type: ignore[arg-type]
                           note="" if s.openaq_api_key else "Optional. Without it, air quality is not assessed."),
        ProviderDiagnostic(provider="USGS", purpose="Earthquakes", state="enabled" if s.usgs_enabled else "disabled",
                           key_variable=None, note="No key needed."),
        ProviderDiagnostic(provider="GDACS", purpose="Disaster alerts", state="enabled" if s.gdacs_enabled else "disabled",
                           key_variable=None, note="No key needed."),
        ProviderDiagnostic(provider="NewsAPI", purpose="News", state=_state(bool(s.news_api_key)),  # type: ignore[arg-type]
                           key_variable=key_variable("newsapi")),
        ProviderDiagnostic(provider="GNews", purpose="News", state=_state(bool(s.gnews_api_key)),  # type: ignore[arg-type]
                           key_variable=key_variable("gnews")),
        ProviderDiagnostic(provider="Google News RSS", purpose="News",
                           state="enabled" if s.enable_google_rss else "disabled", key_variable=None,
                           note="No key needed."),
    ]
    return DiagnosticsResponse(env_files=env_files_found(), providers=rows,
                               issues=[ConfigIssueOut(**i) for i in config_issues()])


_LOCAL = {"127.0.0.1", "::1", "localhost", "testclient"}


@router.post("/diagnostics/providers/test", response_model=ProviderTestResponse, tags=["diagnostics"])
def diagnostics_test(request: Request, city: str = Query(DEFAULT_CITY)) -> ProviderTestResponse:
    """Run one live request per provider for a city and report the outcome by error class.
    Only answers requests from this machine, because it triggers external API calls."""
    host = request.client.host if request.client else ""
    if host not in _LOCAL:
        raise HTTPException(status_code=403, detail="Provider tests can only be run from the server machine.")
    resolved = resolve_city(city)
    if resolved is None:
        raise HTTPException(status_code=404, detail="Unsupported city")
    w = fetch_weather(resolved, settings)
    air = fetch_air(resolved, settings)
    hz = fetch_hazards(resolved, settings)
    results = [ProviderTestOut(provider=a.provider, ok=a.ok, kind=a.kind, http_status=a.status,
                               message="OK" if a.ok else a.message)
               for a in w.attempts + air.attempts + hz.attempts]
    if w.ok and w.provider == "OpenWeatherMap":
        results.append(ProviderTestOut(provider="OpenWeatherMap alerts", ok=w.alerts_status == "available",
                                       kind=None if w.alerts_status == "available" else w.alerts_status,
                                       http_status=None,
                                       message={"available": "OK",
                                                "not_subscribed": "Key has no One Call 3.0 subscription"}.get(
                                           w.alerts_status, "Alerts request failed")))
    return ProviderTestResponse(city=resolved, results=results, weather_used=w.provider)


@router.get("/cities", response_model=CitiesResponse)
def cities() -> CitiesResponse:
    return CitiesResponse(cities=[city_info(c) for c in SUPPORTED_CITIES], personas=all_personas(),
                          default_city=DEFAULT_CITY, default_persona=DEFAULT_PERSONA)


@router.get("/personas", response_model=list[PersonaInfo])
def personas() -> list[PersonaInfo]:
    return all_personas()


@router.get("/methodology", response_model=MethodologyResponse)
def methodology() -> MethodologyResponse:
    p = PARAMS
    return MethodologyResponse(
        version=METHODOLOGY_VERSION,
        summary=[
            "Six factors are assessed separately: crime & security, civil disruption, transport disruption, natural hazards, weather and air quality.",
            "Each factor reports its level, evidence, sources, time window, geographic match, freshness and confidence. A factor without a working source is 'not assessed' – missing data is never treated as low risk.",
            "News factors: articles are classified with a severity (-3..+3) and a separate confidence; reports that don't name the city are down-weighted or excluded; repeated coverage is merged; older reports fade with a half-life.",
            "Natural hazards combine USGS earthquakes (by magnitude and distance) and GDACS alerts (within a hazard-specific radius) with news. A news report of an event already in the feeds is not counted twice.",
            "Weather uses measured conditions and the 48-hour forecast from OpenWeatherMap or Open-Meteo, plus official alerts when available. Weather news corroborates at half weight. Climate averages are context only.",
            "Air quality uses station measurements (OpenAQ) only. Modelled values are shown as context and never lower or raise the assessment.",
            "Critical alerts are never averaged away: a red GDACS alert sets the overall level to at least High; an orange alert, a severe nearby earthquake or a credible severe incident to at least Elevated; an official weather alert to at least Guarded.",
            "The favourable side of the index is scaled by coverage and by the share of factors that could be assessed, so a city can't look safe because data is missing.",
            "Traveller profiles change how much each factor matters; they never add risk where there is no evidence.",
        ],
        formulas={
            "event_impact": "impact[severity] × confidence × location_confidence × 0.5^(age_days / half_life) × (0.15 if historical) × (0.6 if resolved by arrest)",
            "factor_pressure": "P = max_impact + min(volume_cap, volume_weight × ln(1 + sum of other impacts))",
            "factor_risk": "R = 1 − exp(−P / saturation)",
            "hazard_feed_impact": "impact[severity] × 0.95 × 0.5^(age_days / 10); severity from magnitude/distance (USGS) or alert level/radius (GDACS)",
            "weather_risk": "R = 1 − (1 − R_live) × (1 − 0.5 × R_news); R_live = 1 − exp(−points / 6)",
            "air_quality_risk": "US EPA category of the latest PM2.5/PM10 reading → Good 0.03, Moderate 0.10, USG 0.25, Unhealthy 0.45, Very unhealthy 0.65, Hazardous 0.80",
            "overall_risk": "a_f = relevance_f × R_f over assessed factors (sorted); R = a₁ + (1 − a₁) × 0.35 × (1 − Π(1 − a_rest)); R = max(R, critical-alert floor)",
            "persona_risk": "R'_f = 1 − (1 − R_f)^weight_f",
            "index": "index = 10 − 20 × R; positive values × coverage factor (good 1.0, limited 0.5) × assessed share of factor weight; insufficient → no index",
        },
        parameters={
            "impact_by_severity": {str(k): v for k, v in p.impact_by_severity.items()},
            "half_life_days": p.half_life_days, "max_event_age_days": p.max_event_age_days,
            "window_days": p.window_days, "historical_factor": p.historical_factor,
            "resolved_factor": p.resolved_factor, "min_location_confidence": p.min_location_confidence,
            "volume_weight": p.volume_weight, "volume_cap": p.volume_cap, "saturation": p.saturation,
            "category_relevance": p.category_relevance, "secondary_damping": p.secondary_damping,
            "level_thresholds": {k: b for b, k in p.level_thresholds},
            "coverage": {"good_min_articles": p.good_min_articles, "some_min_articles": p.some_min_articles,
                         "fresh_hours": p.fresh_hours, "stale_after_days": p.stale_after_days,
                         "positive_factor": p.coverage_positive_factor},
            "dedup": {"similarity": p.dedup_similarity, "window_hours": p.dedup_window_hours},
            "factor_relevance": RELEVANCE,
            "critical_floors": {"guarded": 0.15, "elevated": 0.35, "high": 0.60},
            "coverage_overall": {"insufficient_below_assessed_share": 0.35, "good_from_assessed_share": 0.8},
            "factors": {k: {"label": FACTOR_LABELS[k], "definition": FACTOR_DEFINITIONS[k]} for k in FACTOR_LABELS},
            "overall_labels": FACTOR_OVERALL_LABELS,
        },
        levels=LEVEL_LABELS,
        limitations=[
            "News coverage is not crime incidence: well-covered cities generate more reports.",
            "Parameters are reasoned heuristics, not statistically calibrated probabilities.",
            "Keyword classification can misread unusual phrasing; every event shows its matched terms and confidence.",
            "Incident dates are rarely provided by news APIs; publication dates are used and labelled as such.",
            "Cities are not directly comparable when their coverage differs.",
            "Air-quality categories use the latest hourly value, not the 24-hour average used for official AQI.",
            "Hazard radii and weather thresholds are reasoned defaults (IMD rainfall bands, common heat and wind limits), not local warning criteria.",
            "Official weather alerts are only available with an OpenWeatherMap One Call 3.0 subscription; without it, their absence means 'not checked', not 'none'.",
        ],
    )
