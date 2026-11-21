"""
Source-by-source coverage
=========================

Every data source behind an assessment gets one of these states:

| state           | meaning                                                              |
|-----------------|----------------------------------------------------------------------|
| available       | answered recently for this city                                      |
| stale           | the latest refresh failed; an older successful result is used        |
| broader_region  | answered, but the data describes a wider area than the city          |
| no_data         | answered, but has nothing for this location (e.g. no AQ station)     |
| unavailable     | the provider failed (timeout, error, rejected key …)                 |
| not_configured  | needs a key or subscription this installation doesn't have           |
| not_applicable  | deliberately not used here (e.g. live feeds with dated sample news)  |
| sample          | labelled sample headlines instead of live news                       |

The overall coverage state is derived from the factor model:

* insufficient – fewer than 35 % of the factor weight could be assessed, or no factor at all;
* good         – ≥ 80 % assessed, news coverage good, live weather available and nothing stale;
* limited      – everything in between. Sample data is capped at limited.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional

from .factors import FactorAssessment

COVERAGE_LABELS = {"good": "Good coverage", "limited": "Limited coverage", "insufficient": "Insufficient data"}
COVERAGE_SUMMARY = {
    "good": "Most factors could be checked with recent, city-specific data.",
    "limited": "Some factors could be checked, but data is thin, older or missing in places.",
    "insufficient": "There isn't enough current, city-specific data to give an assessment.",
}


@dataclass
class SourceStatus:
    key: str
    name: str
    kind: str        # news | weather | alerts | air | air_model | earthquakes | disasters | profile
    state: str       # see table above
    provider: Optional[str]
    fetched_at: Optional[datetime]
    age_seconds: Optional[float]
    detail: str = ""        # diagnostic; logged, never sent to the browser
    message: str = ""       # plain-language explanation for users
    used_for: List[str] = field(default_factory=list)
    resolution: str = ""    # geographic resolution in plain words
    attribution: str = ""


@dataclass
class OverallCoverage:
    state: str
    label: str
    summary: str
    reasons: List[str]
    assessed: int
    total: int


def overall_coverage(fa: FactorAssessment, news_state: str, news_coverage: str, weather_live: bool,
                     any_stale: bool, origin: Optional[str], news_reasons: List[str]) -> OverallCoverage:
    assessed = [f for f in fa.factors.values() if f.assessed]
    reasons: List[str] = []
    reasons.append(f"{len(assessed)} of {len(fa.factors)} factors could be assessed.")
    if fa.unknown:
        reasons.append("Not assessed: " + ", ".join(x.lower() for x in fa.unknown) + ".")
    if news_reasons:
        reasons.extend(r for r in news_reasons[:5] if r not in reasons and not r.startswith("Sample dataset"))
    if not assessed or fa.observed_share < 0.35:
        state = "insufficient"
    elif (fa.observed_share >= 0.8 and news_coverage == "good" and weather_live and not any_stale
          and origin == "live"):
        state = "good"
    else:
        state = "limited"
    if origin == "sample" and state == "good":
        state = "limited"
    if origin == "sample":
        reasons.insert(0, "Sample headlines, not live news: coverage is capped at Limited.")
    if any_stale:
        reasons.insert(0, "At least one source couldn't be refreshed, so an older result is used.")
    return OverallCoverage(state, COVERAGE_LABELS[state], COVERAGE_SUMMARY[state], reasons,
                           len(assessed), len(fa.factors))
