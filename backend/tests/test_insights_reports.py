"""City Insights data flow, presentation-safety and report regression tests (mocked HTTP)."""

from __future__ import annotations

import json
import re

import pytest
import requests
from fastapi.testclient import TestClient

from app.main import app
from app.schemas import InsightsResponse
from core.city_profiles import excerpt, parse_wikidata_facts, split_sections
from core.pipeline import get_profile


class FakeResp:
    def __init__(self, data=None, status=200):
        self._data, self.status_code = data, status

    def json(self):
        return self._data

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.exceptions.HTTPError(f"{self.status_code}", response=self)


SUMMARY = {
    "type": "standard", "title": "Pune", "description": "City in Maharashtra, India",
    "extract": "Pune is a city in the Indian state of Maharashtra.",
    "thumbnail": {"source": "https://upload.wikimedia.org/pune.jpg"},
    "content_urls": {"desktop": {"page": "https://en.wikipedia.org/wiki/Pune"}},
    "wikibase_item": "Q1538",
}
EXTRACT = (
    "Pune is a city in the Indian state of Maharashtra. It is known for its educational institutions and is "
    "often called the Oxford of the East.\n\nThe city has a long history as a cultural centre of the Marathi people.\n\n"
    "== History ==\nAncient history paragraph that is long enough to count as a paragraph here.\n\n"
    "== Geography ==\n\n=== Climate ===\nPune has a hot semi-arid climate bordering on tropical wet and dry, "
    "with average temperatures between 20 and 28 degrees Celsius. The monsoon lasts from June to September.\n\n"
    "== Transport ==\nPune is served by a metro, city buses run by PMPML, and suburban rail services that "
    "connect it to nearby towns. Auto rickshaws are widely available.\n"
)
CLAIMS = {
    "P17": [{"rank": "normal", "mainsnak": {"snaktype": "value", "datavalue": {"value": {"id": "Q668"}}}}],
    "P131": [{"rank": "normal", "mainsnak": {"snaktype": "value", "datavalue": {"value": {"id": "Q1191"}}}}],
    "P1082": [
        {"rank": "normal", "mainsnak": {"snaktype": "value", "datavalue": {"value": {"amount": "+2538473"}}},
         "qualifiers": {"P585": [{"datavalue": {"value": {"time": "+2001-00-00T00:00:00Z"}}}]}},
        {"rank": "normal", "mainsnak": {"snaktype": "value", "datavalue": {"value": {"amount": "+3124458"}}},
         "qualifiers": {"P585": [{"datavalue": {"value": {"time": "+2011-00-00T00:00:00Z"}}}]}},
    ],
    "P2046": [{"rank": "normal", "mainsnak": {"snaktype": "value", "datavalue": {
        "value": {"amount": "+331.26", "unit": "http://www.wikidata.org/entity/Q712226"}}}}],
    "P2044": [{"rank": "normal", "mainsnak": {"snaktype": "value", "datavalue": {
        "value": {"amount": "+560", "unit": "http://www.wikidata.org/entity/Q11573"}}}}],
    "P856": [{"rank": "normal", "mainsnak": {"snaktype": "value", "datavalue": {"value": "https://www.pmc.gov.in"}}}],
}
LABELS = {"entities": {"Q668": {"labels": {"en": {"value": "India"}}},
                       "Q1191": {"labels": {"en": {"value": "Maharashtra"}}}}}


def fake_wiki(url, params=None, **kwargs):
    if "rest_v1/page/summary" in url:
        return FakeResp(SUMMARY)
    if "wikipedia.org/w/api.php" in url:
        return FakeResp({"query": {"pages": [{"title": "Pune", "extract": EXTRACT}]}})
    if "wikidata.org" in url:
        if params and params.get("props") == "claims":
            return FakeResp({"entities": {"Q1538": {"claims": CLAIMS}}})
        return FakeResp(LABELS)
    raise requests.exceptions.ConnectionError("unexpected")


@pytest.fixture
def client():
    return TestClient(app)


def test_split_sections_and_excerpt():
    intro, sections = split_sections(EXTRACT)
    assert intro.startswith("Pune is a city")
    assert "climate" in sections and "transport" in sections
    long = "This is a sentence. " * 60
    ex = excerpt(long, 100)
    assert ex is not None and len(ex) <= 100 and ex.endswith(".")


def test_wikidata_facts_pick_latest_population():
    labels = {e: v["labels"]["en"]["value"] for e, v in LABELS["entities"].items()}
    facts = {f.label: f for f in parse_wikidata_facts(CLAIMS, labels)}
    assert facts["Population"].value == "3,124,458" and facts["Population"].note == "2011 figure"
    assert facts["Country"].value == "India" and facts["Administrative region"].value == "Maharashtra"
    assert facts["Area"].value == "331 km²" and facts["Elevation"].value == "560 m"
    assert facts["Official website"].value.startswith("https://")


def test_wikidata_ignores_wrong_units_and_missing_values():
    claims = {"P2046": [{"rank": "normal", "mainsnak": {"snaktype": "value", "datavalue": {
        "value": {"amount": "+5", "unit": "http://www.wikidata.org/entity/Q35852"}}}}],
              "P1082": [{"rank": "normal", "mainsnak": {"snaktype": "novalue"}}]}
    assert parse_wikidata_facts(claims, {}) == []


