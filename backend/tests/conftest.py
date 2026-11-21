"""Shared fixtures: fixed clock, event factory, offline settings."""

from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.classifier import classify_news_item  # noqa: E402
from core.location import assess_location  # noqa: E402
from core.models import ClassifiedEvent, NewsItem  # noqa: E402

NOW = datetime(2026, 6, 15, 12, 0, tzinfo=timezone.utc)


def make_event(title: str, *, city: str = "Delhi", hours_ago: Optional[float] = 6.0,
               description: Optional[str] = None, source: str = "Test Wire", url: Optional[str] = None,
               origin: str = "live", now: datetime = NOW) -> ClassifiedEvent:
    published = None if hours_ago is None else now - timedelta(hours=hours_ago)
    item = NewsItem(title=title, description=description, city=city, source=source, url=url,
                    published_at=published, origin=origin, provider="test")  # type: ignore[arg-type]
    ev = classify_news_item(item, now.year)
    conf, note = assess_location(city, title, description, origin)
    ev.location_confidence, ev.location_note = conf, note
    return ev


def filler(n: int = 16, city: str = "Delhi") -> list:
    """Neutral, city-attributed reports that establish coverage without risk."""
    return [make_event(f"{city} municipal council meeting number {i} discusses budget", city=city,
                       hours_ago=4 + i) for i in range(n)]


@pytest.fixture
def now() -> datetime:
    return NOW


@pytest.fixture(autouse=True)
def _offline(monkeypatch):
    """Never hit the network in tests."""
    import requests

    def _blocked(*args, **kwargs):
        raise requests.exceptions.ConnectionError("network disabled in tests")

    monkeypatch.setattr(requests, "get", _blocked)
    # Deterministic settings regardless of the developer's .env
    from core.config import settings
    monkeypatch.setattr(settings, "data_mode", "auto")
    monkeypatch.setattr(settings, "enable_google_rss", True)
    monkeypatch.setattr(settings, "news_api_key", "")
    monkeypatch.setattr(settings, "gnews_api_key", "")
    monkeypatch.setattr(settings, "openweather_api_key", "")
    monkeypatch.setattr(settings, "openweather_key_name", None)
    monkeypatch.setattr(settings, "openaq_api_key", "")
    monkeypatch.setattr(settings, "open_meteo_enabled", True)
    monkeypatch.setattr(settings, "usgs_enabled", True)
    monkeypatch.setattr(settings, "gdacs_enabled", True)
    monkeypatch.setattr(settings, "http_retries", 0)
    monkeypatch.setattr(settings, "cache_ttl_seconds", 900)
    import app.main
    import core.http
    # Tests set settings directly; don't let the per-request .env reload undo that.
    monkeypatch.setattr(app.main, "refresh_settings", lambda force=False: False)
    monkeypatch.setattr(core.http.time, "sleep", lambda s: None)
    from core.cache import cache
    cache.clear()
    yield
    cache.clear()
