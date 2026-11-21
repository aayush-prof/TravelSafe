# Data sources

Every provider is optional except where noted; the app starts and degrades honestly if any key is missing. Terms and limits below are from each provider's public documentation as researched for this build (Nov 2026). **Re-check them before any commercial use.** No provider could be called from the build sandbox (its network allowlist blocks them), so integrations are tested against responses in each provider's documented format; verify live access with `POST /api/diagnostics/providers/test`.

## Implemented

| Provider | Data category | Geographic coverage | Resolution | Freshness | Auth | Free tier / limits | Attribution / licence | Contribution to assessment | Fallback | Limitations |
|---|---|---|---|---|---|---|---|---|---|---|
| **OpenWeatherMap** `/data/2.5/weather`, `/data/2.5/forecast` | Current weather, 5-day / 3-hour forecast | Global | Point (city coordinates) | Current ~10 min; forecast 3 h steps | `appid` key (`OPENWEATHER_API_KEY`) | Free plan includes both endpoints; 60 calls/min. New keys can take time to activate (HTTP 401 until then) | "Weather data by OpenWeather" | Weather factor: measured conditions + 48 h forecast hazards | Open-Meteo | City-name geocoding deprecated, so coordinates are always used |
| **OpenWeatherMap One Call 3.0** `/data/3.0/onecall` (alerts only) | Official national weather alerts | Global, where national services publish | Point | As issued | Same key + separate One Call subscription | Not included in the free plan; separate "One Call by Call" subscription | Issuing agency named in each alert | Any alert → critical banner, weather factor ≥ Elevated, overall ≥ Guarded | None. Without it the UI says alerts were **not checked** (never "none") | 401 without the subscription |
| **Open-Meteo Forecast** `api.open-meteo.com/v1/forecast` | Current, hourly (48 h), daily (7 d) | Global | ~1–11 km model grid | Hourly model updates | None | Free for non-commercial use, ~10 000 calls/day | CC BY 4.0: "Weather data by Open-Meteo.com" | Weather factor when OpenWeatherMap is missing or failing | — | Model output, not an official warning |
| **Open-Meteo Air Quality** `air-quality-api.open-meteo.com/v1/air-quality` | Modelled PM2.5, PM10, US AQI | Global | ~45 km (CAMS global) | Hourly | None | As above | CC BY 4.0, CAMS | **Context only, never scored** | — | Can't resolve local hot spots |
| **OpenAQ v3** `/v3/locations`, `/v3/locations/{id}/latest`, `/v3/sensors/{id}/hours` | Measured PM2.5 / PM10 (station) | Global where stations report | Station within 25 km; distance shown | Hourly; readings older than 48 h ignored | `X-API-Key` (`OPENAQ_API_KEY`), free | Rate-limited per key (60/min, 2 000/h at time of writing) | Data from station operators via OpenAQ | Air-quality factor: US EPA (2024) category of the latest hourly value, labelled *indicative* | None. No station → "not assessed", never "clean" | Not every city has stations; v1/v2 retired |
| **USGS FDSN Event** `earthquake.usgs.gov/fdsnws/event/1/query` | Earthquakes | Global | Epicentre point | Minutes | None | Public | U.S. Geological Survey (public domain) | Natural hazards: M ≥ 4.0 within 500 km, last 7 days; severity from magnitude × distance; PAGER red/orange → critical | GDACS, news | Distance from centre ≠ shaking intensity |
| **GDACS** `gdacsapi/api/events/geteventlist/SEARCH` | Earthquake, cyclone, flood, volcano, wildfire, drought alerts | Global | Event point; hazard radius 100–600 km | Minutes–hours | None | Public | GDACS (UN / European Commission) | Natural hazards: events inside a hazard-specific radius; Red → overall ≥ High, Orange → ≥ Elevated | USGS, news | Country-wide events (droughts) and distant events are listed as context only |
| **Google News RSS** | News reports | Global | City name in report | Minutes | None | Unofficial feed; may be rate-limited | Publisher named per item | Crime, civil, transport, hazards, weather (news) | NewsAPI, GNews, labelled sample data | Coverage ≠ incidence |
| **NewsAPI**, **GNews** | News reports | Global | City name | Minutes–hours | Keys (`NEWS_API_KEY`, `GNEWS_API_KEY`) | Developer tiers are limited and non-commercial | Publisher named | As above | Google News RSS | Free tiers delay or truncate results |
| **Wikipedia / Wikidata** | City description, climate text, facts | Global | City | Edited continuously | None | Public APIs | CC BY-SA 4.0 / CC0 | **Context only** (City insights) | — | Climate text is long-term context, never current weather |

## Researched, not integrated

| Provider | Why not (yet) |
|---|---|
| **IMD API** (api.imd.gov.in) | The public reference lists city forecast, current weather, district nowcast and warning endpoints but publishes no anonymous-access terms; access is granted on registration and response schemas couldn't be verified. Shipping an unverified parser for *official warnings* would risk misreporting them. The provider layer (`core/providers/`) is ready for an adapter once access is granted. |
| **Geoapify** | All 45 supported cities already have validated coordinates and time zones; POIs would be context only. |
| **IQAir** | Community plan restricts pollutant concentrations and forecasts; OpenAQ gives measurements with station metadata. |
| **ReliefWeb** | Needs an approved `appname`; country-level reports would not change a city assessment. |
| **World Bank, data.gov.in** | National / annual indicators; the brief rules them out as current city signals. |
| **OpenStreetMap / Overpass** | POI density isn't a safety signal; public instances are rate-limited. |

## Location-match classes used

`exact` (city coordinates or name in report) · `within radius` (stations ≤ 25 km; hazards inside their radius, distance shown) · `broader region` (Open-Meteo air-quality grid; stations > 10 km) · `country / region` (GDACS context events, never scored) · `unknown` (excluded).
