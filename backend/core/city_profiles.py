"""
City information (City insights page)
=====================================

Sources, all fetched live and cached for 24 hours:

1. **Wikipedia REST summary** – title, one-line description, short summary,
   thumbnail, article URL and the Wikidata item id.
2. **Wikipedia plain-text extract** – a longer introduction plus short
   excerpts from the article's *Climate* and *Transport* sections.
3. **Wikidata** – structured facts: population (with the year it refers to),
   area, elevation, country, administrative region and official website.

Time zone and emergency numbers come from TravelSafe's own reference
metadata in ``config.py`` (factual, static values).

What changed from v3 (why City insights "didn't work")
------------------------------------------------------
* v3 fetched only the Wikipedia summary. When that failed, it silently showed
  hand-written blurbs and unsourced population estimates that existed for 6
  of 45 cities, labelled "Unavailable" at the same time; the other 39 cities
  showed an empty page.
* Disambiguation pages were accepted as a city profile.
* The endpoint also ran the entire news/weather analysis first, so a slow
  news provider delayed or broke the page, and failures stayed cached for
  5 minutes with no way to retry.

Now every part is fetched independently with timeouts; a missing part is
reported as missing (never invented), and the page can be refreshed.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import quote

import requests

from .config import CITY_AREAS, CITY_COUNTRIES, CITY_STATES, Settings, get_city_region
from .logging_setup import get_logger
from .news_client import USER_AGENT, safe_error

log = get_logger("profiles")

WIKI_SUMMARY_URL = "https://en.wikipedia.org/api/rest_v1/page/summary/{title}"
WIKI_API_URL = "https://en.wikipedia.org/w/api.php"
WIKIDATA_API_URL = "https://www.wikidata.org/w/api.php"
HEADERS = {"User-Agent": USER_AGENT, "Accept": "application/json"}

# Wikipedia article titles where the plain city name is ambiguous or redirects.
WIKI_TITLES = {
    "Vizag": "Visakhapatnam", "Mysore": "Mysore", "New York": "New York City",
    "Kochi": "Kochi", "Goa": "Goa", "Bali": "Bali", "Hyderabad": "Hyderabad",
    "Darjeeling": "Darjeeling", "Udaipur": "Udaipur", "Bangalore": "Bangalore",
}

UNIT_KM2 = "Q712226"
UNIT_METRE = "Q11573"


@dataclass
class Fact:
    label: str
    value: str
    note: str = ""


@dataclass
class CityProfile:
    city: str
    status: str  # live | unavailable
    title: Optional[str] = None
    description: Optional[str] = None
    summary: Optional[str] = None
    about: List[str] = field(default_factory=list)
    climate: Optional[str] = None
    transport: Optional[str] = None
    image_url: Optional[str] = None
    article_url: Optional[str] = None
    facts: List[Fact] = field(default_factory=list)
    facts_status: str = "unavailable"  # live | unavailable
    fetched_at: Optional[datetime] = None
    problem: str = ""  # internal; logged, never sent to the browser


# ---------------------------------------------------------------------------
# Text helpers
# ---------------------------------------------------------------------------

_HEADING = re.compile(r"^(={2,5})\s*(.+?)\s*\1\s*$", re.M)


def split_sections(extract: str) -> Tuple[str, Dict[str, str]]:
    """Split a Wikipedia plain-text extract into (intro, {heading_lower: text})."""
    matches = list(_HEADING.finditer(extract))
    intro = extract[: matches[0].start()] if matches else extract
    sections: Dict[str, str] = {}
    for i, m in enumerate(matches):
        end = matches[i + 1].start() if i + 1 < len(matches) else len(extract)
        name = m.group(2).strip().lower()
        sections.setdefault(name, extract[m.end():end])
    return intro.strip(), sections


def paragraphs(text: str, limit: int = 3) -> List[str]:
    out = [re.sub(r"\s+", " ", p).strip() for p in re.split(r"\n\s*\n|\n", text or "")]
    return [p for p in out if len(p) > 40][:limit]


def excerpt(text: str, max_chars: int = 480) -> Optional[str]:
    """First paragraph, trimmed to whole sentences within ``max_chars``."""
    paras = paragraphs(text, 1)
    if not paras:
        return None
    para = paras[0]
    if len(para) <= max_chars:
        return para
    sentences = re.split(r"(?<=[.!?])\s+", para)
    out = ""
    for s in sentences:
        if len(out) + len(s) + 1 > max_chars:
            break
        out = f"{out} {s}".strip()
    return out or para[: max_chars - 1].rstrip() + "…"


def _find_section(sections: Dict[str, str], names: Tuple[str, ...]) -> Optional[str]:
    for name in names:
        for key, text in sections.items():
            if key == name or key.startswith(name):
                ex = excerpt(text)
                if ex:
                    return ex
    return None


# ---------------------------------------------------------------------------
# Wikidata helpers
# ---------------------------------------------------------------------------


def _claim_values(claims: Dict[str, Any], prop: str) -> List[Dict[str, Any]]:
    out = []
    for c in claims.get(prop, []) or []:
        snak = c.get("mainsnak") or {}
        if snak.get("snaktype") != "value":
            continue
        out.append({"value": (snak.get("datavalue") or {}).get("value"), "rank": c.get("rank", "normal"),
                    "qualifiers": c.get("qualifiers") or {}})
    return out


def _pick(values: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not values:
        return None
    preferred = [v for v in values if v["rank"] == "preferred"]
    pool = preferred or [v for v in values if v["rank"] != "deprecated"] or values

    def year(v: Dict[str, Any]) -> int:
        try:
            t = v["qualifiers"]["P585"][0]["datavalue"]["value"]["time"]
            return int(t[1:5])
        except (KeyError, IndexError, TypeError, ValueError):
            return 0
    return max(pool, key=year) | {"year": year(max(pool, key=year))}


def _quantity(v: Optional[Dict[str, Any]], unit: Optional[str] = None) -> Optional[float]:
    if not v or not isinstance(v.get("value"), dict):
        return None
    q = v["value"]
    if unit and not str(q.get("unit", "")).endswith(unit):
        return None
    try:
        return float(q.get("amount"))
    except (TypeError, ValueError):
        return None


def _entity_id(v: Optional[Dict[str, Any]]) -> Optional[str]:
    if v and isinstance(v.get("value"), dict):
        return v["value"].get("id")
    return None


def parse_wikidata_facts(claims: Dict[str, Any], labels: Dict[str, str]) -> List[Fact]:
    facts: List[Fact] = []
    country = _entity_id(_pick(_claim_values(claims, "P17")))
    region = _entity_id(_pick(_claim_values(claims, "P131")))
    if country and labels.get(country):
        facts.append(Fact("Country", labels[country]))
    if region and labels.get(region) and labels.get(region) != labels.get(country):
        facts.append(Fact("Administrative region", labels[region]))
    pop = _pick(_claim_values(claims, "P1082"))
    pop_n = _quantity(pop)
    if pop_n:
        note = f"{pop['year']} figure" if pop and pop.get("year") else ""
        facts.append(Fact("Population", f"{int(pop_n):,}", note))
    area = _quantity(_pick(_claim_values(claims, "P2046")), UNIT_KM2)
    if area:
        facts.append(Fact("Area", f"{area:,.0f} km²"))
    elev = _quantity(_pick(_claim_values(claims, "P2044")), UNIT_METRE)
    if elev is not None:
        facts.append(Fact("Elevation", f"{elev:,.0f} m"))
    site = _pick(_claim_values(claims, "P856"))
    if site and isinstance(site.get("value"), str) and site["value"].startswith(("http://", "https://")):
        facts.append(Fact("Official website", site["value"]))
    return facts


def _related_ids(claims: Dict[str, Any]) -> List[str]:
    ids = [_entity_id(_pick(_claim_values(claims, p))) for p in ("P17", "P131")]
    return [i for i in ids if i]


# ---------------------------------------------------------------------------
# Fetch
# ---------------------------------------------------------------------------


def _get(url: str, s: Settings, params: Optional[dict] = None) -> Any:
    r = requests.get(url, params=params, headers=HEADERS, timeout=s.request_timeout_seconds)
    r.raise_for_status()
    return r.json()


def fetch_city_profile(city: str, s: Settings) -> CityProfile:
    title = WIKI_TITLES.get(city, city)
    profile = CityProfile(city=city, status="unavailable")

    # 1. Summary (required for a "live" profile)
    try:
        d = _get(WIKI_SUMMARY_URL.format(title=quote(title.replace(" ", "_"))), s)
        if d.get("type") == "disambiguation":
            raise ValueError("disambiguation page")
        if not (d.get("extract") or "").strip():
            raise ValueError("empty summary")
        profile.title = d.get("title") or city
        profile.description = (d.get("description") or "").strip() or None
        profile.summary = d["extract"].strip()
        thumb = (d.get("thumbnail") or {}).get("source")
        profile.image_url = thumb if isinstance(thumb, str) and thumb.startswith("https://") else None
        profile.article_url = ((d.get("content_urls") or {}).get("desktop") or {}).get("page")
        qid = d.get("wikibase_item")
        profile.status = "live"
        profile.fetched_at = datetime.now(timezone.utc)
    except Exception as exc:  # noqa: BLE001
        profile.problem = f"Wikipedia summary: {safe_error(exc) if not isinstance(exc, ValueError) else exc}"
        log.warning("city profile city=%s unavailable: %s", city, profile.problem)
        return profile

    # 2. Longer introduction + climate / transport excerpts (optional)
    try:
        data = _get(WIKI_API_URL, s, {"action": "query", "prop": "extracts", "explaintext": 1,
                                      "redirects": 1, "titles": profile.title, "format": "json",
                                      "formatversion": 2})
        pages = (data.get("query") or {}).get("pages") or []
        text = pages[0].get("extract", "") if pages else ""
        intro, sections = split_sections(text)
        profile.about = paragraphs(intro, 3)
        profile.climate = _find_section(sections, ("climate",))
        profile.transport = _find_section(sections, ("transport", "transportation", "transit", "getting around"))
    except Exception as exc:  # noqa: BLE001
        log.info("city profile city=%s: article text unavailable (%s)", city, safe_error(exc))

    # 3. Structured facts from Wikidata (optional)
    if qid:
        try:
            ent = _get(WIKIDATA_API_URL, s, {"action": "wbgetentities", "ids": qid, "props": "claims",
                                             "format": "json"})
            claims = ((ent.get("entities") or {}).get(qid) or {}).get("claims") or {}
            labels: Dict[str, str] = {}
            rel = _related_ids(claims)
            if rel:
                lab = _get(WIKIDATA_API_URL, s, {"action": "wbgetentities", "ids": "|".join(rel),
                                                 "props": "labels", "languages": "en", "format": "json"})
                for eid, e in (lab.get("entities") or {}).items():
                    v = ((e.get("labels") or {}).get("en") or {}).get("value")
                    if v:
                        labels[eid] = v
            profile.facts = parse_wikidata_facts(claims, labels)
            profile.facts_status = "live" if profile.facts else "unavailable"
        except Exception as exc:  # noqa: BLE001
            log.info("city profile city=%s: Wikidata facts unavailable (%s)", city, safe_error(exc))
    log.info("city profile city=%s ok (facts=%d, climate=%s, transport=%s)", city, len(profile.facts),
             bool(profile.climate), bool(profile.transport))
    return profile


def reference_facts(city: str) -> List[Fact]:
    """TravelSafe's own metadata – always available."""
    facts = [Fact("Country", CITY_COUNTRIES.get(city, "Unknown"))]
    state = CITY_STATES.get(city)
    if state and state != city and get_city_region(city) == "India":
        facts.append(Fact("State", state))
    facts.append(Fact("Region", CITY_AREAS.get(city, "Unknown")))
    return facts
