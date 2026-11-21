"""API contract tests (network disabled; sample-data path and error paths)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.schemas import (CitiesResponse, CrimeResponse, EventsResponse, HealthResponse, InsightsResponse,
                         MethodologyResponse, OverviewResponse, WeatherResponse)
from core.config import settings


@pytest.fixture
def client():
    return TestClient(app)


def test_health(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    HealthResponse.model_validate(r.json())


def test_cities_and_personas(client):
    data = CitiesResponse.model_validate(client.get("/api/cities").json())
    assert len(data.cities) == 45
    assert {p.id for p in data.personas} == {"student", "solo_female", "family", "backpacker", "elderly"}
    assert sum(c.has_sample_data for c in data.cities) == 5


def test_overview_sample_fallback_is_labelled(client):
    r = client.get("/api/cities/Delhi/overview", params={"persona": "family"})
    assert r.status_code == 200
    ov = OverviewResponse.model_validate(r.json())
    assert ov.data_mode == "sample"
    news = next(s for s in ov.sources if s.kind == "news")
    assert news.state == "sample" and "sample headlines" in news.message
    assert ov.coverage.state == "limited"
    weather = next(s for s in ov.sources if s.kind == "weather")
    assert weather.state == "unavailable"
    assert ov.general.index is not None and -10 <= ov.general.index <= 10
    assert [f.key for f in ov.factors] == ["crime", "civil", "transport", "disaster", "weather", "environment"]
    # Live feeds are not combined with dated sample headlines; missing ones are unknown, never low.
    wf = next(f for f in ov.factors if f.key == "weather")
    assert wf.level == "unknown" or (wf.reliability == "limited" and wf.sources == ["Sample headlines"])


def test_overview_city_without_data_is_insufficient(client):
    ov = OverviewResponse.model_validate(client.get("/api/cities/tokyo/overview").json())
    assert ov.coverage.state == "insufficient"
    assert ov.general.index is None and ov.general.label == "Insufficient current evidence"
    assert all(f.level == "unknown" and f.intensity is None for f in ov.factors)
    assert ov.coverage.factors_assessed == 0


def test_city_alias_and_slug(client):
    assert client.get("/api/cities/Bengaluru/overview").json()["city"]["name"] == "Bangalore"
    assert client.get("/api/cities/new-york/overview").status_code == 200


def test_validation_errors(client):
    assert client.get("/api/cities/Atlantis/overview").status_code == 404
    assert client.get("/api/cities/Delhi/overview", params={"persona": "pirate"}).status_code == 422
    assert client.get("/api/cities/Delhi/events", params={"page_size": 1000}).status_code == 422


def test_events_filters(client):
    r = EventsResponse.model_validate(client.get("/api/cities/Delhi/events", params={"category": "crime"}).json())
    assert r.total >= 1 and all(e.category == "crime" for e in r.items)
    r = EventsResponse.model_validate(client.get("/api/cities/Delhi/events", params={"status": "counted"}).json())
    assert all(e.status == "counted" for e in r.items)
    assert all(e.origin == "sample" for e in r.items)
    r = EventsResponse.model_validate(client.get("/api/cities/Delhi/events",
                                                 params={"status": "all", "severity": "serious"}).json())
    assert r.items and all(e.severity in ("serious", "severe") for e in r.items)
    r = EventsResponse.model_validate(client.get("/api/cities/Delhi/events", params={"days": 1, "status": "all"}).json())
    assert all(e.age_hours is not None and e.age_hours <= 24 for e in r.items)


def test_weather_unavailable_is_explicit(client):
    w = WeatherResponse.model_validate(client.get("/api/cities/Delhi/weather").json())
    assert w.source.state == "unavailable" and w.status == "unavailable"
    assert w.current is None and w.alerts is None and w.daily == [] and w.hourly == []
    assert w.conditions.available is False and w.conditions.level == "unknown"
    assert w.factor.level == "unknown" or w.factor.reliability == "limited"  # news only, never "Low" by default
    assert "API" not in w.source.message and "key" not in w.source.message.lower()


def test_crime_has_disclaimer_and_honest_trend(client):
    c = CrimeResponse.model_validate(client.get("/api/cities/Chennai/crime").json())
    assert "not crime statistics" in c.explanation
    assert c.trend.available is False and c.trend.weeks == []
    assert c.breakdown.available is False


def test_insights(client):
    i = InsightsResponse.model_validate(client.get("/api/cities/Mumbai/insights", params={"persona": "elderly"}).json())
    # Network is disabled: no invented content, a clear message, reference facts only.
    assert i.status == "unavailable" and i.summary is None and i.about == []
    assert "couldn't be loaded" in i.message
    assert {f.label for f in i.facts} >= {"Country", "Region"}
    assert i.emergency and i.persona_tips


def test_methodology(client):
    MethodologyResponse.model_validate(client.get("/api/methodology").json())


@pytest.mark.parametrize("fmt,ctype", [("pdf", "application/pdf"), ("html", "text/html")])
def test_report(client, fmt, ctype):
    r = client.get("/api/cities/Hyderabad/report", params={"format": fmt})
    assert r.status_code == 200 and r.headers["content-type"].startswith(ctype)
    assert "attachment" in r.headers["content-disposition"]
    if fmt == "pdf":
        assert r.content[:4] == b"%PDF"


def test_report_html_escapes_text(client, monkeypatch):
    from core import news_client
    from core.models import NewsItem
    from datetime import datetime, timezone, timedelta

    ref = news_client.sample_reference_time(settings)

    def fake_sample(city, s):
        return [NewsItem(title="<script>alert(1)</script> robbery in Delhi", city=city, source="X",
                         published_at=ref - timedelta(hours=2), origin="sample", provider="Sample dataset")]
    monkeypatch.setattr("core.pipeline.load_sample_news", fake_sample)
    html = client.get("/api/cities/Delhi/report", params={"format": "html"}).text
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;" in html
    _ = datetime, timezone


def test_api_key_never_leaks_in_errors():
    import requests
    from core.news_client import safe_error

    resp = requests.Response()
    resp.status_code = 401
    resp.url = "https://newsapi.org/v2/everything?apiKey=SECRET123"
    err = requests.exceptions.HTTPError("401 Client Error for url: " + resp.url, response=resp)
    msg = safe_error(err)
    assert "SECRET123" not in msg and "401" in msg


def test_cors_allows_local_frontend(client):
    r = client.get("/api/health", headers={"Origin": "http://localhost:3000"})
    assert r.headers.get("access-control-allow-origin") == "http://localhost:3000"
