"""Weather integration: every failure path from the spec, the Open-Meteo
fallback, stale cache and the 'never Low when weather is missing' rule."""

from __future__ import annotations

import requests

from core import pipeline
from core.config import settings
from core.weather_service import fetch_weather

from .provider_fixtures import FakeResp, Router, all_ok_routes, open_meteo, owm_current, owm_forecast, owm_onecall_alerts

KEY = "0123456789abcdef0123456789abcdef"


def _use(monkeypatch, routes):
    r = Router(routes)
    monkeypatch.setattr(requests, "get", r)
    return r


def test_openweathermap_success_with_alerts(monkeypatch):
    monkeypatch.setattr(settings, "openweather_api_key", KEY)
    _use(monkeypatch, all_ok_routes(**{
        "api.openweathermap.org/data/3.0/onecall": FakeResp(json_data=owm_onecall_alerts(["Heavy rain warning"]))}))
    w = fetch_weather("Bangalore", settings)
    assert w.ok and w.provider == "OpenWeatherMap"
    c = w.data.current
    assert c.temperature_c == 24.0 and c.wind_kmh == 10.8 and c.visibility_km == 10.0
    assert len(w.data.hourly) == 16 and w.data.hourly_step_hours == 3 and len(w.data.daily) >= 5
    assert w.alerts_status == "available" and w.alerts[0]["event"] == "Heavy rain warning"
    assert w.alerts[0]["issued_by"] == "India Meteorological Department"


def test_missing_key_uses_open_meteo_without_calling_owm(monkeypatch):
    r = _use(monkeypatch, all_ok_routes())
    w = fetch_weather("Bangalore", settings)
    assert w.ok and w.provider == "Open-Meteo"
    assert r.count("openweathermap") == 0
    assert w.attempts[0].kind == "not_configured"
    assert w.alerts is None and w.alerts_status == "not_supported"  # never "none"
    assert len(w.data.daily) == 7 and w.data.hourly and w.data.current.visibility_km == 24.0


def test_401_rejected_key_falls_back_and_explains(monkeypatch):
    monkeypatch.setattr(settings, "openweather_api_key", KEY)
    _use(monkeypatch, all_ok_routes(**{"api.openweathermap.org/data/2.5/weather": FakeResp(
        401, {"cod": 401, "message": "Invalid API key. Please see https://openweathermap.org/faq#error401"})}))
    w = fetch_weather("Bangalore", settings)
    assert w.ok and w.provider == "Open-Meteo"
    ow = w.attempts[0]
    assert ow.provider == "OpenWeatherMap" and ow.kind == "unauthorized" and ow.status == 401
    assert KEY not in repr(w.attempts)


def test_401_without_fallback_reports_activation_hint(monkeypatch):
    monkeypatch.setattr(settings, "openweather_api_key", KEY)
    monkeypatch.setattr(settings, "open_meteo_enabled", False)
    _use(monkeypatch, {"openweathermap.org/data/2.5/weather": FakeResp(401, {"cod": 401, "message": "Invalid API key"})})
    w = fetch_weather("Bangalore", settings)
    assert not w.ok and w.reason_kind == "unauthorized"
    assert "activate" in w.public_reason and KEY not in w.public_reason


def test_429_is_retried_then_falls_back(monkeypatch):
    monkeypatch.setattr(settings, "openweather_api_key", KEY)
    monkeypatch.setattr(settings, "http_retries", 2)
    r = _use(monkeypatch, all_ok_routes(**{"api.openweathermap.org/data/2.5/weather": FakeResp(429, {"cod": 429})}))
    w = fetch_weather("Bangalore", settings)
    assert r.count("data/2.5/weather") == 3  # 1 try + 2 retries
    assert w.ok and w.provider == "Open-Meteo" and w.attempts[0].kind == "rate_limited"


def test_timeout_and_5xx_retry_and_recover(monkeypatch):
    monkeypatch.setattr(settings, "openweather_api_key", KEY)
    monkeypatch.setattr(settings, "http_retries", 2)
    r = _use(monkeypatch, all_ok_routes(**{"api.openweathermap.org/data/2.5/weather": [
        requests.exceptions.ReadTimeout("slow"), FakeResp(503, {}), FakeResp(json_data=owm_current())]}))
    w = fetch_weather("Bangalore", settings)
    assert w.ok and w.provider == "OpenWeatherMap" and r.count("data/2.5/weather") == 3


def test_401_is_not_retried(monkeypatch):
    monkeypatch.setattr(settings, "openweather_api_key", KEY)
    monkeypatch.setattr(settings, "http_retries", 3)
    r = _use(monkeypatch, all_ok_routes(**{"api.openweathermap.org/data/2.5/weather": FakeResp(401, {})}))
    fetch_weather("Bangalore", settings)
    assert r.count("data/2.5/weather") == 1


def test_malformed_json_is_bad_response(monkeypatch):
    monkeypatch.setattr(settings, "open_meteo_enabled", True)
    _use(monkeypatch, {"api.open-meteo.com": FakeResp(200, text="<html>proxy error</html>")})
    w = fetch_weather("Bangalore", settings)
    assert not w.ok and w.attempts[-1].kind == "bad_response"
    assert "interpreted" in w.public_reason


