"""Convert domain objects into presentation DTOs (see schemas.py)."""

from __future__ import annotations

from typing import List, Optional

from core import presentation as pres
from core.config import (CATEGORY_LABELS, CITY_AREAS, CITY_COUNTRIES, city_aliases,
                         city_slug, get_city_region, settings)
from core.models import ClassifiedEvent, Persona
from core.news_client import sample_cities
from core.personas import get_all_personas
from core.coverage import SourceStatus
from core.factors import FACTOR_ORDER, LEVEL_RANK, Factor
from core.pipeline import CityContext
from core.scoring import CityAssessment

from .schemas import (AssessmentOut, CityInfo, CoverageOut, CriticalAlertOut, EventOut, EvidenceOut, FactorOut,
                      KeyFactorOut, PersonaInfo, SourceStatusOut)

DISCLAIMER = (
    "TravelSafe summarises recent news, weather, air-quality and natural-hazard data. It is a broad indication "
    "for trip research, not a guarantee of personal safety, not a crime rate and not an official "
    "advisory. Always check official travel advice and local authorities."
)


def city_info(city: str) -> CityInfo:
    return CityInfo(
        name=city, slug=city_slug(city), region=get_city_region(city),  # type: ignore[arg-type]
        country=CITY_COUNTRIES.get(city, "—"), area=CITY_AREAS.get(city, "—"),
        has_sample_data=city in sample_cities(settings), aliases=city_aliases(city),
    )


def persona_info(p: Persona) -> PersonaInfo:
    return PersonaInfo(id=p.name, name=p.display_name, description=p.description)


def all_personas() -> List[PersonaInfo]:
    return [persona_info(p) for p in get_all_personas().values()]


def source_out(s: SourceStatus) -> SourceStatusOut:
    return SourceStatusOut(key=s.key, name=s.name, kind=s.kind, state=s.state,  # type: ignore[arg-type]
                           provider=pres.provider_name(s.provider), updated_at=s.fetched_at,
                           message=s.message, used_for=s.used_for, resolution=s.resolution,
                           attribution=s.attribution)


def event_out(e: ClassifiedEvent) -> EventOut:
    n = e.news_item
    sev_key, sev_label = pres.severity(e.severity)
    status, note = pres.event_status(e)
    summary = (n.description or "").strip() or None
    if summary and summary.lower().startswith(n.title.lower()[:40]):
        summary = None
    return EventOut(
        id=e.id, title=n.title, summary=summary,
        url=n.url if n.url and n.url.startswith(("http://", "https://")) else None,
        source=n.source, sources=e.sources or [n.source], report_count=e.duplicate_count,
        category=e.event_type, category_label=CATEGORY_LABELS.get(e.event_type, e.event_type),
        subtype_label=pres.subtype_label(e.subtype),
        severity=sev_key, severity_label=sev_label,  # type: ignore[arg-type]
        confidence_label=pres.confidence_label(e.confidence),
        location_label=pres.location_label(e.location_confidence),
        published_at=n.published_at, age_hours=e.age_hours,
        status=status, status_note=note,  # type: ignore[arg-type]
        notes=pres.event_notes(e), origin=n.origin,
    )


def assessment_out(a) -> AssessmentOut:
    return AssessmentOut(index=a.index, level=a.level, label=a.label, summary=a.summary)


def coverage_out(ctx: CityContext) -> CoverageOut:
    c = ctx.coverage
    return CoverageOut(state=c.state, label=c.label, summary=c.summary, reasons=c.reasons,  # type: ignore[arg-type]
                       factors_assessed=c.assessed, factors_total=c.total)


def _pct(r: float) -> int:
    return int(round(100 * max(0.0, min(1.0, r))))


def factor_out(f: Factor, persona: Persona) -> FactorOut:
    note = None
    if f.persona_weight > 1:
        note = f"Matters more to {persona.display_name.lower()} travellers"
    elif f.persona_weight < 1:
        note = f"Matters less to {persona.display_name.lower()} travellers"
    return FactorOut(
        key=f.key, label=f.label, definition=f.definition, assessed=f.assessed,
        level=f.level, persona_level=f.persona_level, persona_note=note,  # type: ignore[arg-type]
        intensity=_pct(f.risk) if f.assessed else None,
        persona_intensity=_pct(f.persona_risk) if f.assessed else None,
        summary=f.summary,
        evidence=[EvidenceOut(text=e.text, kind=e.kind, source=e.source, when=e.when,  # type: ignore[arg-type]
                              url=e.url if e.url and e.url.startswith(("http://", "https://")) else None,
                              severity=e.severity) for e in f.evidence],
        sources=f.sources, time_window=f.time_window, geo_match=f.geo_match, updated_at=f.freshness,
        reliability=f.confidence, reliability_note=f.confidence_note,  # type: ignore[arg-type]
        contribution=f.contribution, raised_by_alert=bool(f.floor and f.assessed),
    )


def factors_out(ctx: CityContext) -> List[FactorOut]:
    return [factor_out(ctx.factors.factors[k], ctx.assessment.persona) for k in FACTOR_ORDER]


def critical_out(ctx: CityContext) -> List[CriticalAlertOut]:
    return [CriticalAlertOut(factor=c.factor, title=c.title, detail=c.detail, source=c.source,
                             level=c.level, when=c.when, url=c.url)  # type: ignore[arg-type]
            for c in ctx.factors.critical]


def key_factors(ctx: CityContext) -> List[KeyFactorOut]:
    out = []
    ranked = sorted((f for f in ctx.factors.factors.values() if f.assessed and f.level != "low"),
                    key=lambda f: (-LEVEL_RANK[f.level], -(f.contribution or 0)))
    for f in ranked[:3]:
        out.append(KeyFactorOut(category=f.key, level=f.level, text=f"{f.label}: {f.summary}"))  # type: ignore[arg-type]
    return out


def stable_signals(ctx: CityContext) -> List[str]:
    out = []
    for f in ctx.factors.factors.values():
        if f.assessed and f.level == "low":
            out.append(f"{f.label}: {f.summary}")
    return out


def top_events(a: CityAssessment, limit: int = 4) -> List[EventOut]:
    counted = sorted((e for e in a.events if e.counted), key=lambda e: -e.impact)
    return [event_out(e) for e in counted[:limit]]


def sources_out(ctx: CityContext, keys: Optional[List[str]] = None) -> List[SourceStatusOut]:
    return [source_out(s) for s in ctx.sources if keys is None or s.key in keys]


def find_source(ctx: CityContext, key: str) -> SourceStatusOut:
    return next(source_out(s) for s in ctx.sources if s.key == key)