def test_insights_live_flow(client, monkeypatch):
    monkeypatch.setattr(requests, "get", fake_wiki)
    i = InsightsResponse.model_validate(client.get("/api/cities/Pune/insights", params={"persona": "family"}).json())
    assert i.status == "available" and i.message == ""
    assert i.title == "Pune" and i.description and i.summary
    assert len(i.about) == 2
    assert i.climate and "semi-arid" in i.climate
    assert i.transport and "metro" in i.transport
    labels = {f.label for f in i.facts}
    assert {"Country", "Population", "Area", "Local time"} <= labels
    assert i.facts_source == "Wikidata" and i.source.provider == "Wikipedia, Wikidata"
    assert i.image_url and i.article_url


def test_insights_partial_failure_keeps_summary(client, monkeypatch):
    def flaky(url, params=None, **kw):
        if "wikidata" in url or "w/api.php" in url:
            raise requests.exceptions.Timeout()
        return fake_wiki(url, params)
    monkeypatch.setattr(requests, "get", flaky)
    i = InsightsResponse.model_validate(client.get("/api/cities/Pune/insights").json())
    assert i.status == "available" and i.summary
    assert i.climate is None and i.transport is None and i.about == []
    assert i.facts_source == "TravelSafe reference data"


def test_insights_disambiguation_is_not_a_profile(client, monkeypatch):
    monkeypatch.setattr(requests, "get", lambda *a, **k: FakeResp({"type": "disambiguation", "extract": "X may refer to"}))
    i = InsightsResponse.model_validate(client.get("/api/cities/Goa/insights").json())
    assert i.status == "unavailable" and i.summary is None


def test_insights_refresh_and_retry(client, monkeypatch):
    def down(*a, **k):
        raise requests.exceptions.ConnectionError()
    monkeypatch.setattr(requests, "get", down)
    assert client.get("/api/cities/Pune/insights").json()["status"] == "unavailable"
    monkeypatch.setattr(requests, "get", fake_wiki)
    # failure is cached briefly; refresh clears it so "Try again" works immediately
    assert client.post("/api/cities/Pune/refresh").status_code == 200
    assert client.get("/api/cities/Pune/insights").json()["status"] == "available"


def test_insights_stale_profile_served_when_refresh_fails(client, monkeypatch):
    monkeypatch.setattr(requests, "get", fake_wiki)
    get_profile("Pune")
    client.post("/api/cities/Pune/refresh")

    def down(*a, **k):
        raise requests.exceptions.ConnectionError()
    monkeypatch.setattr(requests, "get", down)
    i = client.get("/api/cities/Pune/insights").json()
    assert i["status"] == "available" and i["source"]["state"] == "stale"
    assert "last successful" in i["message"]


INTERNAL_KEYS = {"impact", "recency_weight", "matched_terms", "flags", "confidence", "location_confidence",
                 "exclusion_reason", "risk", "news_risk", "live_risk", "weights", "metrics", "detail",
                 "age_seconds", "persona_weight", "share", "condition_code", "condition_group", "slots"}


def _keys(obj, out=None):
    out = set() if out is None else out
    if isinstance(obj, dict):
        for k, v in obj.items():
            out.add(k)
            _keys(v, out)
    elif isinstance(obj, list):
        for v in obj:
            _keys(v, out)
    return out


@pytest.mark.parametrize("path", ["/api/cities/Delhi/overview", "/api/cities/Delhi/events?status=all",
                                  "/api/cities/Delhi/weather", "/api/cities/Chennai/crime",
                                  "/api/cities/Delhi/insights", "/api/cities"])
def test_ui_endpoints_expose_no_internal_fields(client, path):
    data = client.get(path).json()
    leaked = _keys(data) & INTERNAL_KEYS
    assert not leaked, f"internal fields exposed: {leaked}"
    text = json.dumps(data)
    for bad in ("Traceback", "Exception", "api_key", "apiKey", "OPENWEATHER", "None", "NaN", "undefined"):
        assert bad not in text


def test_pdf_report_structure(client):
    r = client.get("/api/cities/Delhi/report", params={"persona": "solo_female"})
    assert r.status_code == 200 and r.content[:4] == b"%PDF"
    pages = len(re.findall(rb"/Type /Page[^s]", r.content))
    assert 2 <= pages <= 4


def test_pdf_report_insufficient_city_is_short(client):
    r = client.get("/api/cities/Tokyo/report")
    pages = len(re.findall(rb"/Type /Page[^s]", r.content))
    assert pages <= 3  # no events page and no padding when there is nothing to report


def test_html_report_matches_dashboard(client):
    ov = client.get("/api/cities/Delhi/overview", params={"persona": "family"}).json()
    page = client.get("/api/cities/Delhi/report", params={"persona": "family", "format": "html"}).text
    assert ov["general"]["label"] in page and ov["personalized"]["label"] in page
    assert "Sample data" in page
    for internal in ("impact", "recency", "weight ×", "0.3", "confidence_label"):
        assert internal not in page
