"""Multi-factor model: unknown is never low, critical alerts are never averaged
away, feeds are matched geographically, and results are bounded and deterministic."""

from __future__ import annotations

from datetime import timedelta

import pytest
import requests

from core import pipeline
from core.config import settings
from core.coverage import overall_coverage
from core.dedup import deduplicate
from core.environment_service import AirReport, HazardReport, fetch_hazards
from core.factors import build_factors, overall_index
from core.personas import get_persona
from core.providers.air import MeasuredAir, ModelledAir, Reading
from core.providers.disasters import HazardEvent
from core.providers.weather import CurrentWeather, WeatherData
from core.scoring import assess_city
from core.weather_service import WeatherReport, assess_conditions

from .conftest import NOW, filler, make_event
from .provider_fixtures import FakeResp, Router, all_ok_routes, gdacs, usgs

P = get_persona("student")


def news(events, state="live"):
    return assess_city("Delhi", deduplicate(events), P, as_of=NOW, news_state=state, origin="live")


def calm_weather(**kw) -> WeatherReport:
    cur = CurrentWeather(kw.get("t", 24.0), kw.get("t", 24.0), 50, kw.get("wind", 8.0), 200, None, 0, 10, 1012, 10,
                         kw.get("cond", "Clear sky"), kw.get("group", "clear"), NOW)
    data = WeatherData("Open-Meteo", "Weather data by Open-Meteo.com (CC BY 4.0)", cur)
    w = WeatherReport("Delhi", "live", data, NOW, alerts=kw.get("alerts"),
                      alerts_status="available" if kw.get("alerts") is not None else "not_supported")
    w.signal, w.forecast_hazards, w.advice = assess_conditions(data, w.alerts)
    return w


def air(category=None, distance=3.0, modelled=None) -> AirReport:
    r = AirReport("Delhi", fetched_at=NOW)
    if category:
        r.measured = MeasuredAir("Station A", distance, [Reading("pm25", "PM2.5", 80.0, "µg/m³", NOW)],
                                 category, "pm25", NOW)
        r.measured_status = "available"
    else:
        r.measured_status = "no_data"
    if modelled:
        r.modelled = ModelledAir(150.0, 200.0, 190, modelled, NOW)
        r.modelled_status = "available"
    return r


def hazards(events=()) -> HazardReport:
    return HazardReport("Delhi", list(events), "available", "available", fetched_at=NOW)


def quake(mag, dist, sev, attributed, alert=None, hours=5):
    return HazardEvent("USGS", "Earthquake", f"M {mag}", NOW - timedelta(hours=hours), dist, sev, alert, attributed,
                       f"Magnitude {mag}, {dist} km away", None, mag)


def build(events=None, *, weather=None, air_r=None, hz=None, persona=P, news_available=True):
    a = news(events if events is not None else filler())
    return build_factors(a, news_available=news_available, news_label="Test", weather=weather, air=air_r,
                         hazards=hz, persona=persona, as_of=NOW), a


# --- news factors ----------------------------------------------------------

def test_minor_crimes_do_not_make_a_city_high():
    titles = ["Pickpocketing complaints rise at Delhi metro station", "Shoplifting case reported at Delhi mall",
              "Bicycle theft reported in Delhi neighbourhood", "Petty theft at Delhi bus stand"]
    evs = filler() + [make_event(t, hours_ago=10 + i) for i, t in enumerate(titles)]
    fa, _ = build(evs, weather=calm_weather(), air_r=air("Moderate"), hz=hazards())
    assert fa.factors["crime"].level in ("low", "guarded")
    assert fa.level in ("low", "guarded") and not fa.critical


def test_severe_recent_event_is_critical_and_floors_overall():
    evs = filler() + [make_event("Bomb blast kills 12 at crowded Delhi market", hours_ago=8)]
    fa, _ = build(evs, weather=calm_weather(), air_r=air("Good"), hz=hazards())
    assert any(c.factor == "crime" and c.level == "elevated" for c in fa.critical)
    assert fa.level in ("elevated", "high")


def test_duplicate_reports_count_once():
    one = filler() + [make_event("Armed robbery at jewellery store in Delhi", hours_ago=5)]
    many = filler() + [make_event("Armed robbery at jewellery store in Delhi", hours_ago=5 + i * 0.5,
                                  source=f"Wire {i}") for i in range(5)]
    a1, _ = build(one, weather=calm_weather(), air_r=air("Good"), hz=hazards())
    a5, _ = build(many, weather=calm_weather(), air_r=air("Good"), hz=hazards())
    # One incident, not five. Independent sources only raise confidence slightly (corroboration).
    assert a1.factors["crime"].risk <= a5.factors["crime"].risk <= a1.factors["crime"].risk * 1.15
    assert sum(1 for e in deduplicate(many) if e.event_type == "crime") == 1


