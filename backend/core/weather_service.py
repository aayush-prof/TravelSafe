"""
Weather service
===============

Order of providers for a city (coordinates from ``config.CITY_COORDINATES``):

1. OpenWeatherMap, if ``OPENWEATHER_API_KEY`` is configured.
2. Open-Meteo, if enabled (default) – used when OpenWeatherMap is not
   configured or fails for any reason. Only genuine provider data is used;
   sample data is never substituted for weather.

Official alerts come only from OpenWeatherMap One Call 3.0 (needs that
subscription). With Open-Meteo, alerts are reported as "not provided by this
source" – never as "none".

Condition scoring (heuristic, documented in README):

    current:   heat ≥40 °C 3 | ≥35 °C 2 ; cold ≤0 °C 3 | ≤5 °C 1 ; wind ≥50 km/h 3 | ≥30 1 ;
               visibility <1 km 2 | <2 km 1 ; thunderstorm 2 ; heavy rain/snow 2 ;
               rain 1 ; dust/sand 3 ; tornado/extreme 4
    forecast (today + tomorrow, × 0.7):
               rain ≥115.6 mm/day 3 | ≥64.5 mm/day 2   (IMD "very heavy" / "heavy" bands)
               max ≥45 °C 3 | ≥40 °C 2 ; min ≤0 °C 1 ; wind ≥62 km/h 2 | ≥50 km/h 1
    alerts:    each official alert 3 (max 2)
    risk = 1 − exp(−points / 6)
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

from .config import CITY_COORDINATES, CITY_TIMEZONES, Settings
from .http import HttpPolicy, ProviderError
from .logging_setup import get_logger
from .providers.weather import WeatherData, fetch_open_meteo, fetch_openweather, fetch_openweather_alerts
from .scoring import LiveWeatherSignal
from .scoring_params import PARAMS

log = get_logger("weather")


@dataclass
class Attempt:
    provider: str
    ok: bool
    kind: Optional[str] = None
    status: Optional[int] = None
    message: str = ""


@dataclass
class WeatherReport:
    city: str
    status: str  # live | unavailable
    data: Optional[WeatherData] = None
    fetched_at: Optional[datetime] = None
    alerts: Optional[List[Dict[str, str]]] = None
    alerts_status: str = "unavailable"  # available | not_subscribed | not_supported | unavailable
    attempts: List[Attempt] = field(default_factory=list)
    reason_kind: Optional[str] = None
    signal: LiveWeatherSignal = field(default_factory=lambda: LiveWeatherSignal(False))
    forecast_hazards: List[str] = field(default_factory=list)
    advice: List[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.status == "live" and self.data is not None

    @property
    def provider(self) -> Optional[str]:
        return self.data.provider if self.data else None

    @property
    def public_reason(self) -> str:
        """Plain-language reason when no provider succeeded."""
        if self.ok:
            return ""
        kinds = {a.provider: a.kind for a in self.attempts}
        if not self.attempts:
            return "No weather provider is enabled for this installation."
        ow = kinds.get("OpenWeatherMap")
        if ow == "unauthorized":
            return ("The weather service rejected the OpenWeatherMap key. New keys can take a while to activate; "
                    "if it's older, check it was copied correctly.")
        if ow == "rate_limited":
            return "The weather service's request limit was reached. Try again later."
        if all(k in ("network", "timeout") for k in kinds.values() if k):
            return "The weather services couldn't be reached from the TravelSafe server. Check its internet connection."
        if any(k == "bad_response" for k in kinds.values()):
            return "The weather response couldn't be interpreted."
        return "Weather services are temporarily unavailable."


def _points_current(c) -> Tuple[float, List[str], List[str]]:
    pts = 0.0
    f: List[str] = []
    adv: List[str] = []
    t, feels, wind, vis, g = c.temperature_c, c.feels_like_c, c.wind_kmh, c.visibility_km, c.group
    if t is not None:
        if t >= 40:
            pts += 3; f.append(f"Extreme heat ({t:.0f} °C)")
            adv.append("Avoid outdoor activity between 11:00 and 16:00 and carry water.")
        elif t >= 35:
            pts += 2; f.append(f"High temperature ({t:.0f} °C)")
            adv.append("Plan outdoor sightseeing for mornings and evenings; stay hydrated.")
        elif t <= 0:
            pts += 3; f.append(f"Freezing temperature ({t:.0f} °C)")
            adv.append("Dress in layers and watch for ice on roads and pavements.")
        elif t <= 5:
            pts += 1; f.append(f"Cold ({t:.0f} °C)")
        if feels is not None and feels >= 41 and t < 40:
            pts += 1; f.append(f"High heat index (feels like {feels:.0f} °C)")
    if wind is not None:
        if wind >= 50:
            pts += 3; f.append(f"Strong winds ({wind:.0f} km/h)")
            adv.append("Expect possible transport disruption; avoid exposed and coastal areas.")
        elif wind >= 30:
            pts += 1; f.append(f"Moderate winds ({wind:.0f} km/h)")
    if vis is not None:
        if vis < 1:
            pts += 2; f.append(f"Very low visibility ({vis:g} km)")
            adv.append("Allow extra time for road and air travel; fog delays are likely.")
        elif vis < 2:
            pts += 1; f.append(f"Reduced visibility ({vis:g} km)")
    if g == "thunderstorm":
        pts += 2; f.append("Thunderstorm")
        adv.append("Stay indoors during lightning; avoid open ground and water.")
    elif g == "heavy_rain":
        pts += 2; f.append("Heavy rain")
        adv.append("Expect waterlogging or slow traffic; keep plans flexible.")
    elif g in ("rain", "snow"):
        pts += 1; f.append("Rain" if g == "rain" else "Snow")
    elif g == "dust":
        pts += 3; f.append("Dust, sand or haze")
    elif g == "extreme":
        pts += 4; f.append("Extreme weather reported")
    return pts, f, adv


def _points_forecast(days) -> Tuple[float, List[str]]:
    pts = 0.0
    hz: List[str] = []
    for d in days[:2]:
        label = "Today" if d is days[0] else "Tomorrow"
        if d.precip_mm is not None:
            if d.precip_mm >= 115.6:
                pts += 3; hz.append(f"{label}: very heavy rain forecast ({d.precip_mm:.0f} mm)")
            elif d.precip_mm >= 64.5:
                pts += 2; hz.append(f"{label}: heavy rain forecast ({d.precip_mm:.0f} mm)")
        if d.temp_max_c is not None:
            if d.temp_max_c >= 45:
                pts += 3; hz.append(f"{label}: extreme heat forecast ({d.temp_max_c:.0f} °C)")
            elif d.temp_max_c >= 40:
                pts += 2; hz.append(f"{label}: heat forecast ({d.temp_max_c:.0f} °C)")
        if d.temp_min_c is not None and d.temp_min_c <= 0:
            pts += 1; hz.append(f"{label}: freezing temperatures forecast")
        if d.wind_max_kmh is not None:
            if d.wind_max_kmh >= 62:
                pts += 2; hz.append(f"{label}: gale-force winds forecast ({d.wind_max_kmh:.0f} km/h)")
            elif d.wind_max_kmh >= 50:
                pts += 1; hz.append(f"{label}: strong winds forecast ({d.wind_max_kmh:.0f} km/h)")
    return pts * 0.7, hz


def assess_conditions(data: WeatherData, alerts: Optional[List[Dict[str, str]]]) -> Tuple[LiveWeatherSignal, List[str], List[str]]:
    pts, factors, advice = _points_current(data.current)
    fpts, hazards = _points_forecast(data.daily)
    pts += fpts
    if alerts:
        pts += 3 * min(2, len(alerts))
        factors.append(f"{len(alerts)} official weather alert(s)")
        advice.append("Follow the instructions in the official alerts.")
    risk = 1.0 - math.exp(-pts / PARAMS.weather_saturation)
    return LiveWeatherSignal(True, round(risk, 4), factors + hazards), hazards, advice


def fetch_weather(city: str, s: Settings, now: Optional[datetime] = None) -> WeatherReport:
    coords = CITY_COORDINATES.get(city)
    report = WeatherReport(city, "unavailable")
    if not coords:
        report.reason_kind = "not_found"
        return report
    lat, lon = coords["lat"], coords["lon"]
    policy = HttpPolicy(connect_timeout=s.connect_timeout_seconds, read_timeout=s.request_timeout_seconds,
                        retries=s.http_retries)
    data: Optional[WeatherData] = None
    if s.weather_configured:
        try:
            data = fetch_openweather(lat, lon, s.openweather_api_key, policy)
            report.attempts.append(Attempt("OpenWeatherMap", True))
        except ProviderError as e:
            report.attempts.append(Attempt("OpenWeatherMap", False, e.kind, e.status, e.public_message))
            log.warning("weather city=%s OpenWeatherMap failed: kind=%s status=%s detail=%s", city, e.kind, e.status, e.detail)
    else:
        report.attempts.append(Attempt("OpenWeatherMap", False, "not_configured", None, "OpenWeatherMap not configured"))
    if data is None and s.open_meteo_enabled:
        try:
            data = fetch_open_meteo(lat, lon, CITY_TIMEZONES.get(city, "GMT"), policy, now)
            report.attempts.append(Attempt("Open-Meteo", True))
        except ProviderError as e:
            report.attempts.append(Attempt("Open-Meteo", False, e.kind, e.status, e.public_message))
            log.warning("weather city=%s Open-Meteo failed: kind=%s detail=%s", city, e.kind, e.detail)
    if data is None:
        failed = [a for a in report.attempts if not a.ok and a.kind != "not_configured"]
        report.reason_kind = failed[0].kind if failed else "not_configured"
        return report

    report.status, report.data, report.fetched_at = "live", data, datetime.now(timezone.utc)
    if data.provider == "OpenWeatherMap":
        try:
            report.alerts = fetch_openweather_alerts(lat, lon, s.openweather_api_key, policy)
            report.alerts_status = "available"
        except ProviderError as e:
            report.alerts = None
            report.alerts_status = "not_subscribed" if e.kind in ("unauthorized", "forbidden") else "unavailable"
    else:
        report.alerts, report.alerts_status = None, "not_supported"
    report.signal, report.forecast_hazards, report.advice = assess_conditions(data, report.alerts)
    log.info("weather city=%s provider=%s risk=%.2f alerts=%s", city, data.provider, report.signal.risk,
             report.alerts_status)
    return report
