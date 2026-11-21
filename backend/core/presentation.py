"""
Presentation layer
==================

Translates internal model values (confidences, flags, exclusion reasons,
provider errors) into short, plain-language labels for the user interface
and the PDF. The scoring model is untouched; this module only describes it.

Thresholds used for labels
--------------------------
* Classification confidence: ≥ 0.75 "High confidence", ≥ 0.5 "Moderate
  confidence", otherwise "Uncertain".
* Location confidence: ≥ 0.9 "In the city", ≥ 0.6 "Probably in the city",
  ≥ 0.4 "Location unclear", otherwise "Elsewhere".
"""

from __future__ import annotations

from typing import List, Optional, Tuple

from .models import ClassifiedEvent


def confidence_label(conf: float) -> str:
    if conf >= 0.75:
        return "High confidence"
    if conf >= 0.5:
        return "Moderate confidence"
    return "Uncertain"


def location_label(conf: float) -> str:
    if conf >= 0.9:
        return "In the city"
    if conf >= 0.6:
        return "Probably in the city"
    if conf >= 0.4:
        return "Location unclear"
    return "Elsewhere"


def severity(sev: int) -> Tuple[str, str]:
    """Return (key, label)."""
    if sev <= -3:
        return "severe", "Severe"
    if sev == -2:
        return "serious", "Serious"
    if sev == -1:
        return "minor", "Minor"
    if sev == 0:
        return "none", "No adverse impact"
    return "positive", "Positive"


_FLAG_TEXT = [
    ("multiple fatalities", "Multiple fatalities reported"),
    ("fatalities reported", "Fatalities reported"),
    ("injuries reported", "Injuries reported"),
    ("de-escalated", "Described as limited in impact"),
    ("mild weather", "Mild conditions"),
    ("forecast or warning", "Forecast or warning, not a confirmed impact"),
    ("arrest or police action", "Arrests or police action reported"),
    ("historical reference", "Refers to a past incident, so it carries little weight"),
    ("awareness or preparedness", "Awareness or preparedness activity, not an incident"),
    ("ambiguous", "Could also fit another category"),
    ("missing publication date", "Publication date unknown"),
    ("timestamp in the future", "Date looked incorrect and was treated as current"),
]


def event_notes(e: ClassifiedEvent) -> List[str]:
    notes: List[str] = []
    for flag in e.flags:
        for key, text in _FLAG_TEXT:
            if key in flag and text not in notes:
                if key == "fatalities reported" and "Multiple fatalities reported" in notes:
                    break
                notes.append(text)
                break
    return notes


def event_status(e: ClassifiedEvent) -> Tuple[str, str]:
    """Return (status key, plain explanation)."""
    if e.event_type in ("positive", "neutral"):
        return "context", "Shown for context. Not part of the assessment."
    reason = e.exclusion_reason or ""
    if e.counted:
        if e.is_historical:
            return "counted", "Counted with very little weight because it refers to a past incident."
        if e.is_resolved:
            return "counted", "Counted with reduced weight because arrests were reported."
        if e.confidence < 0.5:
            return "counted", "Counted with reduced weight because the classification is uncertain."
        return "counted", "Counted in the assessment."
    if reason.startswith("location"):
        return "not_counted", "Not counted: it appears to have happened somewhere else."
    if reason.startswith("older"):
        return "not_counted", "Not counted: too old to affect the current picture."
    if reason.startswith("no adverse"):
        return "not_counted", "Not counted: no adverse impact described."
    return "not_counted", "Not counted in the assessment."


def subtype_label(subtype: str) -> Optional[str]:
    if not subtype or subtype == "general":
        return None
    return subtype[:1].upper() + subtype[1:]


PROVIDER_NAMES = {
    "Google News RSS": "Google News",
    "NewsAPI": "NewsAPI",
    "GNews": "GNews",
    "Sample dataset": "Sample headlines",
    "OpenWeatherMap": "OpenWeatherMap",
}


def provider_name(p: Optional[str]) -> Optional[str]:
    if not p:
        return None
    return ", ".join(PROVIDER_NAMES.get(x.strip(), x.strip()) for x in p.split(","))


COVERAGE_SUMMARY = {
    "good": "Plenty of recent, city-specific information is available.",
    "limited": "Only a limited amount of recent information is available, so treat this as a rough guide.",
    "insufficient": "There isn't enough recent information to assess this city.",
}
