"""
Shared city/persona data cache to ensure consistent events and scores across pages.
Caches news fetch, classification, and safety scoring for 5 minutes per city/persona.
"""

from datetime import datetime, timedelta
from typing import Any, Dict

from .news_client import fetch_news_for_city
from .classifier import classify_news_list
from .personas import get_persona
from .scoring import compute_safety_result

# Cache storage: key -> {"data": payload, "last_updated": datetime}
_CACHE: Dict[str, Dict[str, Any]] = {}
_CACHE_TTL = timedelta(minutes=5)


def _cache_key(city: str, persona: str) -> str:
    return f"{city.strip().lower()}::{persona.strip().lower()}"


def _is_fresh(entry: Dict[str, Any]) -> bool:
    last_updated: datetime = entry.get("last_updated", datetime.min)
    return datetime.utcnow() - last_updated < _CACHE_TTL


def _build_payload(city: str, persona: str) -> Dict[str, Any]:
    news_items = fetch_news_for_city(city)
    events = classify_news_list(news_items)
    persona_obj = get_persona(persona)
    safety_result = compute_safety_result(city, events, persona_obj)

    positive_neutral = safety_result.event_counts.get("positive", 0) + safety_result.event_counts.get("neutral", 0)
    now = datetime.utcnow()

    return {
        "city": city,
        "persona": persona,
        "events": events,
        "category_counts": safety_result.event_counts,
        "total_events": len(events),
        "safety_index": safety_result.persona_index,
        "base_index": safety_result.base_index,
        "positive_neutral_count": positive_neutral,
        "last_updated": now,
        "result": safety_result,
    }


def get_city_data(city: str, persona: str, force_refresh: bool = False) -> Dict[str, Any]:
    """Return cached city/persona data, refreshing if stale or forced."""
    key = _cache_key(city, persona)
    if not force_refresh:
        entry = _CACHE.get(key)
        if entry and _is_fresh(entry):
            return entry["data"]

    data = _build_payload(city, persona)
    set_city_data(city, persona, data)
    return data


def set_city_data(city: str, persona: str, data: Dict[str, Any]) -> None:
    """Store city/persona data in cache with current timestamp."""
    key = _cache_key(city, persona)
    _CACHE[key] = {"data": data, "last_updated": datetime.utcnow()}
