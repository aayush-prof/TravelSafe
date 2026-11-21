"""
News acquisition
================

Live providers (queried concurrently, results merged and later de-duplicated):

* NewsAPI.org      – needs NEWS_API_KEY
* GNews.io         – needs GNEWS_API_KEY
* Google News RSS  – keyless; can be disabled with ENABLE_GOOGLE_NEWS_RSS=false

Sample data (``sample_data/sample_news.json``) is synthetic demo content for
five cities. It is always labelled ``origin="sample"``.

Changes from the Streamlit version
----------------------------------
* No more ``_generate_sample_for_city``: the old code invented eight
  template headlines (timestamped "now") for any city without sample data,
  which then scored as "SAFE". Cities without data now report
  *insufficient data* instead.
* Unparseable dates are kept as ``None`` instead of silently becoming "now".
* Per-provider status (ok / error / count) is returned so the API can say
  exactly which sources were used or failed.
* Error messages are sanitised so API keys in request URLs never reach logs
  or responses.
"""

from __future__ import annotations

import json
import re
import time
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from functools import lru_cache
from typing import List, Optional, Tuple

import requests

from .config import Settings, city_aliases, get_city_region
from .dedup import strip_source_suffix
from .logging_setup import get_logger
from .models import NewsItem

log = get_logger("news")

NEWSAPI_URL = "https://newsapi.org/v2/everything"
GNEWS_URL = "https://gnews.io/api/v4/search"
GOOGLE_RSS_URL = "https://news.google.com/rss/search"
USER_AGENT = "TravelSafe/3.0 (educational travel-safety project)"

CRIME_QUERY_TERMS = ["crime", "police", "robbery", "theft", "assault", "murder", "arrested"]


@dataclass
class ProviderStatus:
    provider: str
    ok: bool
    count: int = 0
    error: Optional[str] = None
    duration_ms: Optional[int] = None


def safe_error(exc: Exception) -> str:
    """Describe a request failure without echoing URLs (which may contain keys)."""
    if isinstance(exc, requests.exceptions.Timeout):
        return "timed out"
    if isinstance(exc, requests.exceptions.ConnectionError):
        return "connection failed"
    if isinstance(exc, requests.exceptions.HTTPError) and exc.response is not None:
        code = exc.response.status_code
        hint = {401: "invalid API key", 403: "access denied", 426: "plan does not allow this request",
                429: "rate limit reached"}.get(code, "HTTP error")
        return f"{hint} (HTTP {code})"
    if isinstance(exc, (ValueError, ET.ParseError)):
        return "unexpected response format"
    return type(exc).__name__


def parse_datetime(value: Optional[str]) -> Optional[datetime]:
    """Parse ISO-8601 or RFC-2822 timestamps. Naive values are assumed UTC."""
    if not value or not isinstance(value, str):
        return None
    value = value.strip()
    dt: Optional[datetime] = None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        try:
            dt = parsedate_to_datetime(value)
        except (TypeError, ValueError, IndexError):
            dt = None
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _clean(text: Optional[str], limit: int = 600) -> Optional[str]:
    if not text:
        return None
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"&nbsp;|&#160;", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:limit] or None


def _alias_query(city: str, extra: Optional[List[str]] = None) -> str:
    names = " OR ".join(f'"{a}"' for a in city_aliases(city)[:3])
    q = f"({names})" if len(city_aliases(city)) > 1 else names
    if extra:
        q += " AND (" + " OR ".join(extra) + ")"
    return q


# ---------------------------------------------------------------------------
# Providers
# ---------------------------------------------------------------------------


def _fetch_newsapi(city: str, s: Settings, extra: Optional[List[str]]) -> List[NewsItem]:
    params = {
        "q": _alias_query(city, extra),
        "apiKey": s.news_api_key,
        "language": "en",
        "sortBy": "publishedAt",
        "pageSize": s.news_fetch_limit,
        "from": (datetime.now(timezone.utc) - timedelta(days=29)).strftime("%Y-%m-%d"),
    }
    r = requests.get(NEWSAPI_URL, params=params, timeout=s.request_timeout_seconds,
                     headers={"User-Agent": USER_AGENT})
    r.raise_for_status()
    data = r.json()
    if data.get("status") != "ok":
        raise ValueError("NewsAPI returned an error status")
    items = []
    for a in data.get("articles", []):
        title = (a.get("title") or "").strip()
        if not title or title == "[Removed]":
            continue
        items.append(NewsItem(
            title=title, description=_clean(a.get("description")), city=city,
            source=(a.get("source") or {}).get("name") or "NewsAPI", url=a.get("url"),
            published_at=parse_datetime(a.get("publishedAt")), provider="NewsAPI", origin="live",
        ))
    return items


