"""
Geospatial disaster feeds
=========================

USGS FDSN event service (no key) – earthquakes within 500 km over the last
7 days, magnitude ≥ 4. Relevance depends on magnitude *and* distance:

    M ≥ 4.5 within 100 km, M ≥ 5.5 within 250 km, M ≥ 6.5 within 500 km

GDACS (no key; EC-JRC / UN OCHA) – global disaster alerts (earthquakes,
tropical cyclones, floods, volcanoes, wildfires, droughts) from the last
14 days. An event is attributed to the city only when its reported location
is within a hazard-specific radius:

    EQ 300 km, TC 600 km, FL 150 km, VO 150 km, WF 100 km

Droughts and events outside the radius are kept as *context* ("in the
country/region, not attributed to the city") and never raise the score.
GDACS answers HTTP 404 for an empty search window; that is treated as
"no events", not as an error.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, List, Optional

from ..geo import haversine_km
from ..http import HttpPolicy, ProviderError, get_json

USGS = "https://earthquake.usgs.gov/fdsnws/event/1/query"
GDACS = "https://www.gdacs.org/gdacsapi/api/events/geteventlist/SEARCH"
USGS_ATTRIBUTION = "Earthquake data: U.S. Geological Survey (earthquake.usgs.gov)"
GDACS_ATTRIBUTION = "Disaster alerts: GDACS, a cooperation of the UN and the European Commission (gdacs.org)"

GDACS_TYPES = {"EQ": "Earthquake", "TC": "Tropical cyclone", "FL": "Flood", "VO": "Volcano",
               "WF": "Wildfire", "DR": "Drought"}
GDACS_RADIUS_KM = {"EQ": 300, "TC": 600, "FL": 150, "VO": 150, "WF": 100}


@dataclass
class HazardEvent:
    source: str            # "USGS" | "GDACS"
    hazard: str            # Earthquake, Tropical cyclone, ...
    title: str
    when: datetime
    distance_km: Optional[float]
    severity: int          # -1 minor, -2 serious, -3 severe (0 = context only)
    alert_level: Optional[str]  # GDACS Green/Orange/Red, USGS PAGER colour
    attributed: bool       # within the hazard's radius of the city
    relevance: str         # plain-language reason
    url: Optional[str]
    magnitude: Optional[float] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None


def usgs_relevance(mag: float, dist: float) -> int:
    if mag >= 6.5 and dist <= 250:
        return -3
    if (mag >= 6.5 and dist <= 500) or (mag >= 5.5 and dist <= 150):
        return -2
    if (mag >= 5.5 and dist <= 250) or (mag >= 4.5 and dist <= 100):
        return -1
    return 0


def fetch_usgs(lat: float, lon: float, policy: HttpPolicy, now: Optional[datetime] = None) -> List[HazardEvent]:
    now = now or datetime.now(timezone.utc)
    d = get_json("USGS", USGS, params={
        "format": "geojson", "latitude": round(lat, 4), "longitude": round(lon, 4), "maxradiuskm": 500,
        "starttime": (now - timedelta(days=7)).strftime("%Y-%m-%dT%H:%M:%S"), "minmagnitude": 4,
        "orderby": "time", "limit": 50}, policy=policy)
    feats = d.get("features") if isinstance(d, dict) else None
    if not isinstance(feats, list):
        raise ProviderError("USGS", "bad_response", detail="no features list")
    out = []
    for f in feats:
        pr = f.get("properties") or {}
        coords = (f.get("geometry") or {}).get("coordinates") or []
        try:
            mag = float(pr.get("mag"))
            elon, elat = float(coords[0]), float(coords[1])
            when = datetime.fromtimestamp(int(pr.get("time")) / 1000, tz=timezone.utc)
        except (TypeError, ValueError, IndexError):
            continue
        dist = haversine_km(lat, lon, elat, elon)
        sev = usgs_relevance(mag, dist)
        reason = (f"Magnitude {mag:.1f}, {dist:.0f} km away"
                  + ("" if sev else " (too small or too far to affect the city)"))
        out.append(HazardEvent("USGS", "Earthquake", str(pr.get("title") or pr.get("place") or "Earthquake"),
                               when, round(dist), sev, pr.get("alert"), sev < 0, reason, pr.get("url"),
                               mag, elat, elon))
    return out


def _gdacs_time(v: Any) -> Optional[datetime]:
    if not isinstance(v, str):
        return None
    try:
        dt = datetime.fromisoformat(v.replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def fetch_gdacs(lat: float, lon: float, country: str, policy: HttpPolicy, now: Optional[datetime] = None) -> List[HazardEvent]:
    now = now or datetime.now(timezone.utc)
    try:
        d = get_json("GDACS", GDACS, params={
            "eventlist": "EQ;TC;FL;VO;WF;DR", "alertlevel": "green;orange;red",
            "fromdate": (now - timedelta(days=14)).strftime("%Y-%m-%d"),
            "todate": now.strftime("%Y-%m-%d")}, policy=policy)
    except ProviderError as e:
        if e.kind == "not_found":  # GDACS uses 404 for "no events in this window"
            return []
        raise
    feats = d.get("features") if isinstance(d, dict) else None
    if not isinstance(feats, list):
        raise ProviderError("GDACS", "bad_response", detail="no features list")
    out = []
    for f in feats:
        pr = f.get("properties") or {}
        etype = str(pr.get("eventtype") or "")
        if etype not in GDACS_TYPES:
            continue
        coords = (f.get("geometry") or {}).get("coordinates") or []
        try:
            elon, elat = float(coords[0]), float(coords[1])
        except (TypeError, ValueError, IndexError):
            continue
        when = _gdacs_time(pr.get("todate")) or _gdacs_time(pr.get("fromdate"))
        if when is None or now - when > timedelta(days=14):
            continue
        dist = haversine_km(lat, lon, elat, elon)
        level = str(pr.get("alertlevel") or "").capitalize() or None
        radius = GDACS_RADIUS_KM.get(etype)
        in_country = country.lower() in str(pr.get("country") or "").lower()
        attributed = radius is not None and dist <= radius
        if not attributed and not (in_country or dist <= 1500):
            continue  # unrelated event elsewhere in the world
        sev = {"Red": -3, "Orange": -2, "Green": -1}.get(level or "", -1) if attributed else 0
        if attributed:
            reason = f"{level or 'Unrated'} alert, about {dist:.0f} km from the city"
        elif radius is None:
            reason = "Country or regional event; not attributed to the city"
        else:
            reason = f"About {dist:.0f} km away, outside the {radius} km range used for this hazard"
        url = (pr.get("url") or {}).get("report") if isinstance(pr.get("url"), dict) else None
        name = str(pr.get("name") or pr.get("description") or GDACS_TYPES[etype])
        out.append(HazardEvent("GDACS", GDACS_TYPES[etype], name, when, round(dist), sev, level, attributed,
                               reason, url, None, elat, elon))
    return out


def dedupe_quakes(usgs: List[HazardEvent], gdacs: List[HazardEvent]) -> List[HazardEvent]:
    """The same earthquake appears in USGS and GDACS. Keep the USGS record
    (precise magnitude) and carry over the GDACS alert level."""
    kept_g = []
    for g in gdacs:
        if g.hazard != "Earthquake":
            kept_g.append(g)
            continue
        twin = next((u for u in usgs if abs((u.when - g.when).total_seconds()) < 6 * 3600
                     and u.latitude is not None and g.latitude is not None
                     and haversine_km(u.latitude, u.longitude, g.latitude, g.longitude) < 100), None)
        if twin is None:
            kept_g.append(g)
        else:
            twin.alert_level = g.alert_level or twin.alert_level
            if g.severity < twin.severity:
                twin.severity, twin.attributed = g.severity, True
    return usgs + kept_g
