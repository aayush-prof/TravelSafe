"""
Location relevance
==================

News searched "for a city" often only mentions it in passing ("Delhi
tourist robbed in Goa", "Mumbai-based firm ..."). This module estimates how
likely an article describes something happening *in* the target city.

Heuristic (documented in the README):

* city named in a locative phrase ("in Delhi", "at Delhi airport")      -> 1.0
* city named, no other place named locatively                           -> 0.9
* city named locatively AND another place named locatively              -> 0.6
* city's own state/region named, city itself not named                  -> 0.6
* city not named, no other place named (attributed by search/sample)    -> 0.65 sample / 0.5 live
* city named only non-locatively ("from Delhi") but another place
  named locatively ("in Goa")                                           -> 0.25 (excluded)
* city not named and another place named locatively                     -> 0.15 (excluded)

Events below ``min_location_confidence`` (0.4) are excluded from scoring and
shown in the events list with the reason.
"""

from __future__ import annotations

import re
from functools import lru_cache
from typing import Dict, List, Tuple

from .classifier import normalize
from .config import CITY_COUNTRIES, CITY_STATES, SUPPORTED_CITIES, city_aliases

_LOCATIVE_OWN = (r"(in|at|near|inside|across|outside|around|of|parts of) (the )?"
                 r"((south|north|east|west|central|old|outer|greater|downtown) )?")
_LOCATIVE_OTHER = r"(in|at|near|inside|outside) (the )?"

_EXTRA_PLACES = [
    # Common Indian states / large places not in the supported list, used only
    # to detect that an article is located elsewhere.
    "Punjab", "Haryana", "Kerala", "Karnataka", "Maharashtra", "Gujarat", "Rajasthan",
    "Bihar", "Odisha", "Assam", "Manipur", "Kashmir", "Jammu", "Uttar Pradesh",
    "Madhya Pradesh", "Tamil Nadu", "Telangana", "Andhra Pradesh", "West Bengal",
    "Himachal Pradesh", "Uttarakhand", "Jharkhand", "Chhattisgarh", "Noida", "Gurugram",
    "Gurgaon", "Ghaziabad", "Faridabad", "Thane", "Nashik", "Ludhiana", "Kanpur",
    "Meerut", "Ranchi", "Raipur", "Dehradun", "Srinagar", "Madurai", "Mangaluru",
    "Mangalore", "Pakistan", "Bangladesh", "Nepal", "Sri Lanka", "China", "Russia",
    "Ukraine", "Israel", "Gaza", "Iran", "Thailand", "Indonesia", "Malaysia", "Vietnam",
    "Philippines", "Australia", "Canada", "France", "Germany", "Italy", "Spain",
    "Netherlands", "Japan", "United States", "USA", "Britain", "England",
    "California", "Texas", "Florida", "Melbourne", "Los Angeles", "Chicago",
    "San Francisco", "Washington", "Abu Dhabi", "Sharjah", "Doha", "Riyadh", "Kuala Lumpur",
    "Jakarta", "Manila", "Seoul", "Beijing", "Shanghai", "Madrid", "Milan", "Venice",
    "Munich", "Frankfurt", "Brussels", "Vienna", "Lisbon", "Dublin", "Manchester",
    "Edinburgh", "Phuket", "Pattaya", "Lombok", "Vancouver", "Montreal",
]


def _alias_regex(names: List[str]) -> str:
    parts = sorted({normalize(n).strip() for n in names if n.strip()}, key=len, reverse=True)
    return "(" + "|".join(re.escape(p) for p in parts) + ")"


@lru_cache(maxsize=128)
def _patterns(city: str) -> Dict[str, re.Pattern]:
    own = city_aliases(city)
    own_norm = {normalize(a).strip() for a in own}
    region_names = [CITY_STATES[city]] if city in CITY_STATES and CITY_STATES[city] != city else []
    region_norm = {normalize(r).strip() for r in region_names}
    country = CITY_COUNTRIES.get(city, "")

    others: List[str] = []
    for other in SUPPORTED_CITIES:
        if other == city:
            continue
        for alias in city_aliases(other):
            if normalize(alias).strip() not in own_norm:
                others.append(alias)
    for place in _EXTRA_PLACES:
        n = normalize(place).strip()
        if n in own_norm or n in region_norm or place == country:
            continue
        # Don't treat a city's own country as "elsewhere".
        if country and n in {normalize(country).strip(), "india"}:
            continue
        others.append(place)

    b = r"(?<![a-z0-9])"
    e = r"(?![a-z0-9])"
    pats = {
        "own_any": re.compile(b + _alias_regex(own) + e),
        "own_loc": re.compile(b + _LOCATIVE_OWN + _alias_regex(own) + e),
        "other_loc": re.compile(b + _LOCATIVE_OTHER + _alias_regex(others) + e),
    }
    if region_names:
        pats["region_any"] = re.compile(b + _alias_regex(region_names) + e)
    return pats


def assess_location(city: str, title: str, description: str | None, origin: str) -> Tuple[float, str]:
    """Return (location_confidence, human-readable note)."""
    text = normalize(title) + " " + normalize(description)
    pats = _patterns(city)
    own_loc = bool(pats["own_loc"].search(text))
    own_any = own_loc or bool(pats["own_any"].search(text))
    other_match = pats["other_loc"].search(text)
    other_loc = bool(other_match)
    region_any = "region_any" in pats and bool(pats["region_any"].search(text))
    other_name = other_match.group(0).split()[-1].title() if other_match else ""

    if own_loc and not other_loc:
        return 1.0, f"Located in {city}"
    if own_any and not other_loc:
        return 0.9, f"{city} named in the report"
    if own_loc and other_loc:
        return 0.6, f"Mentions {city} and another place ({other_name})"
    if own_any and other_loc:
        return 0.25, f"{city} mentioned, but the event appears to be elsewhere ({other_name})"
    if other_loc:
        return 0.15, f"Event appears to be located elsewhere ({other_name})"
    if region_any:
        return 0.6, f"Regional report ({CITY_STATES.get(city)}); city not named"
    if origin == "sample":
        return 0.65, "Attributed to the city by the sample dataset; city not named in text"
    return 0.5, "Returned by a city search; city not named in text"
