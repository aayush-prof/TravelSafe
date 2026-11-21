"""
Multi-factor travel-conditions model
====================================

Six factors are assessed separately before any summary is formed:

| key         | label                         | evidence                                                   |
|-------------|-------------------------------|------------------------------------------------------------|
| crime       | Crime & security              | news reports naming the city                               |
| civil       | Civil disruption              | news: protests, strikes, unrest                            |
| transport   | Transport disruption          | news: road/rail/air incidents, service disruption          |
| disaster    | Natural hazards               | USGS earthquakes + GDACS alerts (by distance) + news       |
| weather     | Weather                       | measured conditions, 48 h forecast hazards, official alerts, news |
| environment | Air quality                   | OpenAQ **measurements** only (modelled data = context)     |

Per factor: hazard (level), relevance (geographic match / time window),
evidence confidence and sources are reported separately. **Unknown is never
treated as low**: a factor with no working source is "unknown" and is left
out of the summary, which then can't look favourable on missing evidence.

Overall indicator (an evidence summary, not a probability of harm):

    a_f = relevance_f × R_f    over assessed factors (sorted)
    R   = a₁ + (1 − a₁) × 0.35 × (1 − Π(1 − a_rest))
    R   = max(R, floor)        floors from critical alerts (see below)
    index = 10 − 20R ; if index > 0: index × coverage_factor × observed_share
    observed_share = Σ relevance(assessed) / Σ relevance(all factors)

Relevance weights (configurable, reasoned rather than calibrated): crime 1.0,
natural hazards 1.0, civil 0.8, weather 0.8, transport 0.6, air quality 0.6.

Critical alerts are never averaged away: a GDACS **red** alert within range
sets the overall floor to High, an **orange** GDACS alert, a severe USGS
event or a credible severe news report (severity −3, < 72 h, confidence ≥ 0.7,
named in the city) to Elevated, and any official weather alert to Guarded
(the weather factor itself to Elevated). They are also listed in a banner.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional

from .config import CATEGORY_LABELS
from .models import ClassifiedEvent, Persona
from .scoring import CityAssessment, _age_text, _short, apply_persona, category_pressure, pressure_to_risk
from .scoring_params import PARAMS, level_for

FACTOR_ORDER = ["crime", "civil", "transport", "disaster", "weather", "environment"]
FACTOR_LABELS = {
    "crime": "Crime & security", "civil": "Civil disruption", "transport": "Transport disruption",
    "disaster": "Natural hazards", "weather": "Weather", "environment": "Air quality",
}
FACTOR_DEFINITIONS = {
    "crime": "Recent crime and security incidents reported in the city.",
    "civil": "Protests, strikes, curfews and unrest that can disrupt movement.",
    "transport": "Road, rail and air incidents and service disruptions.",
    "disaster": "Earthquakes, cyclones, floods, wildfires and similar hazards near the city.",
    "weather": "Current conditions, forecast hazards for the next 48 hours and official weather alerts.",
    "environment": "Measured air pollution at the nearest monitoring station.",
}
NEWS_CATEGORY = {"crime": "crime", "civil": "protest", "transport": "accident", "disaster": "disaster", "weather": "weather"}
RELEVANCE = {"crime": 1.0, "disaster": 1.0, "civil": 0.8, "weather": 0.8, "transport": 0.6, "environment": 0.6}
PERSONA_KEY = {"crime": "crime", "civil": "protest", "transport": "accident", "disaster": "disaster",
               "weather": "weather", "environment": "environment"}
FLOOR_RISK = {"guarded": 0.15, "elevated": 0.35, "high": 0.60}
LEVEL_RANK = {"unknown": -1, "low": 0, "guarded": 1, "elevated": 2, "high": 3}
AIR_RISK = {"Good": 0.03, "Moderate": 0.10, "Unhealthy for sensitive groups": 0.25, "Unhealthy": 0.45,
            "Very unhealthy": 0.65, "Hazardous": 0.80}
OVERALL_LABELS = {
    "low": "No major concerns detected",
    "guarded": "Some current concerns",
    "elevated": "Elevated concerns",
    "high": "Serious concerns",
    "insufficient": "Insufficient current evidence",
}
HAZARD_TO_NEWS_SUBTYPES = {
    "Earthquake": {"earthquake", "minor seismic"}, "Tropical cyclone": {"storm system"},
    "Flood": {"flood & landslide"}, "Volcano": {"fire & eruption"}, "Wildfire": {"fire & eruption"},
}


@dataclass
class Evidence:
    text: str
    kind: str  # news | measurement | forecast | official_alert | feed_event | model
    source: str
    when: Optional[datetime] = None
    url: Optional[str] = None
    severity: Optional[str] = None


@dataclass
class Factor:
    key: str
    label: str
    definition: str
    assessed: bool
    risk: float
    level: str  # low | guarded | elevated | high | unknown
    persona_risk: float = 0.0
    persona_level: str = "unknown"
    persona_weight: float = 1.0
    summary: str = ""
    evidence: List[Evidence] = field(default_factory=list)
    sources: List[str] = field(default_factory=list)
    time_window: str = ""
    geo_match: str = ""
    freshness: Optional[datetime] = None
    confidence: str = "none"  # good | limited | none
    confidence_note: str = ""
    contribution: Optional[float] = None
    floor: Optional[str] = None


@dataclass
class CriticalAlert:
    factor: str
    title: str
    detail: str
    source: str
    level: str  # guarded | elevated | high
    when: Optional[datetime] = None
    url: Optional[str] = None


@dataclass
class FactorAssessment:
    factors: Dict[str, Factor]
    critical: List[CriticalAlert]
    observed_share: float
    risk: Optional[float]
    level: str
    persona_risk: Optional[float]
    persona_level: str
    unknown: List[str]


def _news_evidence(events: List[ClassifiedEvent], cat: str, n: int = 3) -> List[Evidence]:
    out = []
    for e in sorted((e for e in events if e.counted and e.event_type == cat), key=lambda e: -e.impact)[:n]:
        sev = {-3: "Severe", -2: "Serious", -1: "Minor"}.get(e.severity)
        out.append(Evidence(f"{_short(e.news_item.title, 110)} ({_age_text(e.age_hours)})", "news",
                            e.news_item.source, e.news_item.published_at, e.news_item.url, sev))
    return out


def _latest(events: List[ClassifiedEvent], cat: Optional[str] = None) -> Optional[datetime]:
    ts = [e.news_item.published_at for e in events if e.news_item.published_at and (cat is None or e.event_type == cat)
          and e.location_confidence >= PARAMS.min_location_confidence]
    return max(ts) if ts else None


def _level(r: float) -> str:
    return level_for(r)


def _apply_floor(level: str, floor: Optional[str]) -> str:
    if floor and LEVEL_RANK[floor] > LEVEL_RANK.get(level, -1):
        return floor
    return level


def build_factors(news: CityAssessment, *, news_available: bool, news_label: str,
                  weather=None, air=None, hazards=None, persona: Persona, as_of: datetime) -> FactorAssessment:
    """``weather``: WeatherReport | None (None when deliberately not combined, e.g. sample mode)."""
    events = news.events
    news_ok = news_available and news.coverage.state != "insufficient"
    news_conf = "good" if news.coverage.state == "good" else "limited"
    window = f"Last {PARAMS.window_days} days; older reports count for less"
    factors: Dict[str, Factor] = {}
    critical: List[CriticalAlert] = []

    # ---- News-based factors: crime, civil, transport ----------------------
    for key in ("crime", "civil", "transport"):
        cat = NEWS_CATEGORY[key]
        res = news.categories[cat]
        f = Factor(key, FACTOR_LABELS[key], FACTOR_DEFINITIONS[key], news_ok, res.risk if news_ok else 0.0,
                   _level(res.risk) if news_ok else "unknown")
        f.sources = [news_label] if news_available else []
        f.time_window = window
        f.geo_match = "Reports that name the city"
        f.evidence = _news_evidence(events, cat)
        f.freshness = _latest(events, cat) or _latest(events)
        if news_ok:
            f.confidence, f.confidence_note = news_conf, news.coverage.label
            f.summary = res.basis
        else:
            f.confidence, f.confidence_note = "none", "No usable news coverage for this city"
            f.summary = "Not assessed: no recent news coverage could be retrieved for this city."
        factors[key] = f

    # Credible severe news (acute threat) -> critical
    for e in events:
        if (e.counted and e.severity <= -3 and e.age_hours is not None and e.age_hours <= 72
                and e.confidence >= 0.7 and e.location_confidence >= 0.9 and not e.is_historical):
            key = {"crime": "crime", "protest": "civil", "accident": "transport", "disaster": "disaster",
                   "weather": "weather"}.get(e.event_type, "crime")
            critical.append(CriticalAlert(key, _short(e.news_item.title, 120),
                                          f"Severe incident reported {_age_text(e.age_hours)}", e.news_item.source,
                                          "elevated", e.news_item.published_at, e.news_item.url))
            factors[key].floor = _apply_floor(factors[key].floor or "low", "elevated")

    # ---- Natural hazards: feeds + news (deduplicated) ----------------------
    dres = news.categories["disaster"]
    feed_ok = bool(hazards and hazards.ok)
    hazard_events = hazards.attributed if feed_ok else []
    feed_types = {h.hazard for h in hazard_events}
    covered_subtypes = set().union(*(HAZARD_TO_NEWS_SUBTYPES.get(t, set()) for t in feed_types)) if feed_types else set()
    news_impacts = [e.impact for e in events if e.counted and e.event_type == "disaster"
                    and e.subtype not in covered_subtypes]
    feed_impacts = []
    for h in hazard_events:
        age_d = max(0.0, (as_of - h.when).total_seconds() / 86400)
        rec = 0.5 ** (age_d / PARAMS.half_life_days["disaster"])
        feed_impacts.append(PARAMS.impact_by_severity.get(h.severity, 0) * 0.95 * rec)
    d_risk = pressure_to_risk(category_pressure(news_impacts + feed_impacts))
    d_assessed = feed_ok or news_ok
    fd = Factor("disaster", FACTOR_LABELS["disaster"], FACTOR_DEFINITIONS["disaster"], d_assessed,
                d_risk if d_assessed else 0.0, _level(d_risk) if d_assessed else "unknown")
    fd.sources = ([s for s, st in (("USGS", hazards.usgs_status), ("GDACS", hazards.gdacs_status))
                   if st == "available"] if hazards else []) + ([news_label] if news_available else [])
    fd.time_window = "Earthquakes: last 7 days; disaster alerts: last 14 days; news: last 30 days"
    fd.geo_match = "Earthquakes by magnitude and distance; alerts within 100–600 km depending on hazard"
    for h in hazard_events[:3]:
        fd.evidence.append(Evidence(f"{h.hazard}: {h.title} ({h.relevance})", "feed_event", h.source, h.when, h.url,
                                    {-3: "Severe", -2: "Serious", -1: "Minor"}.get(h.severity)))
        alert = (h.alert_level or "").capitalize()
        if alert in ("Red", "Orange"):  # GDACS alert level, or USGS PAGER colour
            lvl = "high" if alert == "Red" else "elevated"
            critical.append(CriticalAlert("disaster", f"{alert} {h.hazard.lower()} alert: {h.title}",
                                          h.relevance, h.source, lvl, h.when, h.url))
            fd.floor = _apply_floor(fd.floor or "low", lvl)
        elif h.source == "USGS" and h.severity <= -3:
            critical.append(CriticalAlert("disaster", h.title, h.relevance, "USGS", "elevated", h.when, h.url))
            fd.floor = _apply_floor(fd.floor or "low", "elevated")
    fd.evidence += _news_evidence([e for e in events if e.subtype not in covered_subtypes], "disaster",
                                  max(0, 3 - len(fd.evidence)))
    times = [h.when for h in hazard_events] + ([_latest(events, "disaster")] if _latest(events, "disaster") else [])
    fd.freshness = max(times) if times else (hazards.fetched_at if feed_ok else None)
    if not d_assessed:
        fd.summary = "Not assessed: the earthquake and disaster-alert feeds and news were all unavailable."
    elif hazard_events:
        worst = hazard_events[0]
        fd.summary = f"{len(hazard_events)} hazard event(s) near the city; most significant: {worst.hazard.lower()} ({worst.relevance.lower()})."
    elif dres.counted_events:
        fd.summary = dres.basis
    else:
        fd.summary = ("No earthquakes or disaster alerts near the city in the monitored period."
                      if feed_ok else "No disaster reports in the news; hazard feeds unavailable.")
    fd.confidence = "good" if feed_ok and news_ok else ("limited" if d_assessed else "none")
    fd.confidence_note = ("Hazard feeds and news available" if feed_ok and news_ok else
                          "Hazard feeds only" if feed_ok else "News only" if news_ok else "No sources")
    factors["disaster"] = fd

    # ---- Weather -------------------------------------------------------------
    wres = news.categories["weather"]
    w_news_risk = wres.news_risk if news_ok else 0.0
    live = weather is not None and weather.ok
    if live:
        r = 1.0 - (1.0 - weather.signal.risk) * (1.0 - 0.5 * w_news_risk)  # news corroborates at half weight
        fw = Factor("weather", FACTOR_LABELS["weather"], FACTOR_DEFINITIONS["weather"], True, r, _level(r))
        fw.sources = [weather.provider] + (["OpenWeatherMap alerts"] if weather.alerts_status == "available" else []) \
            + ([news_label] if news_ok and wres.counted_events else [])
        fw.geo_match = "City coordinates"
        fw.time_window = "Current conditions and the next 48 hours"
        c = weather.data.current
        fw.freshness = c.observed_at or weather.fetched_at
        for a in weather.alerts or []:
            fw.evidence.append(Evidence(f"Official alert: {a['event']}", "official_alert", a.get("issued_by") or "Weather service"))
            critical.append(CriticalAlert("weather", f"Official weather alert: {a['event']}",
                                          a.get("description", "")[:200], a.get("issued_by") or "Weather service", "guarded"))
            fw.floor = _apply_floor(fw.floor or "low", "elevated")
        for fx in weather.signal.factors[:3]:
            if "official" in fx:
                continue
            fw.evidence.append(Evidence(fx, "forecast" if fx.startswith(("Today", "Tomorrow")) else "measurement", weather.provider))
        fw.evidence += _news_evidence(events, "weather", max(0, 3 - len(fw.evidence))) if news_ok else []
        notable = [x for x in weather.signal.factors if "official" not in x]
        alert_txt = ("Official alert in force: " + "; ".join(a["event"] for a in weather.alerts) + ". "
                     if weather.alerts else "")
        fw.summary = alert_txt + ("Current conditions: " + ", ".join(x.lower() for x in notable[:3]) + "."
                      if notable else f"{c.condition}, {c.temperature_c:.0f} °C. No other weather hazards detected for the next 48 hours."
                      if alert_txt else
                      f"{c.condition}, {c.temperature_c:.0f} °C. No weather hazards detected for the next 48 hours.")
        fw.confidence, fw.confidence_note = "good", f"Live data from {weather.provider}"
    else:
        adverse_news = news_ok and _level(w_news_risk) != "low"
        fw = Factor("weather", FACTOR_LABELS["weather"], FACTOR_DEFINITIONS["weather"], adverse_news,
                    w_news_risk if adverse_news else 0.0, _level(w_news_risk) if adverse_news else "unknown")
        fw.sources = [news_label] if adverse_news else []
        fw.geo_match = "Reports that name the city" if adverse_news else ""
        fw.time_window = window if adverse_news else ""
        fw.evidence = _news_evidence(events, "weather") if adverse_news else []
        reason = (weather.public_reason if weather is not None else
                  "Live weather isn't combined with dated sample headlines.")
        fw.summary = (f"From news reports only. {reason}" if adverse_news else
                      f"Not assessed: live weather unavailable. {reason} Missing weather data is not treated as good weather.")
        fw.confidence = "limited" if adverse_news else "none"
        fw.confidence_note = "News only" if adverse_news else "No weather source"
    factors["weather"] = fw

    # ---- Air quality (measurements only) -------------------------------------
    measured = air.measured if air is not None else None
    if measured is not None and measured.category:
        r = AIR_RISK[measured.category]
        fe = Factor("environment", FACTOR_LABELS["environment"], FACTOR_DEFINITIONS["environment"], True, r, _level(r))
        drv = next((x for x in measured.readings if x.parameter == measured.driver), None)
        fe.summary = (f"{measured.category} (indicative) at {measured.station}, {measured.distance_km:.0f} km away"
                      + (f": {drv.label} {drv.value:g} {drv.unit}." if drv else "."))
        fe.evidence = [Evidence(f"{x.label}: {x.value:g} {x.unit}", "measurement", "OpenAQ", x.observed_at)
                       for x in measured.readings[:4]]
        fe.sources, fe.geo_match = ["OpenAQ"], f"Station {measured.distance_km:.0f} km from the city centre"
        fe.time_window, fe.freshness = "Latest hourly reading (within 48 hours)", measured.observed_at
        fe.confidence = "good" if measured.distance_km <= 10 else "limited"
        fe.confidence_note = "Measured; indicative category from the latest hourly value (US EPA breakpoints)"
    else:
        fe = Factor("environment", FACTOR_LABELS["environment"], FACTOR_DEFINITIONS["environment"], False, 0.0, "unknown")
        why = {"not_configured": "measured air quality isn't set up (OpenAQ key)",
               "no_data": "no monitoring station with recent readings within 25 km",
               "unavailable": "the air-quality service was unavailable"}.get(
            air.measured_status if air else "",
            "live measurements aren't combined with dated sample headlines" if air is None else "no measurements")
        model = air.modelled if air is not None else None
        ctx = (f" Modelled estimate (Open-Meteo, ~45 km grid): {model.category.lower()}; shown as context only."
               if model is not None and model.category else "")
        fe.summary = f"Not assessed: {why}. A missing measurement is not treated as clean air.{ctx}"
        fe.sources = ["Open-Meteo (modelled context)"] if model is not None else []
        fe.confidence_note = why
    factors["environment"] = fe

    # ---- Floors, persona, overall --------------------------------------------
    for f in factors.values():
        if f.floor and f.assessed:
            f.risk = max(f.risk, FLOOR_RISK[f.floor])
            f.level = _apply_floor(f.level, f.floor)
        w = persona.get_weight(PERSONA_KEY[f.key])
        f.persona_weight = w
        if f.assessed:
            f.persona_risk = apply_persona(f.risk, w)
            f.persona_level = _level(f.persona_risk)
        else:
            f.persona_risk, f.persona_level = 0.0, "unknown"

    assessed = [f for f in factors.values() if f.assessed]
    observed = sum(RELEVANCE[f.key] for f in assessed) / sum(RELEVANCE.values())
    unknown = [f.label for f in factors.values() if not f.assessed]
    overall_floor = None
    for c in critical:
        floor = "guarded" if c.factor == "weather" and c.level == "guarded" else c.level
        overall_floor = _apply_floor(overall_floor or "low", floor)

    def combine(attr: str) -> Optional[float]:
        if not assessed:
            return None
        contribs = sorted((RELEVANCE[f.key] * getattr(f, attr) for f in assessed), reverse=True)
        top = contribs[0]
        rest = 1.0
        for a in contribs[1:]:
            rest *= 1.0 - a
        r = min(1.0, top + (1.0 - top) * PARAMS.secondary_damping * (1.0 - rest))
        if overall_floor and overall_floor != "low":
            r = max(r, FLOOR_RISK[overall_floor])
        return r

    risk = combine("risk")
    prisk = combine("persona_risk")
    total = sum(RELEVANCE[f.key] * f.risk for f in assessed) or 0.0
    for f in assessed:
        f.contribution = round(RELEVANCE[f.key] * f.risk / total, 3) if total > 0.005 else 0.0
    critical.sort(key=lambda c: -LEVEL_RANK[c.level])
    return FactorAssessment(factors, critical, round(observed, 3), risk,
                            _level(risk) if risk is not None else "insufficient",
                            prisk, _level(prisk) if prisk is not None else "insufficient", unknown)


def overall_index(risk: Optional[float], coverage_state: str, observed_share: float) -> Optional[float]:
    if risk is None or coverage_state == "insufficient":
        return None
    idx = 10.0 - 20.0 * max(0.0, min(1.0, risk))
    if idx > 0:
        idx *= PARAMS.coverage_positive_factor.get(coverage_state, 0.5) * observed_share
    return round(max(-10.0, min(10.0, idx)), 1)


def overall_summary(fa: FactorAssessment, coverage_state: str) -> str:
    if coverage_state == "insufficient":
        return ("There isn't enough current evidence to assess this city. "
                + (f"Not available: {', '.join(x.lower() for x in fa.unknown)}. " if fa.unknown else "")
                + "This is not an indication that the city is safe or unsafe.")
    ranked = sorted((f for f in fa.factors.values() if f.assessed and f.level != "low"),
                    key=lambda f: (-LEVEL_RANK[f.level], -RELEVANCE[f.key] * f.risk))
    if ranked:
        main = "Main factors: " + ", ".join(f"{f.label.lower()} ({f.level})" for f in ranked[:2]) + "."
    else:
        main = "No assessed factor shows a notable concern in the available sources."
    gaps = f" Not assessed: {', '.join(x.lower() for x in fa.unknown)}." if fa.unknown else ""
    tail = " Coverage is limited, so treat this as a rough guide." if coverage_state == "limited" else ""
    return main + gaps + tail


def timeline(news: CityAssessment, hazards, as_of: datetime, days: int = 14) -> Dict[str, object]:
    """Daily counts of distinct counted incidents per factor. Only offered when
    there are at least 5 incidents spread over at least 3 days."""
    start = (as_of - timedelta(days=days - 1)).date()
    buckets = {(start + timedelta(days=i)).isoformat(): {k: 0 for k in FACTOR_ORDER[:5]} for i in range(days)}
    rev = {v: k for k, v in NEWS_CATEGORY.items()}
    n = 0
    for e in news.events:
        if not e.counted or e.news_item.published_at is None:
            continue
        d = e.news_item.published_at.astimezone(timezone.utc).date().isoformat()
        if d in buckets and e.event_type in rev:
            buckets[d][rev[e.event_type]] += 1
            n += 1
    for h in (hazards.attributed if hazards and hazards.ok else []):
        d = h.when.date().isoformat()
        if d in buckets:
            buckets[d]["disaster"] += 1
            n += 1
    active_days = sum(1 for v in buckets.values() if any(v.values()))
    available = n >= 5 and active_days >= 3
    return {
        "available": available,
        "reason": ("Distinct incidents per day (repeated coverage merged). Reflects reporting, not incidence."
                   if available else f"Not enough incidents for a timeline ({n} over {active_days} day(s); "
                                     "needs at least 5 over 3 days)."),
        "days": [{"date": k, **v} for k, v in buckets.items()] if available else [],
    }


_ = (CATEGORY_LABELS, math)
