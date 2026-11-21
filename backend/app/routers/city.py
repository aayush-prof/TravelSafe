"""City-scoped endpoints: overview, events, weather, crime, insights, refresh."""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timedelta, timezone
from typing import List, Literal, Optional
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, Depends, Query

from core.advice import PERSONA_TIPS, planner
from core.city_profiles import reference_facts
from core.config import CITY_COUNTRIES, CITY_TIMEZONES, EMERGENCY_NUMBERS, EVENT_TYPES
from core.logging_setup import get_logger
from core.coverage import SourceStatus
from core.pipeline import CityContext, analyse_city, get_crime_supplement, get_profile, refresh_city
from core.personas import get_persona
from core.scoring_params import PARAMS

from ..deps import valid_city, valid_persona
from ..schemas import (AirNowOut, AirQualityResponse, AirReadingOut, AirTrendOut, BreakdownOut, CoverageResponse,
                       CrimeResponse, DisastersResponse, EmergencyOut, EventsResponse, FactOut, HazardOut,
                       InsightsResponse, MeasuredAirOut, ModelledAirOut, OverviewResponse, PeriodOut,
                       PrecautionsOut, RefreshResponse, TimelineDay, TimelineOut, TrendOut, TrendWeek,
                       WeatherAlertOut, WeatherConditionsOut, WeatherCurrentOut, WeatherDayOut, WeatherHourOut,
                       WeatherNowOut, WeatherResponse)
from ..serializers import (DISCLAIMER, assessment_out, city_info, coverage_out, critical_out, event_out,
                           factor_out, factors_out, find_source, key_factors, persona_info, source_out,
                           sources_out, stable_signals, top_events)

router = APIRouter(prefix="/api/cities/{city}", tags=["city"])
log = get_logger("api.city")


PLANNER_KEYS = {"crime": "crime", "civil": "protest", "transport": "accident", "disaster": "disaster",
                "weather": "weather", "environment": "environment"}


def _weather_now(ctx: CityContext) -> WeatherNowOut:
    w = ctx.weather
    if not w.ok:
        return WeatherNowOut(available=False, provider=None, temperature_c=None, condition=None, group=None,
                             message=w.public_reason)
    c = w.data.current  # type: ignore[union-attr]
    return WeatherNowOut(available=True, provider=w.provider, temperature_c=c.temperature_c, condition=c.condition,
                         group=c.group, message="Couldn't refresh; showing the last update." if ctx.weather_stale else "")


def _air_now(ctx: CityContext) -> AirNowOut:
    a = ctx.air
    m, mod = a.measured, a.modelled
    pm = next((r.value for r in m.readings if r.parameter == "pm25"), None) if m else None
    msg = "" if m else next((s.message for s in ctx.sources if s.key == "air"), "")
    return AirNowOut(measured=m is not None, category=m.category if m else None, station=m.station if m else None,
                     distance_km=round(m.distance_km, 1) if m else None, pm25=pm,
                     modelled_category=mod.category if mod else None, message=msg)


@router.get("/overview", response_model=OverviewResponse)
def overview(city: str = Depends(valid_city), persona: str = Depends(valid_persona)) -> OverviewResponse:
    ctx = analyse_city(city, persona)
    a = ctx.assessment
    insufficient = ctx.coverage.state == "insufficient"
    levels = {PLANNER_KEYS[k]: ("low" if insufficient else f.level) for k, f in ctx.factors.factors.items()}
    plan = planner(levels, persona)
    tl = ctx.timeline
    return OverviewResponse(
        city=city_info(city), persona=persona_info(a.persona), as_of=a.as_of, updated_at=ctx.updated_at,
        data_mode=ctx.data_mode,  # type: ignore[arg-type]
        period=PeriodOut(start=a.window_start, end=a.window_end, days=PARAMS.window_days),
        latest_report_at=a.data_span["latest"], sources=sources_out(ctx), coverage=coverage_out(ctx),
        general=assessment_out(ctx.general), personalized=assessment_out(ctx.personalized),
        persona_explanation=ctx.persona_explanation, factors=factors_out(ctx), critical_alerts=critical_out(ctx),
        key_factors=key_factors(ctx), stable_signals=stable_signals(ctx), recent_events=top_events(a, 5),
        total_reports=len(a.events),
        timeline=TimelineOut(available=bool(tl["available"]), reason=str(tl["reason"]),
                             days=[TimelineDay(**d) for d in tl["days"]]),  # type: ignore[union-attr]
        weather_now=_weather_now(ctx), air_now=_air_now(ctx),
        precautions=PrecautionsOut(
            dos=plan["dos"], donts=plan["donts"],
            basis=("General precautions; there isn't enough current information to tailor them."
                   if insufficient else "Includes extra precautions for factors currently at Guarded or above.")),
        disclaimer=DISCLAIMER,
    )


