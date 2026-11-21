"""
Weather provider adapters
=========================

Both adapters call by **coordinates** (OpenWeatherMap's built-in city-name
geocoding is deprecated) and normalise into ``WeatherData``. The frontend
never sees provider JSON.

OpenWeatherMap (key: OPENWEATHER_API_KEY)
    /data/2.5/weather   current conditions        (free tier)
    /data/2.5/forecast  5 days in 3-hour steps     (free tier)
    /data/3.0/onecall   official alerts            (One Call 3.0 subscription)

Open-Meteo (no key; CC BY 4.0 – "Weather data by Open-Meteo.com")
    /v1/forecast  current, hourly (48 h used) and daily (7 days)
    No official alerts: Open-Meteo is a forecast model, not a warning service.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from ..http import HttpPolicy, ProviderError, get_json

OWM_CURRENT = "https://api.openweathermap.org/data/2.5/weather"
OWM_FORECAST = "https://api.openweathermap.org/data/2.5/forecast"
OWM_ONECALL = "https://api.openweathermap.org/data/3.0/onecall"
OPEN_METEO = "https://api.open-meteo.com/v1/forecast"

OWM_ATTRIBUTION = "Weather data by OpenWeather (openweathermap.org)"
OM_ATTRIBUTION = "Weather data by Open-Meteo.com (CC BY 4.0)"


@dataclass
class CurrentWeather:
    temperature_c: Optional[float]
    feels_like_c: Optional[float]
    humidity_pct: Optional[float]
    wind_kmh: Optional[float]
    wind_dir_deg: Optional[float]
    wind_gust_kmh: Optional[float]
    precipitation_mm: Optional[float]
    visibility_km: Optional[float]
    pressure_hpa: Optional[float]
    clouds_pct: Optional[float]
    condition: str
    group: str  # clear|clouds|fog|drizzle|rain|heavy_rain|snow|thunderstorm|dust|extreme
    observed_at: Optional[datetime]
    sunrise_local: Optional[str] = None
    sunset_local: Optional[str] = None


@dataclass
class HourPoint:
    time: datetime
    temp_c: Optional[float]
    precip_mm: Optional[float]
    precip_prob: Optional[float]


@dataclass
class DayPoint:
    date: str
    condition: str
    temp_min_c: Optional[float]
    temp_max_c: Optional[float]
    precip_mm: Optional[float]
    precip_prob: Optional[float]
    wind_max_kmh: Optional[float]


@dataclass
class WeatherData:
    provider: str
    attribution: str
    current: CurrentWeather
    hourly: List[HourPoint] = field(default_factory=list)
    hourly_step_hours: int = 1
    daily: List[DayPoint] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Condition codes
# ---------------------------------------------------------------------------

def owm_group(code: int) -> str:
    if 200 <= code < 300:
        return "thunderstorm"
    if 300 <= code < 400:
        return "drizzle"
    if code in (502, 503, 504, 522, 531):
        return "heavy_rain"
    if 500 <= code < 600:
        return "rain"
    if 600 <= code < 700:
        return "snow"
    if code in (701, 711, 721, 741):
        return "fog"
    if code == 781:
        return "extreme"
    if 700 <= code < 800:
        return "dust"
    if code == 800:
        return "clear"
    return "clouds"


WMO = {
    0: ("Clear sky", "clear"), 1: ("Mainly clear", "clear"), 2: ("Partly cloudy", "clouds"),
    3: ("Overcast", "clouds"), 45: ("Fog", "fog"), 48: ("Depositing rime fog", "fog"),
    51: ("Light drizzle", "drizzle"), 53: ("Drizzle", "drizzle"), 55: ("Dense drizzle", "drizzle"),
    56: ("Freezing drizzle", "drizzle"), 57: ("Dense freezing drizzle", "drizzle"),
    61: ("Slight rain", "rain"), 63: ("Moderate rain", "rain"), 65: ("Heavy rain", "heavy_rain"),
    66: ("Freezing rain", "rain"), 67: ("Heavy freezing rain", "heavy_rain"),
    71: ("Slight snow", "snow"), 73: ("Moderate snow", "snow"), 75: ("Heavy snow", "snow"),
    77: ("Snow grains", "snow"), 80: ("Rain showers", "rain"), 81: ("Moderate rain showers", "rain"),
    82: ("Violent rain showers", "heavy_rain"), 85: ("Snow showers", "snow"), 86: ("Heavy snow showers", "snow"),
    95: ("Thunderstorm", "thunderstorm"), 96: ("Thunderstorm with hail", "thunderstorm"),
    99: ("Thunderstorm with heavy hail", "thunderstorm"),
}


def _num(v: Any) -> Optional[float]:
    if isinstance(v, bool) or v is None:
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if f == f else None  # drop NaN


def _require(d: Any, *keys: str, provider: str) -> Any:
    cur = d
    for k in keys:
        if not isinstance(cur, dict) or k not in cur:
            raise ProviderError(provider, "bad_response", detail=f"missing field {'.'.join(keys)}")
        cur = cur[k]
    return cur


# ---------------------------------------------------------------------------
# OpenWeatherMap
# ---------------------------------------------------------------------------

def _hhmm(ts: Optional[int], offset_s: int) -> Optional[str]:
    if not ts:
        return None
    return datetime.fromtimestamp(ts + offset_s, tz=timezone.utc).strftime("%H:%M")


def fetch_openweather(lat: float, lon: float, key: str, policy: HttpPolicy) -> WeatherData:
    p = "OpenWeatherMap"
    if not key:
        raise ProviderError(p, "not_configured")
    base = {"lat": lat, "lon": lon, "appid": key, "units": "metric"}
    d = get_json(p, OWM_CURRENT, params=base, policy=policy)
    main = _require(d, "main", provider=p)
    w0 = (d.get("weather") or [{}])[0] if isinstance(d.get("weather"), list) else {}
    code = int(w0.get("id") or 0)
    if _num(main.get("temp")) is None:
        raise ProviderError(p, "bad_response", detail="no temperature")
    offset = int(d.get("timezone") or 0)
    wind = d.get("wind") or {}
    rain = (d.get("rain") or {}).get("1h")
    vis = _num(d.get("visibility"))
    current = CurrentWeather(
        temperature_c=_num(main.get("temp")), feels_like_c=_num(main.get("feels_like")),
        humidity_pct=_num(main.get("humidity")),
        wind_kmh=round(_num(wind.get("speed")) * 3.6, 1) if _num(wind.get("speed")) is not None else None,
        wind_dir_deg=_num(wind.get("deg")),
        wind_gust_kmh=round(_num(wind.get("gust")) * 3.6, 1) if _num(wind.get("gust")) is not None else None,
        precipitation_mm=_num(rain), visibility_km=round(vis / 1000, 1) if vis is not None else None,
        pressure_hpa=_num(main.get("pressure")), clouds_pct=_num((d.get("clouds") or {}).get("all")),
        condition=(w0.get("description") or "").capitalize() or "Not reported", group=owm_group(code),
        observed_at=datetime.fromtimestamp(d["dt"], tz=timezone.utc) if isinstance(d.get("dt"), int) else None,
        sunrise_local=_hhmm((d.get("sys") or {}).get("sunrise"), offset),
        sunset_local=_hhmm((d.get("sys") or {}).get("sunset"), offset),
    )
    data = WeatherData(p, OWM_ATTRIBUTION, current, hourly_step_hours=3)
    try:
        fc = get_json(p, OWM_FORECAST, params=base, policy=policy)
        f_off = int((fc.get("city") or {}).get("timezone") or offset)
        days: Dict[str, List[dict]] = {}
        for slot in fc.get("list") or []:
            t = datetime.fromtimestamp(slot["dt"], tz=timezone.utc)
            m = slot.get("main") or {}
            rain3 = _num((slot.get("rain") or {}).get("3h")) or 0.0
            snow3 = _num((slot.get("snow") or {}).get("3h")) or 0.0
            if len(data.hourly) < 16:  # 48 h in 3-hour steps
                data.hourly.append(HourPoint(t, _num(m.get("temp")), round(rain3 + snow3, 1), _num(slot.get("pop"))))
            local = datetime.fromtimestamp(slot["dt"] + f_off, tz=timezone.utc).strftime("%Y-%m-%d")
            days.setdefault(local, []).append(slot)
        for day, slots in sorted(days.items())[:5]:
            temps = [_num((s.get("main") or {}).get("temp")) for s in slots]
            temps = [t for t in temps if t is not None]
            descs = [((s.get("weather") or [{}])[0].get("description") or "") for s in slots]
            winds = [(_num((s.get("wind") or {}).get("speed")) or 0) * 3.6 for s in slots]
            precip = sum((_num((s.get("rain") or {}).get("3h")) or 0) + (_num((s.get("snow") or {}).get("3h")) or 0)
                         for s in slots)
            pops = [_num(s.get("pop")) for s in slots if _num(s.get("pop")) is not None]
            data.daily.append(DayPoint(day, (max(set(descs), key=descs.count) if descs else "").capitalize(),
                                       min(temps) if temps else None, max(temps) if temps else None,
                                       round(precip, 1), max(pops) if pops else None,
                                       round(max(winds), 1) if winds else None))
    except ProviderError:
        pass  # forecast is optional; current conditions remain valid
    return data


def fetch_openweather_alerts(lat: float, lon: float, key: str, policy: HttpPolicy) -> List[Dict[str, str]]:
    """Official alerts via One Call 3.0. Raises ProviderError (e.g. 401 when the
    key has no One Call subscription)."""
    p = "OpenWeatherMap alerts"
    d = get_json(p, OWM_ONECALL, params={"lat": lat, "lon": lon, "appid": key, "units": "metric",
                                          "exclude": "minutely,hourly,daily,current"}, policy=policy)
    out = []
    for a in (d.get("alerts") or [])[:6]:
        out.append({
            "event": str(a.get("event") or "Weather alert"),
            "issued_by": str(a.get("sender_name") or ""),
            "start": datetime.fromtimestamp(int(a.get("start") or 0), tz=timezone.utc).isoformat(),
            "end": datetime.fromtimestamp(int(a.get("end") or 0), tz=timezone.utc).isoformat(),
            "description": str(a.get("description") or "")[:700],
            "tags": ", ".join(str(t) for t in (a.get("tags") or [])),
        })
    return out


# ---------------------------------------------------------------------------
# Open-Meteo
# ---------------------------------------------------------------------------

def _parse_local(s: str, tz: Optional[ZoneInfo]) -> Optional[datetime]:
    try:
        dt = datetime.fromisoformat(s)
    except (TypeError, ValueError):
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=tz or timezone.utc)
    return dt.astimezone(timezone.utc)


def fetch_open_meteo(lat: float, lon: float, tz_name: str, policy: HttpPolicy, now: Optional[datetime] = None) -> WeatherData:
    p = "Open-Meteo"
    params = {
        "latitude": lat, "longitude": lon, "timezone": tz_name, "forecast_days": 7,
        "current": "temperature_2m,relative_humidity_2m,apparent_temperature,precipitation,weather_code,"
                   "cloud_cover,pressure_msl,wind_speed_10m,wind_direction_10m,wind_gusts_10m",
        "hourly": "temperature_2m,precipitation,precipitation_probability,visibility",
        "daily": "weather_code,temperature_2m_max,temperature_2m_min,precipitation_sum,"
                 "precipitation_probability_max,wind_speed_10m_max,sunrise,sunset",
        "wind_speed_unit": "kmh",
    }
    d = get_json(p, OPEN_METEO, params=params, policy=policy)
    if isinstance(d, dict) and d.get("error"):
        raise ProviderError(p, "bad_response", detail=str(d.get("reason", ""))[:120])
    try:
        tz = ZoneInfo(tz_name)
    except (ZoneInfoNotFoundError, ValueError):
        tz = None
    cur = _require(d, "current", provider=p)
    if _num(cur.get("temperature_2m")) is None:
        raise ProviderError(p, "bad_response", detail="no temperature")
    code = int(cur.get("weather_code") or 0)
    desc, group = WMO.get(code, ("Not reported", "clouds"))
    observed = _parse_local(str(cur.get("time") or ""), tz)
    hourly = d.get("hourly") or {}
    times = hourly.get("time") or []
    now = now or datetime.now(timezone.utc)
    hours: List[HourPoint] = []
    vis_now = None
    for i, t in enumerate(times):
        ts = _parse_local(t, tz)
        if ts is None:
            continue
        def at(key: str, i: int = i) -> Optional[float]:
            arr = hourly.get(key) or []
            return _num(arr[i]) if i < len(arr) else None
        if ts <= now < ts + timedelta(hours=1):
            vis_now = at("visibility")
        if now - timedelta(hours=1) <= ts <= now + timedelta(hours=48):
            hours.append(HourPoint(ts, at("temperature_2m"), at("precipitation"),
                                   (at("precipitation_probability") or 0) / 100 if at("precipitation_probability") is not None else None))
    daily = d.get("daily") or {}
    days: List[DayPoint] = []
    sunrise = sunset = None
    for i, day in enumerate(daily.get("time") or []):
        def dv(key: str, i: int = i) -> Any:
            arr = daily.get(key) or []
            return arr[i] if i < len(arr) else None
        dcode = int(dv("weather_code") or 0)
        prob = _num(dv("precipitation_probability_max"))
        days.append(DayPoint(str(day), WMO.get(dcode, ("", ""))[0], _num(dv("temperature_2m_min")),
                             _num(dv("temperature_2m_max")), _num(dv("precipitation_sum")),
                             prob / 100 if prob is not None else None, _num(dv("wind_speed_10m_max"))))
        if i == 0:
            sunrise = str(dv("sunrise") or "")[11:16] or None
            sunset = str(dv("sunset") or "")[11:16] or None
    current = CurrentWeather(
        temperature_c=_num(cur.get("temperature_2m")), feels_like_c=_num(cur.get("apparent_temperature")),
        humidity_pct=_num(cur.get("relative_humidity_2m")), wind_kmh=_num(cur.get("wind_speed_10m")),
        wind_dir_deg=_num(cur.get("wind_direction_10m")), wind_gust_kmh=_num(cur.get("wind_gusts_10m")),
        precipitation_mm=_num(cur.get("precipitation")),
        visibility_km=round(vis_now / 1000, 1) if vis_now is not None else None,
        pressure_hpa=_num(cur.get("pressure_msl")), clouds_pct=_num(cur.get("cloud_cover")),
        condition=desc, group=group, observed_at=observed, sunrise_local=sunrise, sunset_local=sunset,
    )
    return WeatherData(p, OM_ATTRIBUTION, current, hours, 1, days[:7])
