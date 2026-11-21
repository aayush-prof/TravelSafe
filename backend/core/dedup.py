"""
Duplicate / related-story handling
==================================

Syndicated or repeated coverage of one incident must not be counted as
several independent incidents.

1. **Canonical URL** – query strings (utm_*, etc.), fragments, ``www.``,
   scheme and trailing slashes are stripped. Identical canonical URLs are
   the same article.
2. **Similarity fallback** – two events are the same incident only if all
   of these hold:
   * same category and subtype,
   * published within ``dedup_window_hours`` (72 h) of each other,
   * title-token Jaccard similarity ≥ ``dedup_similarity`` (0.6) after
     removing stop-words, the city name and the source suffix,
   * any numbers in both titles agree (e.g. "3 injured" vs "5 injured" are
     kept separate, to avoid merging genuinely different incidents).

The representative keeps the most complete record (highest confidence, then
longest description). All sources/URLs and the report count are preserved.
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import List, Optional, Set
from urllib.parse import urlsplit

from .classifier import normalize
from .config import city_aliases
from .models import ClassifiedEvent
from .scoring_params import PARAMS, ScoringParams

_STOP = {
    "a", "an", "the", "in", "on", "at", "of", "for", "to", "and", "or", "as", "after", "with",
    "by", "from", "is", "are", "was", "were", "be", "near", "over", "into", "amid", "says",
    "said", "report", "reported", "reports", "police", "city", "news", "latest", "update",
    "live", "updates", "new",
}
_NUM_WORDS = {
    "one": "1", "two": "2", "three": "3", "four": "4", "five": "5", "six": "6",
    "seven": "7", "eight": "8", "nine": "9", "ten": "10",
}


def canonical_url(url: Optional[str]) -> Optional[str]:
    if not url or url.strip() in {"", "#"}:
        return None
    try:
        parts = urlsplit(url.strip())
    except ValueError:
        return None
    if not parts.netloc:
        return None
    host = parts.netloc.lower()
    if host.startswith("www."):
        host = host[4:]
    path = parts.path.rstrip("/")
    return f"{host}{path}"


def strip_source_suffix(title: str) -> str:
    """Google News titles end with ' - Source Name'."""
    return re.sub(r"\s+[-|–]\s+[^-|–]{2,60}$", "", title).strip()


def _tokens(title: str, city: str) -> Set[str]:
    text = normalize(strip_source_suffix(title))
    for alias in city_aliases(city):
        text = text.replace(" " + normalize(alias).strip() + " ", " ")
    toks = set()
    for t in text.split():
        t = _NUM_WORDS.get(t, t)
        if t not in _STOP and len(t) > 1 or t.isdigit():
            toks.add(t)
    return toks


def _numbers(tokens: Set[str]) -> Set[str]:
    return {t for t in tokens if t.isdigit()}


def _jaccard(a: Set[str], b: Set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def _hours_apart(a: Optional[datetime], b: Optional[datetime]) -> float:
    if a is None or b is None:
        return 0.0  # unknown dates do not block a match on their own
    return abs((a - b).total_seconds()) / 3600.0


def same_incident(a: ClassifiedEvent, b: ClassifiedEvent, params: ScoringParams = PARAMS) -> bool:
    ua, ub = canonical_url(a.news_item.url), canonical_url(b.news_item.url)
    if ua and ub and ua == ub:
        return True
    if a.event_type != b.event_type or a.subtype != b.subtype:
        return False
    if _hours_apart(a.news_item.published_at, b.news_item.published_at) > params.dedup_window_hours:
        return False
    ta, tb = _tokens(a.news_item.title, a.news_item.city), _tokens(b.news_item.title, b.news_item.city)
    na, nb = _numbers(ta), _numbers(tb)
    if na and nb and na != nb:
        return False
    return _jaccard(ta, tb) >= params.dedup_similarity


def _quality(e: ClassifiedEvent) -> tuple:
    return (e.confidence, len(e.news_item.description or ""), e.location_confidence)


def deduplicate(events: List[ClassifiedEvent], params: ScoringParams = PARAMS) -> List[ClassifiedEvent]:
    """Cluster events describing the same incident; return one per cluster."""
    clusters: List[List[ClassifiedEvent]] = []
    for ev in events:
        for cluster in clusters:
            if any(same_incident(ev, other, params) for other in cluster):
                cluster.append(ev)
                break
        else:
            clusters.append([ev])

    result: List[ClassifiedEvent] = []
    for cluster in clusters:
        best = max(cluster, key=_quality)
        rep = best.model_copy(deep=True)
        sources: List[str] = []
        urls: List[str] = []
        for e in cluster:
            for s in e.sources or [e.news_item.source]:
                if s and s not in sources:
                    sources.append(s)
            for u in e.urls:
                if u and u not in urls:
                    urls.append(u)
        rep.sources = sources
        rep.urls = urls
        rep.duplicate_count = len(cluster)
        if len(cluster) > 1:
            # Independent sources corroborate the classification a little,
            # but more articles never add *impact*.
            independent = len(set(sources))
            rep.confidence = round(min(0.95, rep.confidence + 0.03 * (independent - 1)), 2)
            rep.flags = rep.flags + [f"{len(cluster)} reports merged as one incident"]
        result.append(rep)
    return result