_SEVERITY_MAX = {"minor": -1, "serious": -2, "severe": -3}


@router.get("/events", response_model=EventsResponse)
def events(
    city: str = Depends(valid_city),
    persona: str = Depends(valid_persona),
    category: Optional[List[str]] = Query(None, description="Repeatable; one of the event types"),
    q: Optional[str] = Query(None, max_length=100, description="Search title, summary and source"),
    severity: Optional[Literal["minor", "serious", "severe"]] = Query(None, description="At least this severe"),
    days: Optional[int] = Query(None, ge=1, le=90, description="Only reports from the last N days"),
    status: Literal["counted", "all", "not_counted", "context"] = "counted",
    sort: Literal["relevance", "date", "severity"] = "relevance",
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
) -> EventsResponse:
    ctx = analyse_city(city, persona)
    a = ctx.assessment
    items = list(a.events)
    counts = Counter(e.event_type for e in items)
    if category:
        wanted = {c for c in category if c in EVENT_TYPES}
        items = [e for e in items if e.event_type in wanted]
    if q:
        needle = q.lower().strip()
        items = [e for e in items if needle in (e.news_item.title + " " + (e.news_item.description or "")
                                                + " " + " ".join(e.sources)).lower()]
    if severity:
        items = [e for e in items if e.severity <= _SEVERITY_MAX[severity]]
    if days:
        items = [e for e in items if e.age_hours is not None and e.age_hours <= days * 24]
    if status == "counted":
        items = [e for e in items if e.counted]
    elif status == "not_counted":
        items = [e for e in items if e.exclusion_reason]
    elif status == "context":
        items = [e for e in items if e.event_type in ("positive", "neutral")]
    if sort == "relevance":
        items.sort(key=lambda e: (-e.impact, e.severity, e.age_hours if e.age_hours is not None else 1e9))
    elif sort == "date":
        items.sort(key=lambda e: e.age_hours if e.age_hours is not None else 1e9)
    else:
        items.sort(key=lambda e: (e.severity, -e.confidence))
    total = len(items)
    start = (page - 1) * page_size
    return EventsResponse(
        city=city, as_of=a.as_of, data_mode=ctx.data_mode, sources=sources_out(ctx, ["news"]), total=total,  # type: ignore[arg-type]
        page=page, page_size=page_size, total_reports=len(a.events),
        category_counts={t: counts.get(t, 0) for t in EVENT_TYPES},
        items=[event_out(e) for e in items[start:start + page_size]],
    )