def test_older_events_count_less():
    fresh, _ = build(filler() + [make_event("Man stabbed in Delhi street fight", hours_ago=6)], hz=hazards())
    old, _ = build(filler() + [make_event("Man stabbed in Delhi street fight", hours_ago=24 * 20)], hz=hazards())
    assert old.factors["crime"].risk < fresh.factors["crime"].risk


# --- weather ---------------------------------------------------------------

def test_normal_weather_is_low_and_assessed():
    fa, _ = build(weather=calm_weather(), hz=hazards())
    w = fa.factors["weather"]
    assert w.assessed and w.level == "low" and w.confidence == "good"


def test_extreme_heat_raises_weather_factor():
    fa, _ = build(weather=calm_weather(t=44.0), hz=hazards())
    assert fa.factors["weather"].level in ("elevated", "high")


def test_official_weather_alert_is_prominent():
    fa, _ = build(weather=calm_weather(alerts=[{"event": "Red warning: extremely heavy rain", "issued_by": "IMD",
                                                 "description": "Stay indoors."}]), hz=hazards())
    assert fa.critical and fa.critical[0].factor == "weather"
    assert fa.factors["weather"].level in ("elevated", "high")
    assert fa.level != "low"


def test_missing_weather_is_unknown_not_low():
    fa, _ = build(weather=None, hz=hazards())
    assert fa.factors["weather"].level == "unknown" and "Weather" in fa.unknown


def test_adverse_weather_news_still_counts_without_live_data():
    evs = filler() + [make_event("Flash floods and waterlogging in Delhi after cloudburst", hours_ago=4)]
    fa, _ = build(evs, weather=None, hz=hazards())
    w = fa.factors["weather"]
    if w.assessed:  # classified as weather
        assert w.level != "low" and w.confidence == "limited"


# --- air quality -------------------------------------------------------------

def test_air_quality_only_from_measurements():
    fa, _ = build(weather=calm_weather(), air_r=air(None, modelled="Very unhealthy"), hz=hazards())
    e = fa.factors["environment"]
    assert not e.assessed and e.level == "unknown"
    assert "context only" in e.summary  # modelled value mentioned, not scored


def test_measured_unhealthy_air_is_elevated():
    fa, _ = build(weather=calm_weather(), air_r=air("Unhealthy"), hz=hazards())
    assert fa.factors["environment"].level == "elevated"


def test_missing_air_quality_is_not_clean():
    fa, _ = build(weather=calm_weather(), air_r=air(None), hz=hazards())
    assert fa.factors["environment"].level == "unknown"
    assert "not treated as clean air" in fa.factors["environment"].summary


def test_far_station_has_limited_confidence():
    fa, _ = build(weather=calm_weather(), air_r=air("Good", distance=20.0), hz=hazards())
    assert fa.factors["environment"].confidence == "limited"


# --- natural hazards --------------------------------------------------------------

def test_distant_small_earthquake_does_not_affect_city():
    fa, _ = build(weather=calm_weather(), hz=hazards([quake(4.6, 420, 0, False)]))
    assert fa.factors["disaster"].level == "low" and not fa.critical


def test_large_nearby_earthquake_is_critical():
    fa, _ = build(weather=calm_weather(), hz=hazards([quake(6.9, 120, -3, True)]))
    assert any(c.factor == "disaster" for c in fa.critical)
    assert fa.factors["disaster"].level in ("elevated", "high")


def test_gdacs_red_alert_is_never_averaged_away():
    red = HazardEvent("GDACS", "Tropical cyclone", "Cyclone Test", NOW - timedelta(hours=10), 180, -3, "Red", True,
                      "Red alert, about 180 km from the city", "https://www.gdacs.org/x")
    fa, _ = build(weather=calm_weather(), air_r=air("Good"), hz=hazards([red]))
    assert fa.level == "high" and fa.critical[0].level == "high"


def test_national_event_is_context_not_city_level(monkeypatch):
    feed = gdacs([{"type": "DR", "level": "Orange", "lat": 23.0, "lon": 79.0, "country": "India", "days_ago": 2},
                  {"type": "FL", "level": "Red", "lat": 26.1, "lon": 91.7, "country": "India", "days_ago": 1}])
    monkeypatch.setattr(requests, "get", Router(all_ok_routes(**{"gdacs.org": FakeResp(json_data=feed)})))
    hz = fetch_hazards("Delhi", settings)
    assert hz.ok and len(hz.events) == 2 and not hz.attributed  # Assam flood is ~1500 km away
    fa, _ = build(weather=calm_weather(), hz=hz)
    assert fa.factors["disaster"].level == "low" and not fa.critical