def _fetch_gnews(city: str, s: Settings, extra: Optional[List[str]]) -> List[NewsItem]:
    params = {
        "q": _alias_query(city, extra),
        "token": s.gnews_api_key,
        "lang": "en",
        "max": min(s.news_fetch_limit, 10),
        "from": (datetime.now(timezone.utc) - timedelta(days=29)).strftime("%Y-%m-%dT00:00:00Z"),
    }
    r = requests.get(GNEWS_URL, params=params, timeout=s.request_timeout_seconds,
                     headers={"User-Agent": USER_AGENT})
    r.raise_for_status()
    items = []
    for a in r.json().get("articles", []):
        title = (a.get("title") or "").strip()
        if not title:
            continue
        items.append(NewsItem(
            title=title, description=_clean(a.get("description")), city=city,
            source=(a.get("source") or {}).get("name") or "GNews", url=a.get("url"),
            published_at=parse_datetime(a.get("publishedAt")), provider="GNews", origin="live",
        ))
    return items


def _fetch_google_rss(city: str, s: Settings, extra: Optional[List[str]]) -> List[NewsItem]:
    names = " OR ".join(f'"{a}"' for a in city_aliases(city)[:3])
    query = f"({names})"
    if extra:
        query += " (" + " OR ".join(extra) + ")"
    query += " when:30d"
    india = get_city_region(city) == "India"
    params = {
        "q": query,
        "hl": "en-IN" if india else "en-US",
        "gl": "IN" if india else "US",
        "ceid": "IN:en" if india else "US:en",
    }
    r = requests.get(GOOGLE_RSS_URL, params=params, timeout=s.request_timeout_seconds,
                     headers={"User-Agent": USER_AGENT})
    r.raise_for_status()
    root = ET.fromstring(r.content)
    items = []
    for node in root.findall(".//item")[: s.news_fetch_limit]:
        title = (node.findtext("title") or "").strip()
        if not title:
            continue
        source = (node.findtext("source") or "Google News").strip()
        clean_title = strip_source_suffix(title)
        desc = _clean(node.findtext("description"))
        # RSS descriptions usually just repeat the headline + source.
        if desc and (clean_title.lower() in desc.lower() or len(desc) < 25):
            desc = None
        items.append(NewsItem(
            title=clean_title, description=desc, city=city, source=source,
            url=(node.findtext("link") or "").strip() or None,
            published_at=parse_datetime(node.findtext("pubDate")),
            provider="Google News RSS", origin="live",
        ))
    return items


_PROVIDERS = {
    "NewsAPI": _fetch_newsapi,
    "GNews": _fetch_gnews,
    "Google News RSS": _fetch_google_rss,
}


def _run_provider(name: str, city: str, s: Settings, extra) -> Tuple[List[NewsItem], ProviderStatus]:
    start = time.perf_counter()
    try:
        items = _PROVIDERS[name](city, s, extra)
        ms = int((time.perf_counter() - start) * 1000)
        log.info("news provider=%s city=%s ok count=%d (%d ms)", name, city, len(items), ms)
        return items, ProviderStatus(name, True, len(items), None, ms)
    except Exception as exc:  # noqa: BLE001 - every failure is reported, never swallowed
        ms = int((time.perf_counter() - start) * 1000)
        msg = safe_error(exc)
        log.warning("news provider=%s city=%s failed: %s (%d ms)", name, city, msg, ms)
        return [], ProviderStatus(name, False, 0, msg, ms)


def fetch_live_news(city: str, s: Settings, crime_focus: bool = False) -> Tuple[List[NewsItem], List[ProviderStatus]]:
    providers = s.news_providers
    if not providers:
        return [], []
    extra = CRIME_QUERY_TERMS if crime_focus else None
    with ThreadPoolExecutor(max_workers=len(providers)) as pool:
        results = list(pool.map(lambda p: _run_provider(p, city, s, extra), providers))
    items: List[NewsItem] = []
    statuses: List[ProviderStatus] = []
    for its, st in results:
        items.extend(its)
        statuses.append(st)
    return items, statuses


# ---------------------------------------------------------------------------
# Sample data
# ---------------------------------------------------------------------------


@lru_cache(maxsize=4)
def _load_sample(path: str) -> Tuple[Tuple[dict, ...], Optional[datetime]]:
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError) as exc:
        log.error("Could not load sample data from %s: %s", path, exc)
        return tuple(), None
    raw = tuple(data.get("news", []))
    dates = [parse_datetime(r.get("published_at")) for r in raw]
    dates = [d for d in dates if d]
    return raw, (max(dates) if dates else None)


def sample_cities(s: Settings) -> List[str]:
    raw, _ = _load_sample(str(s.sample_news_path))
    return sorted({r.get("city", "") for r in raw if r.get("city")})


def sample_reference_time(s: Settings) -> Optional[datetime]:
    """The sample set is dated Nov–Dec 2025; it is evaluated as of its newest
    timestamp (+1 h) rather than today, and the UI says so explicitly."""
    _, latest = _load_sample(str(s.sample_news_path))
    return latest + timedelta(hours=1) if latest else None


def load_sample_news(city: str, s: Settings) -> List[NewsItem]:
    raw, _ = _load_sample(str(s.sample_news_path))
    items = []
    for r in raw:
        if (r.get("city") or "").lower() != city.lower():
            continue
        title = (r.get("title") or "").strip()
        if not title:
            continue
        items.append(NewsItem(
            title=title, description=r.get("description"), city=city,
            source=r.get("source") or "Sample dataset", url=r.get("url"),
            published_at=parse_datetime(r.get("published_at")),
            provider="Sample dataset", origin="sample",
        ))
    return items
