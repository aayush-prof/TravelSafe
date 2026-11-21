"""
TravelSafe risk model
=====================

Turns classified, location-checked, de-duplicated events into:

* per-category risk (crime, protest, accident, disaster, weather),
* a general city assessment,
* a persona-adjusted assessment,
* a data-coverage assessment,
* a structured explanation of all of the above.

Why the old model was replaced (confirmed in the original source)
-----------------------------------------------------------------
* Absolute per-event penalties, "minimum crime floors", hard caps and a
  "violent-crime confidence breaker" meant three -2 crime headlines produced
  -10 ("SEVERE") regardless of city size or coverage.
* No events returned +5.5 ("SAFE"): missing data looked like safety.
* No recency, no de-duplication, no location check.
* Persona scoring re-applied the same penalties plus an extra offset, so a
  persona could make a city look objectively more dangerous.

Model (all parameters in ``scoring_params.py``)
-----------------------------------------------
Event impact (adverse events only, severity < 0)::

    x = impact[severity] * confidence * location_conf * recency
        * (0.15 if historical) * (0.6 if resolved by arrest)
    recency = 0.5 ** (age_days / half_life[category])

Category pressure and risk (bounded, volume-resistant)::

    P = x_max + min(volume_cap, volume_weight * ln(1 + sum(other x)))
    R = 1 - exp(-P / saturation)            # 0 <= R < 1

Weather also folds in live conditions: R = 1 - (1 - R_news)(1 - R_live).

Overall (strongest category is never diluted; others add a damped term)::

    a_c = relevance_c * R_c   (sorted, a_1 largest)
    R_overall = a_1 + (1 - a_1) * damping * (1 - prod(1 - a_rest))

Index (-10..+10, higher = fewer adverse signals)::

    index = 10 - 20 * R_overall
    if index > 0: index *= coverage_factor (good 1.0, limited 0.5)
    insufficient coverage -> no index ("Insufficient data")

Positive/neutral news is displayed as context but never offsets risk.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional

from .config import CATEGORY_LABELS, RISK_CATEGORIES
from .models import ClassifiedEvent, Persona
from .scoring_params import LEVEL_LABELS, OVERALL_LABELS, PARAMS, ScoringParams, level_for


# ---------------------------------------------------------------------------
# Result structures
# ---------------------------------------------------------------------------


@dataclass
class LiveWeatherSignal:
    available: bool
    risk: float = 0.0
    factors: List[str] = field(default_factory=list)
    reason: str = ""


@dataclass
class CategoryResult:
    category: str
    label: str
    risk: float
    level: str
    pressure: float
    counted_events: int
    top_event_ids: List[str]
    drivers: List[str]
    basis: str
    news_risk: float = 0.0
    live_risk: Optional[float] = None


@dataclass
class CoverageResult:
    state: str  # good | limited | insufficient
    label: str
    reasons: List[str]
    metrics: Dict[str, object]


@dataclass
class Assessment:
    risk: Optional[float]
    index: Optional[float]
    level: str
    label: str
    summary: str


@dataclass
class PersonaAdjustment:
    category: str
    label: str
    weight: float
    base_risk: float
    persona_risk: float
    rationale: str


@dataclass
class CityAssessment:
    city: str
    as_of: datetime
    window_start: datetime
    window_end: datetime
    events: List[ClassifiedEvent]
    categories: Dict[str, CategoryResult]
    coverage: CoverageResult
    general: Assessment
    personalized: Assessment
    persona: Persona
    persona_adjustments: List[PersonaAdjustment]
    persona_explanation: str
    risk_factors: List[Dict[str, object]]
    stable_signals: List[str]
    positive_event_ids: List[str]
    latest_event_age_hours: Optional[float]
    data_span: Dict[str, Optional[datetime]]


COVERAGE_LABELS = {"good": "Good coverage", "limited": "Limited coverage", "insufficient": "Insufficient data"}


# ---------------------------------------------------------------------------
# Event preparation
# ---------------------------------------------------------------------------


def _as_utc(dt: Optional[datetime]) -> Optional[datetime]:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def prepare_events(events: List[ClassifiedEvent], as_of: datetime,
                   params: ScoringParams = PARAMS) -> List[ClassifiedEvent]:
    """Annotate events with age, recency weight, impact and exclusion status."""
    as_of = _as_utc(as_of)
    out: List[ClassifiedEvent] = []
    for src in events:
        e = src.model_copy(deep=True)
        when = _as_utc(e.news_item.incident_at) or _as_utc(e.news_item.published_at)
        e.date_basis = "incident" if e.news_item.incident_at else ("published" if when else "unknown")
        conf = e.confidence
        if when is None:
            e.age_hours = None
            if "missing publication date" not in e.flags:
                e.flags.append("missing publication date")
        else:
            age_h = (as_of - when).total_seconds() / 3600.0
            if age_h < -1.0:
                e.flags.append("timestamp in the future; treated as current with reduced confidence")
                conf *= params.future_timestamp_confidence
                age_h = 0.0
            e.age_hours = round(max(0.0, age_h), 2)

        e.counted = False
        e.impact = 0.0
        e.exclusion_reason = None
        e.recency_weight = 1.0

        if e.event_type in RISK_CATEGORIES:
            half_life = params.half_life_days[e.event_type]
            if e.age_hours is None:
                e.recency_weight = params.unknown_date_weight
            else:
                e.recency_weight = round(0.5 ** ((e.age_hours / 24.0) / half_life), 4)

            if e.location_confidence < params.min_location_confidence:
                e.exclusion_reason = "location: " + (e.location_note or "not located in this city")
            elif e.age_hours is not None and e.age_hours / 24.0 > params.max_event_age_days:
                e.exclusion_reason = f"older than {int(params.max_event_age_days)} days"
            elif e.severity >= 0:
                e.exclusion_reason = "no adverse impact described"
            else:
                impact = params.impact_by_severity.get(e.severity, 0.0)
                impact *= conf * e.location_confidence * e.recency_weight
                if e.is_historical:
                    impact *= params.historical_factor
                if e.is_resolved:
                    impact *= params.resolved_factor
                e.impact = round(impact, 4)
                e.counted = True
        out.append(e)
    return out


# ---------------------------------------------------------------------------
# Aggregation
# ---------------------------------------------------------------------------


def category_pressure(impacts: List[float], params: ScoringParams = PARAMS) -> float:
    vals = sorted((max(0.0, v) for v in impacts if v and v > 0), reverse=True)
    if not vals:
        return 0.0
    volume = params.volume_weight * math.log1p(sum(vals[1:]))
    return vals[0] + min(params.volume_cap, volume)


def pressure_to_risk(pressure: float, params: ScoringParams = PARAMS) -> float:
    if not math.isfinite(pressure) or pressure <= 0:
        return 0.0
    return 1.0 - math.exp(-pressure / params.saturation)


def combine_overall(category_risks: Dict[str, float], params: ScoringParams = PARAMS) -> float:
    contribs = sorted(
        (params.category_relevance.get(c, 1.0) * max(0.0, min(1.0, r)) for c, r in category_risks.items()),
        reverse=True,
    )
    if not contribs:
        return 0.0
    top = contribs[0]
    rest = 1.0
    for a in contribs[1:]:
        rest *= 1.0 - a
    return min(1.0, top + (1.0 - top) * params.secondary_damping * (1.0 - rest))


def apply_persona(risk: float, weight: float) -> float:
    """Adjust relevance of a category risk. Zero stays zero."""
    risk = max(0.0, min(1.0, risk))
    return 1.0 - (1.0 - risk) ** weight


def risk_to_index(risk: float, coverage_state: str, params: ScoringParams = PARAMS) -> Optional[float]:
    if coverage_state == "insufficient":
        return None
    index = 10.0 - 20.0 * max(0.0, min(1.0, risk))
    if index > 0:
        index *= params.coverage_positive_factor.get(coverage_state, 0.5)
    return round(max(-10.0, min(10.0, index)), 1)


# ---------------------------------------------------------------------------
# Coverage
# ---------------------------------------------------------------------------


def assess_coverage(events: List[ClassifiedEvent], *, news_state: str, origin: Optional[str],
                    weather_available: bool, params: ScoringParams = PARAMS,
                    extra_reasons: Optional[List[str]] = None) -> CoverageResult:
    """news_state: live | cached | stale | sample | unavailable."""
    in_window = [
        e for e in events
        if e.location_confidence >= params.min_location_confidence
        and (e.age_hours is None or e.age_hours <= params.window_days * 24)
    ]
    adverse = [e for e in in_window if e.counted]
    ages = [e.age_hours for e in in_window if e.age_hours is not None]
    newest = min(ages) if ages else None
    metrics: Dict[str, object] = {
        "articles_analyzed": sum(e.duplicate_count for e in events),
        "distinct_reports_in_window": len(in_window),
        "adverse_events_counted": len(adverse),
        "duplicates_merged": sum(e.duplicate_count - 1 for e in events),
        "excluded_location": sum(1 for e in events if (e.exclusion_reason or "").startswith("location")),
        "excluded_age": sum(1 for e in events if (e.exclusion_reason or "").startswith("older")),
        "newest_report_age_hours": round(newest, 1) if newest is not None else None,
        "mean_classification_confidence": round(sum(e.confidence for e in adverse) / len(adverse), 2) if adverse else None,
        "mean_location_confidence": round(sum(e.location_confidence for e in in_window) / len(in_window), 2) if in_window else None,
        "weather_feed": "available" if weather_available else "unavailable",
    }
    reasons: List[str] = list(extra_reasons or [])

    if news_state == "unavailable":
        reasons.insert(0, "News sources are unavailable, so there is nothing to assess.")
        return CoverageResult("insufficient", COVERAGE_LABELS["insufficient"], reasons, metrics)
    if not in_window:
        reasons.insert(0, f"No reports attributable to this city in the last {params.window_days} days.")
        return CoverageResult("insufficient", COVERAGE_LABELS["insufficient"], reasons, metrics)
    if newest is not None and newest > params.stale_after_days * 24:
        reasons.insert(0, f"The newest report is {newest / 24:.0f} days old.")
        return CoverageResult("insufficient", COVERAGE_LABELS["insufficient"], reasons, metrics)

    points = 0
    n = len(in_window)
    if n >= params.good_min_articles:
        points += 2
        reasons.append(f"{n} distinct reports in the last {params.window_days} days.")
    elif n >= params.some_min_articles:
        points += 1
        reasons.append(f"{n} distinct reports in the last {params.window_days} days (moderate volume).")
    else:
        reasons.append(f"Only {n} distinct report(s) in the last {params.window_days} days.")
    if newest is not None and newest <= params.fresh_hours:
        points += 1
        reasons.append("Most recent report is under 3 days old.")
    elif newest is not None:
        reasons.append(f"Most recent report is {newest / 24:.1f} days old.")
    if weather_available:
        points += 1
        reasons.append("Live weather data available.")
    else:
        reasons.append("Live weather data unavailable; weather relies on news only.")
    loc = metrics["mean_location_confidence"]
    if isinstance(loc, float) and loc < 0.6:
        reasons.append("Many reports do not name the city explicitly (lower location confidence).")

    if origin == "sample":
        reasons.insert(0, "Sample dataset, not live news: coverage is capped at Limited.")
        state = "limited"
    elif news_state == "stale":
        reasons.insert(0, "Live refresh failed; showing older cached results: coverage is capped at Limited.")
        state = "limited"
    else:
        state = "good" if points >= 3 else "limited"
    return CoverageResult(state, COVERAGE_LABELS[state], reasons, metrics)


# ---------------------------------------------------------------------------
# Explanations
# ---------------------------------------------------------------------------


def _age_text(hours: Optional[float]) -> str:
    if hours is None:
        return "date unknown"
    if hours < 1:
        return "under an hour ago"
    if hours < 24:
        return f"{hours:.0f} hour{'s' if round(hours) != 1 else ''} ago"
    days = round(hours / 24)
    return f"{days} day{'s' if days != 1 else ''} ago"


def _short(title: str, n: int = 80) -> str:
    return title if len(title) <= n else title[: n - 1].rstrip() + "…"


def _category_result(cat: str, events: List[ClassifiedEvent], live: Optional[LiveWeatherSignal],
                     params: ScoringParams) -> CategoryResult:
    counted = sorted((e for e in events if e.counted and e.event_type == cat), key=lambda e: -e.impact)
    pressure = category_pressure([e.impact for e in counted], params)
    news_risk = pressure_to_risk(pressure, params)
    drivers: List[str] = [f"{_short(e.news_item.title)} ({_age_text(e.age_hours)})" for e in counted[:3]]
    # Plain-language basis shown in the UI.
    n = len(counted)
    if n == 0:
        basis = "No recent reports found."
    else:
        worst = min(e.severity for e in counted)
        word = {-3: "severe", -2: "serious"}.get(worst, "minor")
        if n == 1:
            basis = f"1 recent {word} incident."
        elif word == "minor":
            basis = f"{n} recent incidents, all minor."
        else:
            basis = f"{n} recent incidents, including a {word} one."
    live_risk = None
    risk = news_risk
    if cat == "weather":
        if live is not None and live.available:
            live_risk = live.risk
            risk = 1.0 - (1.0 - news_risk) * (1.0 - live.risk)
            drivers = [f"Live conditions: {f.lower()}" for f in live.factors] + drivers
            basis = ("Current conditions: " + ", ".join(f.lower() for f in live.factors) + ". "
                     if live.factors else "Current conditions are unremarkable. ") + basis
        else:
            basis += " Live weather is not available."
    return CategoryResult(
        category=cat, label=CATEGORY_LABELS[cat], risk=round(risk, 4), level=level_for(risk, params),
        pressure=round(pressure, 3), counted_events=len(counted),
        top_event_ids=[e.id for e in counted[:5]], drivers=drivers, basis=basis,
        news_risk=round(news_risk, 4), live_risk=round(live_risk, 4) if live_risk is not None else None,
    )


def _summary(level: str, cats: Dict[str, CategoryResult], coverage: CoverageResult,
             params: ScoringParams) -> str:
    if coverage.state == "insufficient":
        return ("There is not enough recent, city-specific information to assess this city. "
                "This is not an indication that the city is safe or unsafe.")
    ranked = sorted(cats.values(), key=lambda c: -params.category_relevance.get(c.category, 1) * c.risk)
    notable = [c for c in ranked if c.level in ("guarded", "elevated", "high")]
    if not notable:
        main = "No category shows a notable adverse signal in the available reports."
    else:
        parts = [f"{c.label.lower()} ({LEVEL_LABELS[c.level].lower()})" for c in notable[:2]]
        main = "Main signals: " + " and ".join(parts) + "."
    tail = " Coverage is limited, so treat this as a rough indication." if coverage.state == "limited" else ""
    return f"{main}{tail}"


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------


def assess_city(
    city: str,
    events: List[ClassifiedEvent],
    persona: Persona,
    *,
    as_of: datetime,
    news_state: str,
    origin: Optional[str],
    live_weather: Optional[LiveWeatherSignal] = None,
    params: ScoringParams = PARAMS,
    extra_coverage_reasons: Optional[List[str]] = None,
) -> CityAssessment:
    as_of = _as_utc(as_of)
    prepared = prepare_events(events, as_of, params)
    weather_available = bool(live_weather and live_weather.available)

    categories = {c: _category_result(c, prepared, live_weather, params) for c in RISK_CATEGORIES}
    coverage = assess_coverage(prepared, news_state=news_state, origin=origin,
                               weather_available=weather_available, params=params,
                               extra_reasons=extra_coverage_reasons)

    base_risks = {c: r.risk for c, r in categories.items()}
    overall = combine_overall(base_risks, params)

    if coverage.state == "insufficient":
        general = Assessment(None, None, "insufficient", OVERALL_LABELS["insufficient"],
                             _summary("insufficient", categories, coverage, params))
    else:
        lvl = level_for(overall, params)
        general = Assessment(round(overall, 4), risk_to_index(overall, coverage.state, params), lvl,
                             OVERALL_LABELS[lvl], _summary(lvl, categories, coverage, params))

    # Persona ----------------------------------------------------------------
    adjustments: List[PersonaAdjustment] = []
    persona_risks: Dict[str, float] = {}
    for c in RISK_CATEGORIES:
        w = persona.get_weight(c)
        pr = apply_persona(base_risks[c], w)
        persona_risks[c] = pr
        adjustments.append(PersonaAdjustment(c, CATEGORY_LABELS[c], w, round(base_risks[c], 4), round(pr, 4),
                                             persona.rationale.get(c, "Standard relevance.")))
    p_overall = combine_overall(persona_risks, params)
    if coverage.state == "insufficient":
        personalized = Assessment(None, None, "insufficient", OVERALL_LABELS["insufficient"],
                                  "Personalised assessment unavailable: insufficient data.")
        p_expl = "No personalised result because the general assessment has insufficient data."
    else:
        plvl = level_for(p_overall, params)
        p_idx = risk_to_index(p_overall, coverage.state, params)
        changed = [a for a in adjustments if abs(a.persona_risk - a.base_risk) >= 0.01]
        who = f"{persona.display_name.lower()} travellers"
        if not changed:
            p_expl = (f"Same as the general result: the topics that matter more or less to {who} "
                      "have no current reports.")
        else:
            changed.sort(key=lambda a: -abs(a.persona_risk - a.base_risk))
            more = [a.label.lower() for a in changed if a.weight > 1][:2]
            less = [a.label.lower() for a in changed if a.weight < 1][:2]
            parts = []
            if more:
                parts.append(f"{' and '.join(more)} reports carry more weight")
            if less:
                parts.append(f"{' and '.join(less)} reports carry less weight")
            text = "; ".join(parts)
            p_expl = (text[:1].upper() + text[1:] + " for this profile. "
                      "This changes how existing reports are weighed; it does not add new risk.")
        personalized = Assessment(round(p_overall, 4), p_idx, plvl, OVERALL_LABELS[plvl],
                                  _summary(plvl, {c: _with_risk(categories[c], persona_risks[c], params)
                                                  for c in RISK_CATEGORIES}, coverage, params))

    # Explanations ----------------------------------------------------------
    by_id = {e.id: e for e in prepared}
    contribs = {c: params.category_relevance.get(c, 1.0) * r for c, r in base_risks.items()}
    total_contrib = sum(contribs.values()) or 1.0
    risk_factors: List[Dict[str, object]] = []
    stable: List[str] = []
    for c, res in sorted(categories.items(), key=lambda kv: -contribs[kv[0]]):
        if res.level != "low":
            top = by_id.get(res.top_event_ids[0]) if res.top_event_ids else None
            text = f"{res.label} is {LEVEL_LABELS[res.level].lower()}"
            if top is not None:
                text += f", mainly because of \u201c{_short(top.news_item.title, 90)}\u201d ({_age_text(top.age_hours)})."
            elif res.live_risk:
                text += " because of current weather conditions."
            else:
                text += "."
            risk_factors.append({"category": c, "level": res.level, "text": text,
                                 "share": round(contribs[c] / total_contrib, 3),
                                 "event_ids": res.top_event_ids[:3]})
        elif coverage.state != "insufficient":
            if c == "weather" and res.live_risk is not None:
                stable.append("Weather: live conditions show no notable concerns.")
            elif res.counted_events:
                stable.append(f"{res.label}: only minor or older reports.")
            else:
                stable.append(f"{res.label}: no recent reports (which is not proof of safety).")

    positives = [e.id for e in sorted(prepared, key=lambda e: (e.age_hours or 1e9))
                 if e.event_type == "positive" and e.location_confidence >= params.min_location_confidence][:5]
    in_window = [e for e in prepared if e.location_confidence >= params.min_location_confidence
                 and e.news_item.published_at is not None]
    dates = sorted(_as_utc(e.news_item.published_at) for e in in_window)
    ages = [e.age_hours for e in in_window if e.age_hours is not None]

    return CityAssessment(
        city=city, as_of=as_of, window_start=as_of - timedelta(days=params.window_days), window_end=as_of,
        events=prepared, categories=categories, coverage=coverage, general=general,
        personalized=personalized, persona=persona, persona_adjustments=adjustments,
        persona_explanation=p_expl, risk_factors=risk_factors, stable_signals=stable,
        positive_event_ids=positives, latest_event_age_hours=round(min(ages), 1) if ages else None,
        data_span={"earliest": dates[0] if dates else None, "latest": dates[-1] if dates else None},
    )


def _with_risk(res: CategoryResult, risk: float, params: ScoringParams) -> CategoryResult:
    copy = CategoryResult(**{**res.__dict__})
    copy.risk = risk
    copy.level = level_for(risk, params)
    return copy