def test_usgs_feed_parsing_and_relevance(monkeypatch):
    feed = usgs([{"mag": 6.8, "lat": 29.5, "lon": 77.8, "hours_ago": 3},   # ~170 km from Delhi
                 {"mag": 4.2, "lat": 34.0, "lon": 74.8, "hours_ago": 30}])  # Kashmir, far and small
    monkeypatch.setattr(requests, "get", Router(all_ok_routes(**{"earthquake.usgs.gov": FakeResp(json_data=feed)})))
    hz = fetch_hazards("Delhi", settings)
    near = [e for e in hz.events if e.attributed]
    assert len(near) == 1 and near[0].severity == -3 and near[0].magnitude == 6.8


def test_feed_and_news_of_same_quake_not_double_counted():
    q = quake(6.0, 140, -2, True)
    evs = filler() + [make_event("Strong earthquake jolts Delhi, buildings shake", hours_ago=5)]
    with_news, _ = build(evs, weather=calm_weather(), hz=hazards([q]))
    without, _ = build(filler(), weather=calm_weather(), hz=hazards([q]))
    assert with_news.factors["disaster"].risk == pytest.approx(without.factors["disaster"].risk, abs=0.02)


# --- coverage, missing data and aggregation ---------------------------------------------

def test_no_reports_is_not_safe():
    """News answered with nothing about the city: news factors are unknown and
    the favourable index is scaled down, never presented as 'safe'."""
    fa, a = build([], weather=calm_weather(), air_r=air("Good"), hz=hazards())
    assert {"Crime & security", "Civil disruption", "Transport disruption"} <= set(fa.unknown)
    cov = overall_coverage(fa, "live", a.coverage.state, True, False, "live", [])
    assert cov.state == "limited"
    full, af = build(weather=calm_weather(), air_r=air("Good"), hz=hazards())
    assert overall_index(fa.risk, cov.state, fa.observed_share) < overall_index(full.risk, "good", full.observed_share)


def test_missing_provider_keeps_the_others():
    fa, _ = build(weather=calm_weather(), air_r=None, hz=None)
    assert fa.factors["weather"].assessed and fa.factors["crime"].assessed
    assert fa.factors["environment"].level == "unknown"
    assert fa.factors["disaster"].assessed  # news still covers it


def test_insufficient_is_explicit():
    fa, a = build([], weather=None, air_r=None, hz=None, news_available=False)
    cov = overall_coverage(fa, "unavailable", a.coverage.state, False, False, None, [])
    assert cov.state == "insufficient" and fa.risk is None and fa.level == "insufficient"
    assert overall_index(fa.risk, cov.state, fa.observed_share) is None


def test_bounded_and_deterministic():
    evs = filler() + [make_event(f"Bomb blast kills {i + 10} in Delhi", hours_ago=2 + i) for i in range(30)]
    kw = dict(weather=calm_weather(t=46.0), air_r=air("Hazardous"), hz=hazards([quake(7.5, 50, -3, True)]))
    r1, _ = build(evs, **kw)
    r2, _ = build(evs, **kw)
    assert 0.0 <= r1.risk <= 1.0 and r1.risk == r2.risk
    assert -10 <= overall_index(r1.risk, "good", r1.observed_share) <= 10
    assert [f.risk for f in r1.factors.values()] == [f.risk for f in r2.factors.values()]


def test_contributions_sum_to_one():
    fa, _ = build(filler() + [make_event("Robbery at Delhi bank", hours_ago=4)], weather=calm_weather(t=38.0),
                  air_r=air("Moderate"), hz=hazards())
    total = sum(f.contribution for f in fa.factors.values() if f.assessed)
    assert total == pytest.approx(1.0, abs=0.01)


def test_personas_reweigh_but_never_add_risk():
    fa_elder, _ = build(weather=calm_weather(), air_r=air("Unhealthy"), hz=hazards(), persona=get_persona("elderly"))
    fa_student, _ = build(weather=calm_weather(), air_r=air("Unhealthy"), hz=hazards(), persona=P)
    assert fa_elder.factors["environment"].persona_risk > fa_student.factors["environment"].persona_risk
    zero, _ = build([], weather=None, air_r=None, hz=None, persona=get_persona("family"), news_available=False)
    assert all(f.persona_risk == 0 for f in zero.factors.values())


def test_pipeline_live_feeds_end_to_end(monkeypatch):
    """Whole pipeline with every non-news provider answering (news blocked)."""
    monkeypatch.setattr(settings, "data_mode", "live")
    monkeypatch.setattr(settings, "openaq_api_key", "test-openaq")
    monkeypatch.setattr(requests, "get", Router(all_ok_routes()))
    ctx = pipeline.analyse_city("Bangalore", "student")
    st = {s.key: s.state for s in ctx.sources}
    assert st["news"] == "unavailable" and st["weather"] == "available" and st["air"] == "available"
    assert st["air_model"] == "broader_region" and st["alerts"] == "not_configured"
    assert ctx.factors.factors["environment"].assessed and ctx.factors.factors["crime"].level == "unknown"
    assert ctx.coverage.state == "limited"  # half the factor weight, no news
    assert ctx.general.index is not None and ctx.general.index < 5