def test_missing_fields_are_rejected_not_defaulted(monkeypatch):
    monkeypatch.setattr(settings, "openweather_api_key", KEY)
    monkeypatch.setattr(settings, "open_meteo_enabled", False)
    _use(monkeypatch, {"data/2.5/weather": FakeResp(json_data={"weather": [{"id": 800}], "dt": 1})})
    w = fetch_weather("Bangalore", settings)
    assert not w.ok and w.attempts[0].kind == "bad_response"


def test_open_meteo_error_body(monkeypatch):
    _use(monkeypatch, {"api.open-meteo.com": FakeResp(400, {"error": True, "reason": "Cannot initialize WeatherVariable"})})
    w = fetch_weather("Bangalore", settings)
    assert not w.ok and w.attempts[-1].kind == "bad_response" and w.attempts[-1].status == 400


def test_unknown_coordinates(monkeypatch):
    w = fetch_weather("Atlantis", settings)
    assert not w.ok and w.reason_kind == "not_found" and not w.attempts


def test_all_providers_unavailable(monkeypatch):
    monkeypatch.setattr(settings, "openweather_api_key", KEY)
    _use(monkeypatch, {})
    w = fetch_weather("Bangalore", settings)
    assert not w.ok and {a.kind for a in w.attempts} == {"network"}
    assert "couldn't be reached" in w.public_reason


def test_alerts_none_vs_unavailable(monkeypatch):
    monkeypatch.setattr(settings, "openweather_api_key", KEY)
    _use(monkeypatch, all_ok_routes())  # onecall answers with no alerts
    w = fetch_weather("Bangalore", settings)
    assert w.alerts == [] and w.alerts_status == "available"
    _use(monkeypatch, all_ok_routes(**{"api.openweathermap.org/data/3.0/onecall": FakeResp(401, {"cod": 401})}))
    w = fetch_weather("Bangalore", settings)
    assert w.alerts is None and w.alerts_status == "not_subscribed"
    _use(monkeypatch, all_ok_routes(**{"api.openweathermap.org/data/3.0/onecall": FakeResp(500, {})}))
    w = fetch_weather("Bangalore", settings)
    assert w.alerts is None and w.alerts_status == "unavailable"


def test_extreme_heat_and_heavy_rain_raise_weather_signal(monkeypatch):
    _use(monkeypatch, all_ok_routes(**{"api.open-meteo.com/v1/forecast": FakeResp(
        json_data=open_meteo(temp=43.0, tmax=46.0, precip_day=120.0))}))
    w = fetch_weather("Delhi", settings)
    assert w.ok
    assert any("Extreme heat" in f for f in w.signal.factors)
    assert any("very heavy rain" in h for h in w.forecast_hazards)
    assert w.signal.risk > 0.6


def test_normal_weather_is_low(monkeypatch):
    _use(monkeypatch, all_ok_routes())
    w = fetch_weather("Bangalore", settings)
    assert w.ok and w.signal.risk < 0.15 and not w.signal.factors


def test_stale_weather_served_and_labelled(monkeypatch):
    monkeypatch.setattr(settings, "data_mode", "live")
    _use(monkeypatch, all_ok_routes())
    monkeypatch.setattr(settings, "cache_ttl_seconds", 0)
    w1, _, _, stale1 = pipeline.get_weather("Bangalore", settings)
    assert w1.ok and not stale1
    _use(monkeypatch, {})
    w2, _, _, stale2 = pipeline.get_weather("Bangalore", settings)
    assert w2.ok and stale2
    ctx = pipeline.analyse_city("Bangalore", "student")
    assert next(s for s in ctx.sources if s.key == "weather").state == "stale"
    assert ctx.coverage.state != "good"


def test_weather_never_low_when_unavailable(monkeypatch):
    """Screenshot bug: 'Weather in the news: Low' while live weather was missing."""
    monkeypatch.setattr(settings, "data_mode", "live")
    _use(monkeypatch, {})
    ctx = pipeline.analyse_city("Bangalore", "student")
    f = ctx.factors.factors["weather"]
    assert not ctx.weather.ok
    assert f.level == "unknown" and not f.assessed
    assert "not treated as good weather" in f.summary


def test_weather_endpoint_unavailable_state(monkeypatch):
    from fastapi.testclient import TestClient
    from app.main import app
    monkeypatch.setattr(settings, "data_mode", "live")
    _use(monkeypatch, {})
    d = TestClient(app).get("/api/cities/bangalore/weather").json()
    assert d["status"] == "unavailable" and d["current"] is None and d["hourly"] == []
    assert d["factor"]["level"] == "unknown" and d["conditions"]["level"] == "unknown"
    assert d["reason"] and d["alerts"] is None


def test_weather_endpoint_full(monkeypatch):
    from fastapi.testclient import TestClient
    from app.main import app
    monkeypatch.setattr(settings, "openweather_api_key", KEY)
    _use(monkeypatch, all_ok_routes(**{"api.openweathermap.org/data/2.5/forecast": FakeResp(
        json_data=owm_forecast(rain3h=12.0))}))
    d = TestClient(app).get("/api/cities/bangalore/weather").json()
    assert d["status"] == "available" and d["provider"] == "OpenWeatherMap"
    assert d["current"]["condition"] == "Clear sky" and d["hourly_step_hours"] == 3
    assert len(d["hourly"]) == 16 and d["daily"][0]["precip_mm"] > 60
    assert d["alerts"] == [] and d["alerts_message"].startswith("No official")
    assert "OpenWeather" in d["attribution"]
    body = str(d)
    assert KEY not in body and "appid" not in body
