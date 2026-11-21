"""Live news parsing and stale-cache behaviour (mocked HTTP). Weather is covered in test_weather.py."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import requests

from core import pipeline
from core.config import settings


class FakeResp:
    def __init__(self, status=200, json_data=None, content=b""):
        self.status_code, self._json, self.content = status, json_data, content

    def json(self):
        return self._json

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.exceptions.HTTPError(f"{self.status_code} error", response=self)


def _rss(items):
    body = "".join(
        f"<item><title>{t} - Example Times</title><link>https://ex.com/{i}</link>"
        f"<pubDate>{d}</pubDate><source url='https://ex.com'>Example Times</source></item>"
        for i, (t, d) in enumerate(items))
    return f"<?xml version='1.0'?><rss><channel>{body}</channel></rss>".encode()


def test_google_rss_live_path(monkeypatch):
    now = datetime.now(timezone.utc)
    fmt = lambda h: (now - timedelta(hours=h)).strftime("%a, %d %b %Y %H:%M:%S GMT")  # noqa: E731
    xml = _rss([("Armed robbery at jewellery store in Delhi", fmt(5)),
                ("Armed robbery at jewellery store in Delhi", fmt(6)),
                ("Delhi tourist robbed in Goa", fmt(7))]
               + [(f"Delhi council meeting {i} on budget", fmt(8 + i)) for i in range(15)])
    monkeypatch.setattr(requests, "get", lambda *a, **k: FakeResp(content=xml))
    ctx = pipeline.analyse_city("Delhi", "student")
    assert ctx.data_mode == "live"
    news = ctx.sources[0]
    assert news.state == "available" and news.provider == "Google News RSS"
    crime = [e for e in ctx.assessment.events if e.event_type == "crime"]
    merged = next(e for e in crime if e.news_item.title.startswith("Armed"))
    assert merged.duplicate_count == 2 and merged.news_item.title.endswith("Delhi")  # source suffix stripped
    goa = next(e for e in crime if "Goa" in e.news_item.title)
    assert not goa.counted
    assert ctx.coverage.state in ("good", "limited")
    # second call is served from cache (no new request)
    calls = []
    monkeypatch.setattr(requests, "get", lambda *a, **k: calls.append(a) or FakeResp(content=xml))
    again = pipeline.analyse_city("Delhi", "family")
    assert again.sources[0].state == "available" and not [c for c in calls if "news.google" in str(c[0])]


def test_newsapi_parsing(monkeypatch):
    monkeypatch.setattr(settings, "news_api_key", "k")
    monkeypatch.setattr(settings, "enable_google_rss", False)
    now = datetime.now(timezone.utc).isoformat()
    payload = {"status": "ok", "articles": [
        {"title": "Flooding hits Mumbai suburbs", "description": "Heavy rain", "url": "https://n.com/a",
         "publishedAt": now, "source": {"name": "Wire"}},
        {"title": "[Removed]", "publishedAt": now, "source": {}},
    ]}
    monkeypatch.setattr(requests, "get", lambda *a, **k: FakeResp(json_data=payload))
    items, statuses = pipeline.fetch_live_news("Mumbai", settings)
    assert len(items) == 1 and items[0].provider == "NewsAPI" and items[0].published_at is not None
    assert statuses[0].ok


def test_stale_cache_served_and_labelled(monkeypatch):
    now = datetime.now(timezone.utc).strftime("%a, %d %b %Y %H:%M:%S GMT")
    monkeypatch.setattr(requests, "get", lambda *a, **k: FakeResp(content=_rss([("Delhi metro update", now)])))
    monkeypatch.setattr(settings, "cache_ttl_seconds", 0)
    pipeline.analyse_city("Delhi", "student")

    def fail(*a, **k):
        raise requests.exceptions.ConnectionError("down")
    monkeypatch.setattr(requests, "get", fail)
    ctx = pipeline.analyse_city("Delhi", "student")
    assert ctx.sources[0].state == "stale"
    assert ctx.coverage.state != "good"
