"""Recorded-format provider responses (shapes follow each provider's public
documentation) and a tiny URL router for ``requests.get``."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Dict, List, Optional, Union

import requests


class FakeResp:
    def __init__(self, status: int = 200, json_data: Any = None, content: bytes = b"", text: Optional[str] = None):
        self.status_code = status
        self._json = json_data
        self.content = content if content else (json.dumps(json_data).encode() if json_data is not None else b"")
        self._text = text

    def json(self):
        if self._text is not None:
            return json.loads(self._text)  # raises ValueError for malformed bodies
        if self._json is None:
            raise ValueError("no JSON body")
        return self._json

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.exceptions.HTTPError(f"{self.status_code} error", response=self)


Handler = Union[FakeResp, Exception, Callable[..., Any], List[Any]]


class Router:
    """Route ``requests.get`` by URL substring. A list value is consumed in order
    (the last item repeats). Unknown URLs raise ConnectionError, like the test
    sandbox's blocked network. ``calls`` records (url, params, headers)."""

    def __init__(self, routes: Dict[str, Handler]):
        self.routes = routes
        self.calls: List[tuple] = []

    def __call__(self, url, params=None, headers=None, timeout=None, **kw):
        self.calls.append((url, params or {}, headers or {}))
        for frag, h in self.routes.items():
            if frag in url:
                if isinstance(h, list):
                    h = h.pop(0) if len(h) > 1 else h[0]
                if isinstance(h, Exception):
                    raise h
                if callable(h) and not isinstance(h, FakeResp):
                    return h(url, params=params, headers=headers)
                return h
        raise requests.exceptions.ConnectionError(f"blocked: {url}")

    def count(self, frag: str) -> int:
        return sum(1 for c in self.calls if frag in c[0])


def now_utc() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


# --- OpenWeatherMap -------------------------------------------------------

def owm_current(temp=24.0, code=800, desc="clear sky", wind_ms=3.0, vis=10000, now=None) -> dict:
    now = now or now_utc()
    return {"coord": {"lon": 77.59, "lat": 12.97}, "weather": [{"id": code, "main": "X", "description": desc}],
            "main": {"temp": temp, "feels_like": temp + 1, "humidity": 60, "pressure": 1012},
            "visibility": vis, "wind": {"speed": wind_ms, "deg": 200}, "clouds": {"all": 10},
            "dt": int(now.timestamp()), "sys": {"sunrise": int(now.timestamp()) - 20000,
                                               "sunset": int(now.timestamp()) + 20000},
            "timezone": 19800, "name": "Bengaluru", "cod": 200}


def owm_forecast(temp=24.0, rain3h=0.0, now=None) -> dict:
    now = now or now_utc()
    lst = []
    for i in range(40):
        slot = {"dt": int((now + timedelta(hours=3 * i)).timestamp()),
                "main": {"temp": temp + (i % 8) - 4}, "wind": {"speed": 3}, "pop": 0.2,
                "weather": [{"id": 500 if rain3h else 800, "description": "light rain" if rain3h else "clear sky"}]}
        if rain3h:
            slot["rain"] = {"3h": rain3h}
        lst.append(slot)
    return {"cod": "200", "cnt": 40, "list": lst, "city": {"timezone": 19800}}


def owm_onecall_alerts(events: List[str], now=None) -> dict:
    now = now or now_utc()
    return {"lat": 12.97, "lon": 77.59, "timezone": "Asia/Kolkata", "alerts": [
        {"sender_name": "India Meteorological Department", "event": e, "start": int(now.timestamp()),
         "end": int((now + timedelta(hours=12)).timestamp()), "description": f"{e} expected.", "tags": ["Rain"]}
        for e in events]}


# --- Open-Meteo -----------------------------------------------------------

def open_meteo(temp=25.0, code=1, precip_day=0.0, tmax=29.0, wind_max=15.0, tz="Asia/Kolkata", now=None) -> dict:
    from zoneinfo import ZoneInfo
    now = (now or now_utc()).astimezone(ZoneInfo(tz))
    start = now.replace(minute=0, second=0) - timedelta(hours=now.hour)
    hours = [start + timedelta(hours=i) for i in range(24 * 7)]
    days = [(start + timedelta(days=i)).date().isoformat() for i in range(7)]
    return {
        "latitude": 12.97, "longitude": 77.59, "timezone": tz, "utc_offset_seconds": 19800,
        "current": {"time": now.strftime("%Y-%m-%dT%H:%M"), "interval": 900, "temperature_2m": temp,
                    "relative_humidity_2m": 55, "apparent_temperature": temp + 1, "precipitation": 0.0,
                    "weather_code": code, "cloud_cover": 20, "pressure_msl": 1011, "wind_speed_10m": 9.0,
                    "wind_direction_10m": 250, "wind_gusts_10m": 18.0},
        "hourly": {"time": [h.strftime("%Y-%m-%dT%H:%M") for h in hours],
                   "temperature_2m": [temp - 3 + (i % 24) / 4 for i in range(len(hours))],
                   "precipitation": [0.0] * len(hours), "precipitation_probability": [10] * len(hours),
                   "visibility": [24000.0] * len(hours)},
        "daily": {"time": days, "weather_code": [code] * 7, "temperature_2m_max": [tmax] * 7,
                  "temperature_2m_min": [tmax - 9] * 7, "precipitation_sum": [precip_day] * 7,
                  "precipitation_probability_max": [20] * 7, "wind_speed_10m_max": [wind_max] * 7,
                  "sunrise": [f"{d}T06:21" for d in days], "sunset": [f"{d}T17:58" for d in days]},
    }


