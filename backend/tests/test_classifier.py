"""Classifier behaviour: categories, severity, negation, history, context."""

from __future__ import annotations

import pytest

from core.classifier import classify_text
from core.location import assess_location


@pytest.mark.parametrize("title,category,severity", [
    ("Robbery at jewelry store in T Nagar, police launch manhunt", "crime", -2),
    ("Cyclone alert issued for Tamil Nadu coast", "disaster", -2),
    ("Bomb blast kills 12 in crowded market", "crime", -3),
    ("Phone stolen from tourist near the station", "crime", -1),
    ("Auto rickshaw strike affects commuters", "protest", -1),
    ("Curfew imposed after violent clashes", "protest", -2),
    ("Three killed as bus overturns on highway", "accident", -3),
    ("Heatwave grips the city, red alert issued", "weather", -2),
    ("Cultural festival inaugurated at the city park", "positive", 1),
    ("City council approves annual budget", "neutral", 0),
])
def test_basic_categories(title, category, severity):
    c = classify_text(title, None, 2026)
    assert c.event_type == category
    assert c.severity == severity


def test_word_boundaries_prevent_substring_matches():
    # Old classifier matched "rain" inside "train" and "drug" inside "drugstore".
    assert classify_text("Train timetable updated for the new season", None, 2026).event_type == "neutral"
    assert classify_text("New drugstore chain opens downtown", None, 2026).event_type == "neutral"
    assert classify_text("Stock market crash wipes out gains", None, 2026).event_type == "neutral"


def test_negation_is_ignored():
    c = classify_text("Police deny rumours of kidnapping near the beach", None, 2026)
    assert c.event_type == "neutral"
    assert any("negated" in f for f in c.flags)


def test_no_injuries_caps_severity():
    c = classify_text("Fire breaks out in warehouse, no injuries reported", None, 2026)
    assert c.event_type == "accident"
    assert c.severity == -1


def test_injuries_escalate_but_minor_injuries_do_not():
    assert classify_text("Fire at chemical factory, 2 injured", None, 2026).severity == -2
    c = classify_text("Car hits divider; three occupants sustained minor injuries", None, 2026)
    assert c.severity == -1


def test_historical_reference_flagged():
    c = classify_text("Court sentences two for 2019 murder", None, 2026)
    assert c.event_type == "crime"
    assert c.is_historical
    assert classify_text("City remembers victims on bomb blast anniversary", None, 2026).is_historical


def test_awareness_context_not_an_incident():
    c = classify_text("Cybercrime awareness camp held for students", None, 2026)
    assert c.event_type == "neutral"
    assert classify_text("Fire safety mock drill conducted at mall", None, 2026).event_type == "neutral"


def test_resolved_crime_flagged():
    c = classify_text("Two-wheeler theft gang arrested in Whitefield", None, 2026)
    assert c.event_type == "crime" and c.is_resolved
    ongoing = classify_text("Robbery at bank, police launch manhunt", None, 2026)
    assert not ongoing.is_resolved


def test_minor_as_age_does_not_downgrade_crime():
    c = classify_text("Minor girl kidnapped from bus stand", None, 2026)
    assert c.severity == -2


def test_film_shooting_is_not_violence():
    assert classify_text("Shooting of new film begins in Goa", None, 2026).event_type == "neutral"


def test_mild_weather_is_not_adverse():
    c = classify_text("Pleasant weather continues with mild showers", None, 2026)
    assert c.event_type == "weather" and c.severity == 0


def test_severity_and_confidence_are_independent():
    strong = classify_text("Armed robbery at bank", None, 2026)
    weak = classify_text("Residents talk about the market", "Some mention a robbery last month", 2026)
    assert strong.severity == weak.severity == -2
    assert weak.confidence < strong.confidence


def test_ambiguous_headline_lowers_confidence():
    clear = classify_text("Heavy rain lashes the city", None, 2026)
    mixed = classify_text("Heavy rain disrupts protest march", None, 2026)
    assert mixed.confidence < clear.confidence


@pytest.mark.parametrize("city,title,low", [
    ("Delhi", "Delhi tourist robbed at knifepoint in Goa", True),
    ("Goa", "Fire in Pune factory kills two", True),
    ("Delhi", "Armed robbery at jewellery store in South Delhi", False),
    ("Mumbai", "Power outage affects parts of Navi Mumbai", False),
])
def test_location_relevance(city, title, low):
    conf, _ = assess_location(city, title, None, "live")
    assert (conf < 0.4) is low


def test_regional_mention_is_partial():
    conf, note = assess_location("Chennai", "Cyclone alert issued for Tamil Nadu coast", None, "live")
    assert 0.4 <= conf < 0.9
    assert "Regional" in note