@router.get("/weather", response_model=WeatherResponse)
def weather(city: str = Depends(valid_city), persona: str = Depends(valid_persona)) -> WeatherResponse:
    ctx = analyse_city(city, persona)
    a, w = ctx.assessment, ctx.weather
    news = sorted((e for e in a.events if e.event_type == "weather"), key=lambda e: -e.impact)
    note = ""
    if ctx.data_mode == "sample":
        note = ("Weather news on this page comes from the dated sample headlines. Live conditions are current "
                "and are not mixed into the sample assessment.")
    d = w.data
    alerts = None
    if w.alerts is not None:
        alerts = [WeatherAlertOut(event=x.get("event", "Weather alert"), issued_by=x.get("issued_by", ""),
                                  start=x.get("start"), end=x.get("end"), description=x.get("description", ""))
                  for x in w.alerts]
    alerts_src = find_source(ctx, "alerts")
    if not w.ok:
        alerts_message = "Official alerts can't be checked while live weather is unavailable."
    elif alerts is None:
        alerts_message = alerts_src.message or "Official alerts aren't available, so their absence here doesn't mean there are none."
    else:
        alerts_message = "" if alerts else "No official weather alerts are active for this location."
    status = "unavailable" if not w.ok else ("stale" if ctx.weather_stale else "available")
    cur = None
    if d is not None:
        c = d.current
        cur = WeatherCurrentOut(**{k: getattr(c, k) for k in WeatherCurrentOut.model_fields})
    return WeatherResponse(
        city=city, timezone=CITY_TIMEZONES.get(city, "UTC"),
        data_mode=ctx.data_mode, status=status, reason=w.public_reason,  # type: ignore[arg-type]
        provider=w.provider, attribution=d.attribution if d else "",
        fallback_used=bool(w.ok and any(not x.ok and x.kind != "not_configured" for x in w.attempts)),
        updated_at=w.fetched_at, source=find_source(ctx, "weather"), alerts_source=alerts_src, current=cur,
        hourly=[WeatherHourOut(time=h.time, temp_c=h.temp_c, precip_mm=h.precip_mm, precip_prob=h.precip_prob)
                for h in (d.hourly if d else [])],
        hourly_step_hours=d.hourly_step_hours if d else 1,
        daily=[WeatherDayOut(**x.__dict__) for x in (d.daily if d else [])],
        alerts=alerts, alerts_message=alerts_message,
        conditions=WeatherConditionsOut(
            available=w.ok, level=ctx.factors.factors["weather"].level if w.ok else "unknown",  # type: ignore[arg-type]
            factors=[x for x in w.signal.factors if x not in w.forecast_hazards], forecast_hazards=w.forecast_hazards),
        advice=w.advice, news_events=[event_out(e) for e in news[:6]],
        factor=factor_out(ctx.factors.factors["weather"], a.persona), note=note,
    )


@router.get("/air-quality", response_model=AirQualityResponse)
def air_quality(city: str = Depends(valid_city), persona: str = Depends(valid_persona)) -> AirQualityResponse:
    ctx = analyse_city(city, persona)
    m, mod = ctx.air.measured, ctx.air.modelled
    measured = None if m is None else MeasuredAirOut(
        station=m.station, distance_km=round(m.distance_km, 1), category=m.category, driver=m.driver,
        observed_at=m.observed_at,
        readings=[AirReadingOut(parameter=r.parameter, label=r.label, value=r.value, unit=r.unit,
                                observed_at=r.observed_at) for r in m.readings],
        trend=[AirTrendOut(time=t.time, pm25=t.pm25) for t in m.trend], attribution=m.attribution)
    modelled = None if mod is None else ModelledAirOut(
        pm25=mod.pm25, pm10=mod.pm10, us_aqi=mod.us_aqi, category=mod.category, observed_at=mod.observed_at,
        trend=[AirTrendOut(time=t.time, pm25=t.pm25) for t in mod.trend], attribution=mod.attribution)
    return AirQualityResponse(
        city=city, data_mode=ctx.data_mode, measured=measured, modelled=modelled,  # type: ignore[arg-type]
        sources=sources_out(ctx, ["air", "air_model"]),
        factor=factor_out(ctx.factors.factors["environment"], ctx.assessment.persona),
        note=("Categories use US EPA breakpoints applied to the latest hourly value, so they are indicative "
              "(official AQI uses 24-hour averages). Modelled values describe a ~45 km area and are shown for "
              "context only; they don't affect the assessment."),
    )


_SEV = {-3: "severe", -2: "serious", -1: "minor", 0: "none"}


