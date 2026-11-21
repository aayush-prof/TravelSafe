"""Scoring engine scenarios (fixed clock, deterministic fixtures)."""

from __future__ import annotations

import math

import pytest

from core.dedup import deduplicate
from core.personas import get_all_personas, get_persona
from core.scoring import (LiveWeatherSignal, apply_persona, assess_city, category_pressure, combine_overall,
                          pressure_to_risk, risk_to_index)
from core.scoring_params import level_for

from .conftest import NOW, filler, make_event


def run(events, persona="student", *, origin="live", news_state="live", weather=None, city="Delhi"):
    return assess_city(city, deduplicate(events), get_persona(persona), as_of=NOW, news_state=news_state,
                       origin=origin, live_weather=weather)


# 1 ---------------------------------------------------------------------------
def test_no_events_is_insufficient_not_safe():
    a = run([])
    assert a.coverage.state == "insufficient"
    assert a.general.index is None and a.general.level == "insufficient"
    assert a.personalized.index is None
    assert "not an indication" in a.general.summary


def test_unavailable_news_is_insufficient():
    a = run(filler(), news_state="unavailable")
    assert a.coverage.state == "insufficient"


def test_stale_reports_only_is_insufficient():
    old = [make_event(f"Delhi council meeting {i}", hours_ago=24 * 40 + i) for i in range(10)]
    assert run(old).coverage.state == "insufficient"


# 2 ---------------------------------------------------------------------------
def test_one_or_two_minor_reports_do_not_make_city_unsafe():
    one = run(filler() + [make_event("Phone stolen from tourist in Delhi market")])
    two = run(filler() + [make_event("Phone stolen in Delhi market"),
                          make_event("Pickpocket targets commuters on Delhi metro", hours_ago=30)])
    assert one.categories["crime"].level == "low"
    assert two.categories["crime"].level in ("low", "guarded")
    assert one.general.level in ("low", "guarded") and two.general.level in ("low", "guarded")
    assert one.general.index > 0 and two.general.index > 0


def test_many_minor_reports_capped_below_elevated():
    many = [make_event(f"Bike theft number {i} reported in Delhi sector {i}", hours_ago=5 + i) for i in range(40)]
    a = run(filler() + many)
    assert a.categories["crime"].level in ("low", "guarded")


# 3 ---------------------------------------------------------------------------
def test_one_recent_severe_event_is_meaningful():
    base = run(filler())
    a = run(filler() + [make_event("Bomb blast in Delhi market kills 12", hours_ago=3)])
    assert a.categories["crime"].level in ("elevated", "high")
    assert a.general.level in ("elevated", "high")
    assert a.general.index < base.general.index - 8


# 4 ---------------------------------------------------------------------------
def test_duplicates_do_not_multiply_impact():
    single = run(filler() + [make_event("Armed robbery at Delhi jewellery store", source="A")])
    dupes = run(filler() + [make_event("Armed robbery at Delhi jewellery store", source=f"Source {i}",
                                       hours_ago=6 + i) for i in range(8)])
    ev = [e for e in dupes.events if e.event_type == "crime"]
    assert len(ev) == 1 and ev[0].duplicate_count == 8 and len(ev[0].sources) == 8
    assert dupes.categories["crime"].risk == pytest.approx(single.categories["crime"].risk, abs=0.03)


def test_dedup_by_canonical_url():
    a = make_event("Robbery at store", url="https://www.example.com/news/robbery?utm_source=x")
    b = make_event("Store robbed, police say", url="http://example.com/news/robbery/")
    assert len(deduplicate([a, b])) == 1


def test_similar_wording_with_different_numbers_not_merged():
    a = make_event("Bus accident in Delhi leaves 3 injured")
    b = make_event("Bus accident in Delhi leaves 5 injured", hours_ago=30)
    assert len(deduplicate([a, b])) == 2


# 5 ---------------------------------------------------------------------------
def test_old_event_has_less_influence():
    recent = run(filler() + [make_event("Armed robbery at Delhi bank", hours_ago=12)])
    old = run(filler() + [make_event("Armed robbery at Delhi bank", hours_ago=24 * 45)])
    assert old.categories["crime"].risk < recent.categories["crime"].risk / 2
    very_old = run(filler() + [make_event("Armed robbery at Delhi bank", hours_ago=24 * 120)])
    excluded = [e for e in very_old.events if e.event_type == "crime"][0]
    assert not excluded.counted and "older than" in excluded.exclusion_reason


def test_missing_and_future_timestamps_handled():
    a = run(filler() + [make_event("Armed robbery at Delhi bank", hours_ago=None),
                        make_event("Delhi house burglary reported", hours_ago=-48)])
    evs = {e.news_item.title: e for e in a.events}
    assert evs["Armed robbery at Delhi bank"].recency_weight == 0.5
    assert evs["Armed robbery at Delhi bank"].date_basis == "unknown"
    assert any("future" in f for f in evs["Delhi house burglary reported"].flags)


