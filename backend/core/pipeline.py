"""
City analysis pipeline
======================

    fetch (live providers | labelled sample)  ->  classify  ->  location check
        ->  de-duplicate  ->  score (persona applied last)

The persona-independent part (fetch + classify + locate + dedup) is cached
per city, so every page of the frontend reuses one fetch. Persona scoring is
cheap and computed per request.

Data states exposed to the API:

* ``live``        fetched from a provider during this request
* ``cached``      live data served from cache (age shown)
* ``stale``       refresh failed; older live data served (age shown)
* ``sample``      labelled sample dataset (never presented as live)
* ``unavailable`` nothing could be fetched

Weather, air quality and hazard feeds are cached per provider group
(weather 15 min, air quality and hazards 30 min, failures 60 s). When a
refresh fails, the last successful result is served and marked *stale*.
Live feeds are never combined with dated sample headlines.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

from . import presentation as pres
from .cache import CacheEntry, cache
from .city_profiles import CityProfile, fetch_city_profile
from .classifier import classify_news_item
from .config import Settings, settings as default_settings
from .coverage import OverallCoverage, SourceStatus, overall_coverage
from .dedup import deduplicate
from .environment_service import AirReport, HazardReport, fetch_air, fetch_hazards
from .factors import OVERALL_LABELS, FactorAssessment, build_factors, overall_index, overall_summary, timeline
from .location import assess_location
from .logging_setup import get_logger
from .models import ClassifiedEvent, NewsItem
from .news_client import (ProviderStatus, fetch_live_news, load_sample_news, sample_cities,
                          sample_reference_time)
from .personas import get_persona
from .providers.disasters import GDACS_ATTRIBUTION, USGS_ATTRIBUTION
from .scoring import CityAssessment, assess_city
from .weather_service import WeatherReport, fetch_weather

log = get_logger("pipeline")


@dataclass
class NewsDataset:
    city: str
    events: List[ClassifiedEvent]
    origin: Optional[str]  # live | sample | None
    state: str  # live | sample | unavailable
    providers: List[ProviderStatus] = field(default_factory=list)
    fetched_at: Optional[datetime] = None
    as_of: Optional[datetime] = None
    note: str = ""


def process_items(items: List[NewsItem], city: str, reference_year: int) -> List[ClassifiedEvent]:
    events = []
    for item in items:
        ev = classify_news_item(item, reference_year)
        conf, note = assess_location(city, item.title, item.description, item.origin)
        ev.location_confidence = conf
        ev.location_note = note
        events.append(ev)
    return deduplicate(events)


def build_news_dataset(city: str, s: Settings, now: Optional[datetime] = None) -> Tuple[NewsDataset, bool]:
    """Return (dataset, ok). ``ok`` controls how long the result is cached."""
    now = now or datetime.now(timezone.utc)
    has_sample = city in sample_cities(s)

    def sample_dataset(note: str) -> NewsDataset:
        ref = sample_reference_time(s) or now
        items = load_sample_news(city, s)
        return NewsDataset(city, process_items(items, city, ref.year), "sample", "sample",
                           fetched_at=now, as_of=ref, note=note)

    if s.data_mode == "sample":
        if has_sample:
            return sample_dataset("Sample mode (DATA_MODE=sample)."), True
        return NewsDataset(city, [], None, "unavailable", fetched_at=now, as_of=now,
                           note="Sample mode is on and there is no sample data for this city."), True

    items, statuses = fetch_live_news(city, s)
    if not statuses:
        note = "No live news provider is enabled."
    elif any(st.ok for st in statuses):
        return NewsDataset(city, process_items(items, city, now.year), "live", "live", statuses,
                           fetched_at=now, as_of=now), True
    else:
        note = "All live news providers failed: " + "; ".join(f"{st.provider} – {st.error}" for st in statuses) + "."

    if s.data_mode == "auto" and has_sample:
        ds = sample_dataset(note + " Showing the labelled sample dataset instead.")
        ds.providers = statuses
        return ds, False
    return NewsDataset(city, [], None, "unavailable", statuses, fetched_at=now, as_of=now, note=note), False


def get_news_dataset(city: str, s: Settings = default_settings) -> Tuple[NewsDataset, CacheEntry, bool, bool]:
    """Return (dataset, entry, from_cache, is_stale)."""
    key = f"news::{city}::{s.data_mode}"
    entry, from_cache = cache.get_or_compute(
        key, lambda: build_news_dataset(city, s), s.cache_ttl_seconds, s.failure_cache_ttl_seconds)
    dataset: NewsDataset = entry.value
    if not entry.ok and dataset.origin != "live":
        stale = cache.get_stale(key, s.stale_max_age_seconds)
        if stale is not None and stale.value.origin == "live":
            log.warning("serving stale live news for %s (age %.0fs)", city, stale.age_seconds)
            return stale.value, stale, True, True
    return dataset, entry, from_cache, False


def _cached(key: str, compute, ttl: float, fail_ttl: float, stale_max: float):
    """Return (value, entry, from_cache, stale). When the latest attempt failed
    but an earlier successful result is still within ``stale_max``, that older
    result is returned and marked stale (never silently passed off as fresh)."""
    entry, from_cache = cache.get_or_compute(key, compute, ttl, fail_ttl)
    if not entry.ok:
        old = cache.get_stale(key, stale_max)
        if old is not None and old.ok:
            log.warning("serving stale %s (age %.0fs)", key, old.age_seconds)
            return old.value, old, True, True
    return entry.value, entry, from_cache, False


WEATHER_TTL_SECONDS = 15 * 60
ENV_TTL_SECONDS = 30 * 60


def get_weather(city: str, s: Settings = default_settings):
    """Return (WeatherReport, entry, from_cache, stale)."""
    return _cached(f"weather::{city}", lambda: (lambda r: (r, r.ok))(fetch_weather(city, s)),
                   min(s.cache_ttl_seconds, WEATHER_TTL_SECONDS), s.failure_cache_ttl_seconds, 6 * 3600)


def get_air(city: str, s: Settings = default_settings):
    return _cached(f"air::{city}", lambda: (lambda r: (r, r.ok))(fetch_air(city, s)),
                   ENV_TTL_SECONDS, s.failure_cache_ttl_seconds, 6 * 3600)


def get_hazards(city: str, s: Settings = default_settings):
    return _cached(f"hazards::{city}", lambda: (lambda r: (r, r.ok))(fetch_hazards(city, s)),
                   ENV_TTL_SECONDS, s.failure_cache_ttl_seconds, 12 * 3600)


PROFILE_TTL_SECONDS = 24 * 3600
PROFILE_FAILURE_TTL_SECONDS = 120


def get_profile(city: str, s: Settings = default_settings) -> Tuple[CityProfile, CacheEntry, bool, bool]:
    """City information. Successful lookups are cached for a day; failures for
    two minutes. If a refresh fails, the last good profile is served (stale)."""
    key = f"profile::{city}"
    entry, from_cache = cache.get_or_compute(
        key, lambda: (lambda p: (p, p.status == "live"))(fetch_city_profile(city, s)),
        PROFILE_TTL_SECONDS, PROFILE_FAILURE_TTL_SECONDS)
    if not entry.ok:
        stale = cache.get_stale(key, 7 * 24 * 3600)
        if stale is not None:
            return stale.value, stale, True, True
    return entry.value, entry, from_cache, False


def refresh_city(city: str) -> int:
    """Forget cached data for a city so the next request fetches it again."""
    return cache.invalidate(lambda k: k.split("::")[1:2] == [city])


def get_crime_supplement(city: str, main_ids: set, s: Settings = default_settings) -> Tuple[List[ClassifiedEvent], List[ProviderStatus]]:
    """Crime-focused search (live only). Shown for reference; never scored,
    because targeted searches over-represent crime relative to other news."""
    if s.data_mode == "sample" or not s.news_providers:
        return [], []

    def compute():
        items, statuses = fetch_live_news(city, s, crime_focus=True)
        now = datetime.now(timezone.utc)
        evs = [e for e in process_items(items, city, now.year) if e.event_type == "crime"]
        return (evs, statuses), any(st.ok for st in statuses)

    entry, _ = cache.get_or_compute(f"crime-supp::{city}", compute, s.cache_ttl_seconds, s.failure_cache_ttl_seconds)
    evs, statuses = entry.value
    return [e for e in evs if e.id not in main_ids], statuses


# ---------------------------------------------------------------------------
# Source statuses (plain-language; ``detail`` stays server-side)
# ---------------------------------------------------------------------------

def _age(entry: CacheEntry) -> float:
    return round(entry.age_seconds, 1)


def news_source(ds: NewsDataset, entry: CacheEntry, from_cache: bool, stale: bool, in_window: int) -> SourceStatus:
    used = ["Crime & security", "Civil disruption", "Transport disruption", "Natural hazards", "Weather"]
    if ds.state == "unavailable":
        if not ds.providers:
            return SourceStatus("news", "News reports", "news", "not_configured", None, ds.fetched_at, None, ds.note,
                                "No live news source is set up for this installation.", used, "City name in reports")
        return SourceStatus("news", "News reports", "news", "unavailable", None, ds.fetched_at, None, ds.note,
                            "News for this city couldn't be retrieved right now.", used, "City name in reports")
    if ds.origin == "sample":
        msg = ("Live news couldn't be reached, so labelled sample headlines are used instead."
               if ds.providers else "This installation is set to use labelled sample headlines.")
        return SourceStatus("news", "News reports", "news", "sample", "Sample dataset", ds.fetched_at, None,
                            ds.note or "Synthetic sample headlines.", msg, used, "City name in reports")
    providers = ", ".join(p.provider for p in ds.providers if p.ok)
    failed = [f"{p.provider}: {p.error}" for p in ds.providers if not p.ok]
    detail = ("Failed: " + "; ".join(failed)) if failed else ""
    if stale:
        return SourceStatus("news", "News reports", "news", "stale", providers, ds.fetched_at, _age(entry),
                            "Live refresh failed. " + detail, "Couldn't refresh the news; the last successful update is used.",
                            used, "City name in reports")
    if in_window == 0:
        return SourceStatus("news", "News reports", "news", "no_data", providers, ds.fetched_at, _age(entry), detail,
                            "News sources answered but had no recent reports that name this city.", used,
                            "City name in reports")
    msg = "Some news sources didn't respond; results come from the others." if failed else ""
    return SourceStatus("news", "News reports", "news", "available", providers, ds.fetched_at, _age(entry),
                        detail, msg, used, "City name in reports")


def weather_sources(w: WeatherReport, entry: CacheEntry, stale: bool, combined: bool) -> List[SourceStatus]:
    detail = "; ".join(f"{a.provider}: {a.kind or 'ok'}{f' ({a.status})' if a.status else ''}" for a in w.attempts)
    na = "Shown on the Weather page, but not combined with dated sample headlines."
    if not w.ok:
        kinds = {a.kind for a in w.attempts}
        state = "not_configured" if kinds <= {"not_configured"} else "unavailable"
        main = SourceStatus("weather", "Weather", "weather", state, None, w.fetched_at, None, detail,
                            w.public_reason, ["Weather"], "City coordinates")
        alerts = SourceStatus("alerts", "Official weather alerts", "alerts", state, None, None, None, detail,
                              "Alerts can't be checked while live weather is unavailable.", ["Weather"], "")
        return [main, alerts]
    if not combined:
        state = "not_applicable"
        msg = na
    else:
        state = "stale" if stale else "available"
        msg = "Couldn't refresh the weather; the last successful update is used." if stale else ""
        if any(not a.ok and a.kind != "not_configured" for a in w.attempts):
            msg = msg or f"The primary weather provider failed, so {w.provider} is used instead."
    main = SourceStatus("weather", "Weather", "weather", state, w.provider, w.fetched_at, _age(entry), detail, msg,
                        ["Weather"], "Point forecast for the city coordinates", w.data.attribution)
    st = w.alerts_status
    if st == "available":
        a = SourceStatus("alerts", "Official weather alerts", "alerts", "available" if combined else "not_applicable",
                         "OpenWeatherMap One Call", w.fetched_at, _age(entry), "",
                         "" if combined else na, ["Weather"], "City coordinates")
    elif st == "not_subscribed":
        a = SourceStatus("alerts", "Official weather alerts", "alerts", "not_configured", None, None, None,
                         "One Call 3.0 rejected the key",
                         "Official alerts need an OpenWeatherMap One Call 3.0 subscription, which this key doesn't have. "
                         "Check your national weather service.", ["Weather"], "")
    elif st == "not_supported":
        a = SourceStatus("alerts", "Official weather alerts", "alerts", "not_configured", None, None, None, "",
                         f"{w.provider} doesn't provide official alerts; they need an OpenWeatherMap key with One Call 3.0. "
                         "Check your national weather service.", ["Weather"], "")
    else:
        a = SourceStatus("alerts", "Official weather alerts", "alerts", "unavailable", None, None, None, "",
                         "The alert service didn't respond, so the absence of alerts here doesn't mean there are none.",
                         ["Weather"], "")
    return [main, a]


def air_sources(air: AirReport, entry: CacheEntry, stale: bool, combined: bool) -> List[SourceStatus]:
    detail = "; ".join(f"{a.provider}: {a.kind or 'ok'}" for a in air.attempts)
    m = air.measured
    if air.measured_status == "available" and m is not None:
        far = m.distance_km > 10
        state = "not_applicable" if not combined else ("stale" if stale else ("broader_region" if far else "available"))
        msg = ("Shown for reference, not combined with dated sample headlines." if not combined else
               f"Nearest station is {m.distance_km:.0f} km from the centre, so readings may not reflect the whole city."
               if far else "")
        measured = SourceStatus("air", "Air quality (measured)", "air", state, "OpenAQ", air.fetched_at, _age(entry),
                                detail, msg, ["Air quality"], f"Monitoring station {m.distance_km:.0f} km away",
                                m.attribution)
    else:
        state, msg = {
            "not_configured": ("not_configured", "Measured air quality needs an OpenAQ API key (free)."),
            "no_data": ("no_data", "No monitoring station with recent readings within 25 km of the city."),
        }.get(air.measured_status, ("unavailable", "The air-quality measurement service didn't respond."))
        measured = SourceStatus("air", "Air quality (measured)", "air", state, None, air.fetched_at, None, detail, msg,
                                ["Air quality"], "Within 25 km")
    if air.modelled_status == "available" and air.modelled is not None:
        model = SourceStatus("air_model", "Air quality (modelled)", "air_model", "broader_region",
                             "Open-Meteo", air.fetched_at, _age(entry), "",
                             "Model estimate on a ~45 km grid; shown as context and not used in the assessment.",
                             [], "~45 km model grid", air.modelled.attribution)
    elif air.modelled_status == "disabled":
        model = SourceStatus("air_model", "Air quality (modelled)", "air_model", "not_configured", None, None, None, "",
                             "Turned off in this installation's settings.", [], "")
    else:
        model = SourceStatus("air_model", "Air quality (modelled)", "air_model", "unavailable", None, None, None, detail,
                             "The air-quality model service didn't respond.", [], "")
    return [measured, model]


def hazard_sources(h: HazardReport, entry: CacheEntry, stale: bool, combined: bool) -> List[SourceStatus]:
    out = []
    for key, name, st, res, attr in (
        ("earthquakes", "Earthquakes", h.usgs_status, "Within 500 km, last 7 days", USGS_ATTRIBUTION),
        ("disasters", "Disaster alerts", h.gdacs_status, "100–600 km depending on hazard, last 14 days", GDACS_ATTRIBUTION),
    ):
        prov = "USGS" if key == "earthquakes" else "GDACS"
        if st == "available":
            state = "not_applicable" if not combined else ("stale" if stale else "available")
            msg = ("Shown for reference, not combined with dated sample headlines." if not combined else
                   "Couldn't refresh; the last successful update is used." if stale else "")
            out.append(SourceStatus(key, name, key, state, prov, h.fetched_at, _age(entry), "", msg,
                                    ["Natural hazards"], res, attr))
        elif st == "disabled":
            out.append(SourceStatus(key, name, key, "not_configured", None, None, None, "",
                                    "Turned off in this installation's settings.", ["Natural hazards"], res))
        else:
            out.append(SourceStatus(key, name, key, "unavailable", None, h.fetched_at, None,
                                    "; ".join(f"{a.provider}: {a.kind}" for a in h.attempts if a.provider == prov),
                                    f"The {prov} feed didn't respond.", ["Natural hazards"], res))
    return out


# ---------------------------------------------------------------------------
# Analysis
# ---------------------------------------------------------------------------

@dataclass
class Summary:
    index: Optional[float]
    level: str
    label: str
    summary: str


@dataclass
class CityContext:
    assessment: CityAssessment
    factors: FactorAssessment
    coverage: OverallCoverage
    general: Summary
    personalized: Summary
    persona_explanation: str
    dataset: NewsDataset
    weather: WeatherReport
    weather_stale: bool
    air: AirReport
    hazards: HazardReport
    sources: List[SourceStatus]
    data_mode: str  # live | sample | none
    timeline: Dict[str, object]
    updated_at: Optional[datetime]


def _persona_explanation(fa: FactorAssessment, persona) -> str:
    changed = [f for f in fa.factors.values() if f.assessed and abs(f.persona_risk - f.risk) >= 0.01]
    who = f"{persona.display_name.lower()} travellers"
    if not changed:
        return (f"Same as the general result: the factors that matter more or less to {who} "
                "show no current concerns.")
    more = [f.label.lower() for f in changed if f.persona_weight > 1][:2]
    less = [f.label.lower() for f in changed if f.persona_weight < 1][:2]
    parts = []
    if more:
        parts.append(f"{' and '.join(more)} carry more weight")
    if less:
        parts.append(f"{' and '.join(less)} carry less weight")
    text = "; ".join(parts)
    return text[:1].upper() + text[1:] + f" for {who}. This changes how existing evidence is weighed; it never adds risk."


def analyse_city(city: str, persona_name: str, s: Settings = default_settings) -> CityContext:
    ds, entry, from_cache, stale = get_news_dataset(city, s)
    weather, w_entry, _w_cached, w_stale = get_weather(city, s)
    air, a_entry, _a_cached, a_stale = get_air(city, s)
    hazards, h_entry, _h_cached, h_stale = get_hazards(city, s)
    persona = get_persona(persona_name)
    combined = ds.origin != "sample"  # live feeds describe today; sample headlines are dated

    extra: List[str] = []
    if ds.origin == "sample":
        extra.append(f"Sample data is evaluated as of its reference date ({ds.as_of:%d %b %Y}).")
    failed = [p for p in ds.providers if not p.ok]
    if failed and ds.origin == "live":
        extra.append("Some news sources didn't respond: " + ", ".join(pres.provider_name(p.provider) or p.provider
                                                                     for p in failed) + ".")
    news_state = {"live": "stale" if stale else ("cached" if from_cache else "live"),
                  "sample": "sample", "unavailable": "unavailable"}[ds.state]
    as_of = ds.as_of or datetime.now(timezone.utc)
    assessment = assess_city(city, ds.events, persona, as_of=as_of, news_state=news_state, origin=ds.origin,
                             live_weather=None, extra_coverage_reasons=extra)
    news_label = ("Sample headlines" if ds.origin == "sample" else
                  ", ".join(pres.provider_name(p.provider) or p.provider for p in ds.providers if p.ok) or "News")
    fa = build_factors(assessment, news_available=ds.state != "unavailable", news_label=news_label,
                       weather=weather if combined else None, air=air if combined else None,
                       hazards=hazards if combined else None, persona=persona, as_of=assessment.as_of)
    in_window = int(assessment.coverage.metrics.get("distinct_reports_in_window") or 0)
    sources = ([news_source(ds, entry, from_cache, stale, in_window)]
               + weather_sources(weather, w_entry, w_stale, combined)
               + air_sources(air, a_entry, a_stale, combined)
               + hazard_sources(hazards, h_entry, h_stale, combined))
    any_stale = any(x.state == "stale" for x in sources)
    news_reasons = [r for r in assessment.coverage.reasons if "weather" not in r.lower()]
    cov = overall_coverage(fa, news_state, assessment.coverage.state, combined and weather.ok, any_stale,
                           ds.origin, news_reasons)
    if cov.state == "insufficient":
        general = Summary(None, "insufficient", OVERALL_LABELS["insufficient"], overall_summary(fa, cov.state))
        personal = Summary(None, "insufficient", OVERALL_LABELS["insufficient"],
                           "No personalised result: there isn't enough current evidence.")
        p_expl = "No personalised result because the general assessment has insufficient evidence."
    else:
        def label(level: str) -> str:
            # A favourable result on partial coverage says exactly that, never "safe".
            if level == "low" and cov.state != "good":
                return "No major concerns in the available sources"
            return OVERALL_LABELS[level]
        general = Summary(overall_index(fa.risk, cov.state, fa.observed_share), fa.level,
                          label(fa.level), overall_summary(fa, cov.state))
        personal = Summary(overall_index(fa.persona_risk, cov.state, fa.observed_share), fa.persona_level,
                           label(fa.persona_level), overall_summary(fa, cov.state))
        p_expl = _persona_explanation(fa, persona)
    times = [x.fetched_at for x in sources if x.fetched_at and x.state in ("available", "stale", "broader_region", "no_data")]
    mode = ds.origin or "none"
    return CityContext(assessment, fa, cov, general, personal, p_expl, ds, weather, w_stale, air, hazards, sources,
                       mode, timeline(assessment, hazards if combined else None, assessment.as_of),
                       max(times) if times else None)


def cache_stats() -> Dict[str, int]:
    return cache.stats()
