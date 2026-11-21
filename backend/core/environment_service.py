"""Air quality (measured via OpenAQ, modelled context via Open-Meteo) and
geospatial hazards (USGS, GDACS) for a city."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import List, Optional

from .config import CITY_COORDINATES, CITY_COUNTRIES, Settings
from .http import HttpPolicy, ProviderError
from .logging_setup import get_logger
from .providers.air import MeasuredAir, ModelledAir, fetch_open_meteo_air, fetch_openaq
from .providers.disasters import HazardEvent, dedupe_quakes, fetch_gdacs, fetch_usgs
from .weather_service import Attempt

log = get_logger("environment")


def _policy(s: Settings) -> HttpPolicy:
    return HttpPolicy(connect_timeout=s.connect_timeout_seconds, read_timeout=s.request_timeout_seconds,
                      retries=s.http_retries)


@dataclass
class AirReport:
    city: str
    measured: Optional[MeasuredAir] = None
    measured_status: str = "not_configured"  # available | not_configured | no_data | unavailable
    modelled: Optional[ModelledAir] = None
    modelled_status: str = "disabled"        # available | disabled | unavailable
    attempts: List[Attempt] = field(default_factory=list)
    fetched_at: Optional[datetime] = None

    @property
    def ok(self) -> bool:  # used by the cache: success if any source answered
        return self.measured_status in ("available", "no_data") or self.modelled_status == "available"


def fetch_air(city: str, s: Settings, now: Optional[datetime] = None) -> AirReport:
    r = AirReport(city, fetched_at=datetime.now(timezone.utc))
    c = CITY_COORDINATES.get(city)
    if not c:
        r.measured_status = r.modelled_status = "unavailable"
        return r
    pol = _policy(s)
    if s.openaq_api_key:
        try:
            r.measured = fetch_openaq(c["lat"], c["lon"], s.openaq_api_key, pol, now)
            r.measured_status = "available"
            r.attempts.append(Attempt("OpenAQ", True))
        except ProviderError as e:
            r.measured_status = "no_data" if e.kind == "no_data" else "unavailable"
            r.attempts.append(Attempt("OpenAQ", False, e.kind, e.status, e.public_message))
            log.info("air city=%s OpenAQ: %s %s", city, e.kind, e.detail)
    else:
        r.attempts.append(Attempt("OpenAQ", False, "not_configured", None, "OpenAQ not configured"))
    if s.open_meteo_enabled:
        try:
            r.modelled = fetch_open_meteo_air(c["lat"], c["lon"], pol, now)
            r.modelled_status = "available"
            r.attempts.append(Attempt("Open-Meteo air quality", True))
        except ProviderError as e:
            r.modelled_status = "unavailable"
            r.attempts.append(Attempt("Open-Meteo air quality", False, e.kind, e.status, e.public_message))
    return r


@dataclass
class HazardReport:
    city: str
    events: List[HazardEvent] = field(default_factory=list)
    usgs_status: str = "disabled"   # available | disabled | unavailable
    gdacs_status: str = "disabled"
    attempts: List[Attempt] = field(default_factory=list)
    fetched_at: Optional[datetime] = None

    @property
    def ok(self) -> bool:
        return "available" in (self.usgs_status, self.gdacs_status)

    @property
    def attributed(self) -> List[HazardEvent]:
        return [e for e in self.events if e.attributed]


def fetch_hazards(city: str, s: Settings, now: Optional[datetime] = None) -> HazardReport:
    r = HazardReport(city, fetched_at=datetime.now(timezone.utc))
    c = CITY_COORDINATES.get(city)
    if not c:
        return r
    pol = _policy(s)
    usgs: List[HazardEvent] = []
    gdacs: List[HazardEvent] = []
    if s.usgs_enabled:
        try:
            usgs = fetch_usgs(c["lat"], c["lon"], pol, now)
            r.usgs_status = "available"
            r.attempts.append(Attempt("USGS", True))
        except ProviderError as e:
            r.usgs_status = "unavailable"
            r.attempts.append(Attempt("USGS", False, e.kind, e.status, e.public_message))
    if s.gdacs_enabled:
        try:
            gdacs = fetch_gdacs(c["lat"], c["lon"], CITY_COUNTRIES.get(city, ""), pol, now)
            r.gdacs_status = "available"
            r.attempts.append(Attempt("GDACS", True))
        except ProviderError as e:
            r.gdacs_status = "unavailable"
            r.attempts.append(Attempt("GDACS", False, e.kind, e.status, e.public_message))
    r.events = sorted(dedupe_quakes(usgs, gdacs), key=lambda e: (e.severity, -e.when.timestamp()))
    return r