# 6 ---------------------------------------------------------------------------
def test_low_confidence_has_reduced_influence():
    strong = make_event("Armed robbery at Delhi bank")
    weak = strong.model_copy(deep=True)
    weak.confidence = 0.3
    a, b = run(filler() + [strong]), run(filler() + [weak])
    assert b.categories["crime"].risk < a.categories["crime"].risk


# 7 ---------------------------------------------------------------------------
def test_event_elsewhere_not_attributed():
    a = run(filler() + [make_event("Delhi tourist robbed at knifepoint in Goa")])
    ev = [e for e in a.events if e.event_type == "crime"][0]
    assert not ev.counted and ev.exclusion_reason.startswith("location")
    assert a.categories["crime"].risk == 0


# 8 ---------------------------------------------------------------------------
def test_neutral_and_positive_do_not_cancel_adverse():
    bad = [make_event("Armed robbery at Delhi jewellery store")]
    positives = [make_event(f"Grand festival {i} celebrated in Delhi", hours_ago=2 + i) for i in range(25)]
    a, b = run(filler() + bad), run(filler() + bad + positives)
    assert b.categories["crime"].risk == pytest.approx(a.categories["crime"].risk)
    assert b.general.risk == pytest.approx(a.general.risk)


# 9 ---------------------------------------------------------------------------
def test_missing_weather_is_reported_not_safe():
    a = run(filler(), weather=LiveWeatherSignal(False, reason="no key"))
    assert a.coverage.metrics["weather_feed"] == "unavailable"
    assert any("weather" in r.lower() and "unavailable" in r.lower() for r in a.coverage.reasons)
    assert "not available" in a.categories["weather"].basis


def test_live_weather_raises_weather_category():
    a = run(filler(), weather=LiveWeatherSignal(True, 0.5, ["Extreme heat (42 °C)"]))
    assert a.categories["weather"].level == "guarded"
    assert a.categories["weather"].live_risk == 0.5


# 10 --------------------------------------------------------------------------
def test_sample_data_capped_and_flagged():
    evs = [make_event(f"Delhi metro adds trains on line {i}", origin="sample") for i in range(20)]
    a = run(evs, origin="sample", news_state="sample")
    assert a.coverage.state == "limited"
    assert any("Sample" in r for r in a.coverage.reasons)
    # positive side is halved under limited coverage
    assert a.general.index == pytest.approx(5.0)


# 11 --------------------------------------------------------------------------
@pytest.mark.parametrize("name", list(get_all_personas()))
def test_each_persona_is_consistent_and_explained(name):
    events = filler() + [make_event("Armed robbery at Delhi jewellery store"),
                         make_event("Heatwave grips Delhi, orange alert issued", hours_ago=10)]
    base = run(events, "student")
    a = run(events, name)
    p = get_persona(name)
    for adj in a.persona_adjustments:
        expected = apply_persona(adj.base_risk, p.get_weight(adj.category))
        assert adj.persona_risk == pytest.approx(expected, abs=1e-3)
        if adj.weight > 1:
            assert adj.persona_risk >= adj.base_risk
        if adj.weight < 1:
            assert adj.persona_risk <= adj.base_risk
    # persona never changes the general assessment
    assert a.general.risk == base.general.risk
    assert a.persona_explanation


def test_persona_never_creates_risk_from_nothing():
    a = run(filler(), "family")
    assert a.personalized.risk == 0 and a.general.risk == 0


def test_persona_shift_is_at_most_about_one_level():
    for p in get_all_personas().values():
        for w in p.weights.values():
            assert apply_persona(0.35, w) < 0.6  # guarded/elevated boundary never jumps to high


# 12 --------------------------------------------------------------------------
def test_extreme_values_bounded():
    huge = [make_event(f"Bomb blast in Delhi market {i} kills 40", hours_ago=1 + i) for i in range(200)]
    a = run(filler() + huge, "family")
    assert 0 <= a.general.risk <= 1 and -10 <= a.general.index <= 10
    assert -10 <= a.personalized.index <= 10
    assert pressure_to_risk(float("inf")) == 0.0 or pressure_to_risk(1e9) <= 1.0
    assert pressure_to_risk(float("nan")) == 0.0
    assert category_pressure([-5, 0, float("nan") if False else 0]) == 0.0
    assert risk_to_index(2.0, "good") == -10.0 and risk_to_index(-1, "good") == 10.0


def test_overall_not_inflated_by_many_mild_categories():
    mild = {c: 0.2 for c in ["crime", "protest", "accident", "disaster", "weather"]}
    assert combine_overall(mild) < 0.35  # stays "guarded"
    assert combine_overall({"crime": 0.7}) == pytest.approx(0.7)  # strongest never diluted


def test_borderline_risk_is_not_elevated():
    assert level_for(0.50) == "guarded"
    assert level_for(0.64) == "guarded"
    assert level_for(0.65) == "elevated"
    assert level_for(0.85) == "high"


def test_pressure_monotonic_and_log_volume():
    assert category_pressure([1.0]) == 1.0
    assert category_pressure([1.0, 1.0]) == pytest.approx(1 + 1.5 * math.log(2))
    assert category_pressure([1.0] * 1000) == pytest.approx(1 + 2.5)
