"""
Air-quality provider adapters
=============================

OpenAQ v3 (key: OPENAQ_API_KEY, header ``X-API-Key``) – **measured** values
from monitoring stations. We search within 25 km (the API maximum) of the
city coordinates, pick the nearest station with a recent PM2.5 or PM10
reading, and report its distance and timestamp.

Open-Meteo Air Quality (no key, CC BY 4.0) – **modelled** CAMS estimates on a
~45 km global grid. Shown as context only; it never changes the assessment.

Indicative AQI uses US EPA breakpoints (PM2.5 revised 2024) applied to the
latest hourly value. A proper AQI uses 24-hour averages, so the UI labels it
"indicative".
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from ..geo import haversine_km
from ..http import HttpPolicy, ProviderError, get_json

OPENAQ = "https://api.openaq.org/v3"
OM_AQ = "https://air-quality-api.open-meteo.com/v1/air-quality"
OPENAQ_ATTRIBUTION = "Air-quality measurements via OpenAQ (openaq.org); data from the station operator"
OM_AQ_ATTRIBUTION = "Modelled air quality by Open-Meteo.com (CAMS, CC BY 4.0)"

# (upper bound inclusive, category, level)
PM25_BREAKS = [(9.0, "Good"), (35.4, "Moderate"), (55.4, "Unhealthy for sensitive groups"),
               (125.4, "Unhealthy"), (225.4, "Very unhealthy"), (float("inf"), "Hazardous")]
PM10_BREAKS = [(54, "Good"), (154, "Moderate"), (254, "Unhealthy for sensitive groups"),
               (354, "Unhealthy"), (424, "Very unhealthy"), (float("inf"), "Hazardous")]
CATEGORY_ORDER = [b[1] for b in PM25_BREAKS]
PARAM_LABEL = {"pm25": "PM2.5", "pm10": "PM10", "no2": "NO₂", "o3": "O₃", "so2": "SO₂", "co": "CO"}


def category_for(param: str, value: float) -> Optional[str]:
    table = PM25_BREAKS if param == "pm25" else PM10_BREAKS if param == "pm10" else None
    if table is None or value is None or value < 0:
        return None
    for bound, cat in table:
        if value <= bound:
            return cat
    return None


@dataclass
class Reading:
    parameter: str
    label: str
    value: float
    unit: str
    observed_at: Optional[datetime]


@dataclass
class TrendPoint:
    time: datetime
    pm25: Optional[float]


@dataclass
class MeasuredAir:
    station: str
    distance_km: float
    readings: List[Reading]
    category: Optional[str]
    driver: Optional[str]  # parameter that determined the category
    observed_at: Optional[datetime]
    trend: List[TrendPoint] = field(default_factory=list)
    attribution: str = OPENAQ_ATTRIBUTION


@dataclass
class ModelledAir:
    pm25: Optional[float]
    pm10: Optional[float]
    us_aqi: Optional[float]
    category: Optional[str]
    observed_at: Optional[datetime]
    trend: List[TrendPoint] = field(default_factory=list)
    attribution: str = OM_AQ_ATTRIBUTION


def _num(v: Any) -> Optional[float]:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if f == f and f >= 0 else None


def _utc(s: Any) -> Optional[datetime]:
    if not isinstance(s, str):
        return None
    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def worst_category(values: Dict[str, float]) -> Tuple[Optional[str], Optional[str]]:
    best: Tuple[int, Optional[str], Optional[str]] = (-1, None, None)
    for p, v in values.items():
        c = category_for(p, v)
        if c is not None and CATEGORY_ORDER.index(c) > best[0]:
            best = (CATEGORY_ORDER.index(c), c, p)
    return best[1], best[2]


def fetch_openaq(lat: float, lon: float, key: str, policy: HttpPolicy, now: Optional[datetime] = None,
                 max_age_hours: float = 48) -> MeasuredAir:
    p = "OpenAQ"
    if not key:
        raise ProviderError(p, "not_configured")
    now = now or datetime.now(timezone.utc)
    hdr = {"X-API-Key": key}
    locs = get_json(p, f"{OPENAQ}/locations", params={"coordinates": f"{lat:.4f},{lon:.4f}", "radius": 25000,
                                                      "limit": 25}, headers=hdr, policy=policy)
    results = locs.get("results") if isinstance(locs, dict) else None
    if not isinstance(results, list):
        raise ProviderError(p, "bad_response", detail="no results list")
    candidates = []
    for loc in results:
        c = loc.get("coordinates") or {}
        try:  # coordinates can be negative, so don't use _num()
            la, lo = float(c.get("latitude")), float(c.get("longitude"))
        except (TypeError, ValueError):
            continue
        sensors = {s.get("id"): (s.get("parameter") or {}) for s in loc.get("sensors") or [] if s.get("id") is not None}
        if not any((pp.get("name") in ("pm25", "pm10")) for pp in sensors.values()):
            continue
        last = _utc(((loc.get("datetimeLast") or {}).get("utc")))
        if last is None or now - last > timedelta(hours=max_age_hours):
            continue
        candidates.append((haversine_km(lat, lon, la, lo), loc, sensors))
    if not candidates:
        raise ProviderError(p, "no_data", detail="no station with recent PM readings within 25 km")
    dist, loc, sensors = min(candidates, key=lambda x: x[0])
    latest = get_json(p, f"{OPENAQ}/locations/{loc['id']}/latest", headers=hdr, policy=policy)
    readings: List[Reading] = []
    newest: Optional[datetime] = None
    for r in (latest.get("results") or []) if isinstance(latest, dict) else []:
        param = sensors.get(r.get("sensorsId")) or {}
        name = param.get("name")
        val = _num(r.get("value"))
        when = _utc(((r.get("datetime") or {}).get("utc")))
        if not name or val is None or when is None or now - when > timedelta(hours=max_age_hours):
            continue
        readings.append(Reading(name, PARAM_LABEL.get(name, name.upper()), round(val, 1), str(param.get("units") or ""), when))
        newest = max(newest, when) if newest else when
    if not readings:
        raise ProviderError(p, "no_data", detail="station has no recent readings")
    cat, driver = worst_category({r.parameter: r.value for r in readings if r.parameter in ("pm25", "pm10")})
    measured = MeasuredAir(str(loc.get("name") or "Monitoring station"), round(dist, 1), readings, cat, driver, newest)
    pm25_sensor = next((sid for sid, pp in sensors.items() if pp.get("name") == "pm25"), None)
    if pm25_sensor is not None:
        try:
            hist = get_json(p, f"{OPENAQ}/sensors/{pm25_sensor}/hours", headers=hdr, policy=policy,
                            params={"datetime_from": (now - timedelta(hours=72)).strftime("%Y-%m-%dT%H:%M:%SZ"),
                                    "limit": 100})
            for h in (hist.get("results") or []) if isinstance(hist, dict) else []:
                t = _utc((((h.get("period") or {}).get("datetimeFrom") or {}).get("utc")))
                v = _num(h.get("value"))
                if t and v is not None:
                    measured.trend.append(TrendPoint(t, round(v, 1)))
            measured.trend.sort(key=lambda x: x.time)
        except ProviderError:
            measured.trend = []  # trend is optional
    return measured


def fetch_open_meteo_air(lat: float, lon: float, policy: HttpPolicy, now: Optional[datetime] = None) -> ModelledAir:
    p = "Open-Meteo air quality"
    now = now or datetime.now(timezone.utc)
    d = get_json(p, OM_AQ, params={"latitude": lat, "longitude": lon, "timezone": "GMT",
                                    "current": "pm2_5,pm10,us_aqi", "hourly": "pm2_5",
                                    "past_days": 2, "forecast_days": 1}, policy=policy)
    if not isinstance(d, dict) or d.get("error"):
        raise ProviderError(p, "bad_response")
    cur = d.get("current") or {}
    pm25, pm10 = _num(cur.get("pm2_5")), _num(cur.get("pm10"))
    if pm25 is None and pm10 is None:
        raise ProviderError(p, "no_data")
    vals = {k: v for k, v in (("pm25", pm25), ("pm10", pm10)) if v is not None}
    cat, _ = worst_category(vals)
    trend = []
    h = d.get("hourly") or {}
    for t, v in zip(h.get("time") or [], h.get("pm2_5") or [], strict=False):
        ts = _utc(str(t) + ("" if str(t).endswith("Z") else "+00:00"))
        if ts and ts <= now and _num(v) is not None:
            trend.append(TrendPoint(ts, round(float(v), 1)))
    return ModelledAir(pm25, pm10, _num(cur.get("us_aqi")), cat,
                       _utc(str(cur.get("time") or "") + "+00:00"), trend[-48:])