def open_meteo_air(pm25=18.0, pm10=40.0, now=None) -> dict:
    now = now or now_utc()
    hrs = [now.replace(minute=0, second=0) - timedelta(hours=47 - i) for i in range(48)]
    return {"current": {"time": now.strftime("%Y-%m-%dT%H:%M"), "pm2_5": pm25, "pm10": pm10, "us_aqi": 64},
            "hourly": {"time": [h.strftime("%Y-%m-%dT%H:%M") for h in hrs], "pm2_5": [pm25] * 48}}


# --- OpenAQ v3 ------------------------------------------------------------

def openaq_locations(dist_deg=0.03, hours_old=1.0, now=None, lat=12.97, lon=77.59) -> dict:
    now = now or now_utc()
    return {"meta": {"found": 1}, "results": [{
        "id": 8118, "name": "BTM Layout, Bengaluru - CPCB",
        "coordinates": {"latitude": lat + dist_deg, "longitude": lon},
        "sensors": [{"id": 101, "name": "pm25 µg/m³", "parameter": {"id": 2, "name": "pm25", "units": "µg/m³"}},
                    {"id": 102, "name": "pm10 µg/m³", "parameter": {"id": 1, "name": "pm10", "units": "µg/m³"}}],
        "datetimeLast": {"utc": (now - timedelta(hours=hours_old)).strftime("%Y-%m-%dT%H:%M:%SZ")},
    }]}


def openaq_latest(pm25=42.0, pm10=80.0, hours_old=1.0, now=None) -> dict:
    now = now or now_utc()
    t = (now - timedelta(hours=hours_old)).strftime("%Y-%m-%dT%H:%M:%SZ")
    return {"results": [{"datetime": {"utc": t}, "value": pm25, "sensorsId": 101, "locationsId": 8118},
                        {"datetime": {"utc": t}, "value": pm10, "sensorsId": 102, "locationsId": 8118}]}


def openaq_hours(values: List[float], now=None) -> dict:
    now = now or now_utc()
    return {"results": [{"value": v, "period": {"datetimeFrom": {"utc": (now - timedelta(hours=len(values) - i)).strftime("%Y-%m-%dT%H:00:00Z")}}}
                        for i, v in enumerate(values)]}


# --- USGS / GDACS ---------------------------------------------------------

def usgs(events: List[dict], now=None) -> dict:
    """events: dicts with mag, lat, lon, hours_ago, [alert]"""
    now = now or now_utc()
    return {"type": "FeatureCollection", "metadata": {"count": len(events)}, "features": [
        {"type": "Feature", "id": f"us{i}",
         "properties": {"mag": e["mag"], "place": e.get("place", "Test region"),
                        "time": int((now - timedelta(hours=e.get("hours_ago", 5))).timestamp() * 1000),
                        "url": f"https://earthquake.usgs.gov/earthquakes/eventpage/us{i}",
                        "alert": e.get("alert"), "title": f"M {e['mag']} - {e.get('place', 'Test region')}"},
         "geometry": {"type": "Point", "coordinates": [e["lon"], e["lat"], 10.0]}} for i, e in enumerate(events)]}


def gdacs(events: List[dict], now=None) -> dict:
    """events: dicts with type, level, lat, lon, country, days_ago, name"""
    now = now or now_utc()
    return {"type": "FeatureCollection", "features": [
        {"type": "Feature", "geometry": {"type": "Point", "coordinates": [e["lon"], e["lat"]]},
         "properties": {"eventtype": e["type"], "eventid": 1000 + i, "name": e.get("name", "Test event"),
                        "alertlevel": e["level"], "country": e.get("country", "India"),
                        "fromdate": (now - timedelta(days=e.get("days_ago", 1) + 1)).strftime("%Y-%m-%dT%H:%M:%S"),
                        "todate": (now - timedelta(days=e.get("days_ago", 1))).strftime("%Y-%m-%dT%H:%M:%S"),
                        "url": {"report": f"https://www.gdacs.org/report.aspx?eventid={1000 + i}"}}}
        for i, e in enumerate(events)]}


def all_ok_routes(**over) -> Dict[str, Handler]:
    """Every non-news provider answering normally (calm conditions)."""
    r: Dict[str, Handler] = {
        "api.openweathermap.org/data/2.5/weather": FakeResp(json_data=owm_current()),
        "api.openweathermap.org/data/2.5/forecast": FakeResp(json_data=owm_forecast()),
        "api.openweathermap.org/data/3.0/onecall": FakeResp(json_data={"lat": 0, "lon": 0}),
        "air-quality-api.open-meteo.com": FakeResp(json_data=open_meteo_air()),
        "api.open-meteo.com/v1/forecast": FakeResp(json_data=open_meteo()),
        "api.openaq.org/v3/locations/8118/latest": FakeResp(json_data=openaq_latest(pm25=6.0, pm10=20.0)),
        "api.openaq.org/v3/locations": FakeResp(json_data=openaq_locations()),
        "api.openaq.org/v3/sensors": FakeResp(json_data=openaq_hours([6.0] * 24)),
        "earthquake.usgs.gov": FakeResp(json_data=usgs([])),
        "gdacs.org": FakeResp(status=404, json_data=None),
    }
    r.update(over)
    return r