def _hazard_out(h) -> HazardOut:
    return HazardOut(source=h.source, hazard=h.hazard, title=h.title, when=h.when,
                     distance_km=round(h.distance_km) if h.distance_km is not None else None,
                     severity=_SEV.get(h.severity, "none"), alert_level=h.alert_level,  # type: ignore[arg-type]
                     near_city=h.attributed, relevance=h.relevance,
                     url=h.url if h.url and h.url.startswith(("http://", "https://")) else None, magnitude=h.magnitude)


@router.get("/disasters", response_model=DisastersResponse)
def disasters(city: str = Depends(valid_city), persona: str = Depends(valid_persona)) -> DisastersResponse:
    ctx = analyse_city(city, persona)
    h = ctx.hazards
    news = sorted((e for e in ctx.assessment.events if e.event_type == "disaster"), key=lambda e: -e.impact)
    return DisastersResponse(
        city=city, data_mode=ctx.data_mode,  # type: ignore[arg-type]
        events=[_hazard_out(x) for x in h.events if x.attributed],
        context=[_hazard_out(x) for x in h.events if not x.attributed][:10],
        sources=sources_out(ctx, ["earthquakes", "disasters", "news"]),
        factor=factor_out(ctx.factors.factors["disaster"], ctx.assessment.persona),
        news_events=[event_out(e) for e in news[:6]],
        note=("Events near the city are those within the distance where they could plausibly affect it. "
              "Other events in the country or region are listed for context and don't affect the assessment."),
    )


@router.get("/coverage", response_model=CoverageResponse)
def coverage(city: str = Depends(valid_city), persona: str = Depends(valid_persona)) -> CoverageResponse:
    ctx = analyse_city(city, persona)
    return CoverageResponse(city=city, data_mode=ctx.data_mode, coverage=coverage_out(ctx),  # type: ignore[arg-type]
                            sources=sources_out(ctx), factors=factors_out(ctx), updated_at=ctx.updated_at)


def _trend(events, as_of) -> TrendOut:
    dated = [e for e in events if e.news_item.published_at is not None and e.age_hours is not None
             and e.age_hours <= 28 * 24]
    weeks = []
    for i in range(4):
        start = as_of - timedelta(days=7 * (i + 1))
        end = as_of - timedelta(days=7 * i)
        n = sum(1 for e in dated if start < e.news_item.published_at <= end)  # type: ignore[operator]
        weeks.append(TrendWeek(week_start=start, count=n))
    weeks.reverse()
    active_weeks = sum(1 for w in weeks if w.count)
    if len(dated) < 8 or active_weeks < 3:
        return TrendOut(available=False, weeks=[],
                        reason="There aren't enough comparable reports yet to show a weekly pattern.")
    return TrendOut(available=True, weeks=weeks,
                    reason="Number of crime-related news reports per week. This reflects coverage, not crime rates.")


@router.get("/crime", response_model=CrimeResponse)
def crime(city: str = Depends(valid_city), persona: str = Depends(valid_persona)) -> CrimeResponse:
    ctx = analyse_city(city, persona)
    a = ctx.assessment
    crime_events = [e for e in a.events if e.event_type == "crime"]
    counted = sorted((e for e in crime_events if e.counted), key=lambda e: -e.impact)
    other = [e for e in crime_events if not e.counted]
    supp, _status = get_crime_supplement(city, {e.id for e in a.events}) if ctx.data_mode == "live" else ([], [])
    srcs = sources_out(ctx, ["news"])
    breakdown_counts = Counter(e.subtype for e in counted)
    if len(counted) >= 3:
        breakdown = BreakdownOut(available=True, reason="",
                                 items=[{"label": k[:1].upper() + k[1:], "count": v}
                                        for k, v in breakdown_counts.most_common()])
    else:
        breakdown = BreakdownOut(available=False, items=[],
                                 reason="A breakdown needs at least three incidents.")
    return CrimeResponse(
        city=city, as_of=a.as_of, data_mode=ctx.data_mode, sources=srcs, coverage=coverage_out(ctx),  # type: ignore[arg-type]
        explanation=("This page lists news reports about crime in the city. It is not crime statistics: "
                     "the number of reports depends on media coverage, not on how often crime happens."),
        factor=factor_out(ctx.factors.factors["crime"], a.persona),
        incidents_counted=len(counted), articles_counted=sum(e.duplicate_count for e in counted),
        events=[event_out(e) for e in counted], not_counted=[event_out(e) for e in other],
        breakdown=breakdown, trend=_trend(counted, a.as_of),
        supplementary=[event_out(e) for e in supp[:10]],
        supplementary_note=("Results from a crime-specific search, shown for reference only. Targeted searches "
                            "over-represent crime, so they are not used in the assessment."),
    )


def _local_time(city: str) -> Optional[str]:
    tz = CITY_TIMEZONES.get(city)
    if not tz:
        return None
    try:
        now = datetime.now(timezone.utc).astimezone(ZoneInfo(tz))
    except ZoneInfoNotFoundError:
        log.warning("time zone %s not found (install tzdata)", tz)
        return None
    off = now.strftime("%z")
    return f"{now:%H:%M} (UTC{off[:3]}:{off[3:]})"


@router.get("/insights", response_model=InsightsResponse)
def insights(city: str = Depends(valid_city), persona: str = Depends(valid_persona)) -> InsightsResponse:
    """City background. Independent of the news/weather analysis so it loads on its own."""
    prof, _entry, cached, stale_copy = get_profile(city)
    p = get_persona(persona)
    live = prof.status == "live"
    facts = [FactOut(label=f.label, value=f.value, note=f.note) for f in (prof.facts or reference_facts(city))]
    if not any(f.label == "Country" for f in facts):
        facts.insert(0, FactOut(label="Country", value=CITY_COUNTRIES.get(city, "Unknown")))
    lt = _local_time(city)
    if lt:
        facts.append(FactOut(label="Local time", value=lt))
    stale = live and stale_copy
    state = "unavailable" if not live else ("stale" if stale else ("cached" if cached else "live"))
    message = ""
    if not live:
        message = "City information from Wikipedia couldn't be loaded right now. Try again in a moment."
    elif stale:
        message = "Couldn't refresh city information, so the last successful version is shown."
    tips = PERSONA_TIPS.get(persona, {})
    return InsightsResponse(
        city=city_info(city), persona=persona_info(p), status="available" if live else "unavailable",
        message=message, title=prof.title, description=prof.description, summary=prof.summary,
        about=prof.about, image_url=prof.image_url, article_url=prof.article_url, facts=facts,
        facts_source="Wikidata" if prof.facts else "TravelSafe reference data",
        climate=prof.climate, transport=prof.transport, local_time=lt,
        emergency=[EmergencyOut(**x) for x in EMERGENCY_NUMBERS.get(CITY_COUNTRIES.get(city, ""), [])],
        emergency_note="National numbers. Confirm locally on arrival; your accommodation can advise too.",
        persona_priority=str(tips.get("priority", "")),
        persona_tips=list(tips.get("tips", [])),  # type: ignore[arg-type]
        source=source_out(SourceStatus("profile", "City information", "profile",
                                       "available" if state in ("live", "cached") else state,
                                       "Wikipedia, Wikidata" if live else None, prof.fetched_at, None,
                                       prof.problem, message, [], "City article", "Wikipedia (CC BY-SA 4.0), Wikidata (CC0)")),
    )


@router.post("/refresh", response_model=RefreshResponse)
def refresh(city: str = Depends(valid_city)) -> RefreshResponse:
    """Clear cached news, weather, air-quality, hazard and city data so the next request fetches fresh data."""
    cleared = refresh_city(city)
    log.info("refresh requested city=%s cleared=%d", city, cleared)
    return RefreshResponse(city=city, cleared=cleared)
