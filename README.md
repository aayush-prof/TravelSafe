# TravelSafe

TravelSafe is a travel-conditions dashboard for 45 cities in India and worldwide. For a city and a traveller profile it checks six factors separately (crime and security, civil disruption, transport disruption, natural hazards, weather and air quality), shows the evidence behind each one, and says plainly when something couldn't be checked. It is an evidence summary for trip research, **not** a safety guarantee, a crime rate or an official advisory.

- **Backend:** Python 3.10+ · FastAPI · Pydantic v2 · ReportLab (`backend/`)
- **Frontend:** Next.js 16 (App Router) · React 19 · TypeScript (strict) · Tailwind CSS 4 · shadcn/ui · Recharts · Lucide (`frontend/`)
- **Data:** OpenWeatherMap, Open-Meteo, OpenAQ, USGS, GDACS, Google News RSS / NewsAPI / GNews, Wikipedia / Wikidata. Details in [`docs/DATA_SOURCES.md`](docs/DATA_SOURCES.md).

What changed in this version and why (including the root cause of the broken weather) is in [`IMPLEMENTATION_NOTES.md`](IMPLEMENTATION_NOTES.md). Test evidence is in [`TEST_RESULTS.md`](TEST_RESULTS.md).

---

## Run it locally on Windows (PowerShell)

Prerequisites: **Python 3.10–3.13** (`py --version`) and **Node.js 20.9+**, Node 22 LTS recommended (`node --version`).

Unzip so you have a `TravelSafe` folder containing `backend` and `frontend`.

### Terminal 1: backend

```powershell
cd TravelSafe\backend
py -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
notepad .env
uvicorn app.main:app --reload --reload-include .env --host 127.0.0.1 --port 8000
```

In Notepad, paste your keys after the `=` signs (no quotes, no spaces), for example `OPENWEATHER_API_KEY=0123abcd...`, and save. Every key is optional; see [Environment variables](#environment-variables). Edits to `.env` are picked up on the next request, without a restart.

### Terminal 2: frontend

```powershell
cd TravelSafe\frontend
npm install
npm run dev
```

Open:

- App: **http://localhost:3000**
- API: **http://127.0.0.1:8000** (health: `/api/health`, readiness: `/api/ready`)
- API docs (Swagger): **http://127.0.0.1:8000/docs**

No `frontend/.env.local` is needed when the backend runs on `127.0.0.1:8000`.

### Check your weather key in 30 seconds

1. Open http://127.0.0.1:8000/docs.
2. Run **GET /api/diagnostics/providers**. It shows which providers are configured, the *name* of the variable that supplied each key (never its value), and configuration problems such as a `.env.txt` file or a key placed in the frontend.
3. Run **POST /api/diagnostics/providers/test** with `city=Delhi`. It makes one real request per provider and reports the outcome, e.g. `OpenWeatherMap ok=false kind=unauthorized http_status=401` (key rejected or not yet active). This endpoint only answers requests from the machine running the backend.

### Production build (optional)

```powershell
cd TravelSafe\frontend
npm run build
npm run start
```

### macOS / Linux

```bash
cd TravelSafe/backend && python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt && cp .env.example .env
uvicorn app.main:app --reload --reload-include .env --host 127.0.0.1 --port 8000
# second terminal
cd TravelSafe/frontend && npm install && npm run dev
```

---

## Environment variables

All keys go in **`backend/.env`** (a project-root `.env` is also read; `backend/.env` wins; real environment variables win over both). **Never put keys in `frontend/.env.local`**: the frontend never needs them and the browser must never see them.

| Variable | Needed? | What it does |
|---|---|---|
| `OPENWEATHER_API_KEY` | Optional | OpenWeatherMap current weather + forecast. Legacy names `OPENWEATHERMAP_API_KEY`, `WEATHER_API_KEY`, `OWM_API_KEY` are accepted and flagged. Official alerts additionally need a One Call 3.0 subscription. |
| `OPEN_METEO_ENABLED` | Default `true` | Keyless weather fallback and modelled (context-only) air quality. |
| `OPENAQ_API_KEY` | Optional (free) | Measured air quality from monitoring stations. Without it, air quality is "not assessed", never "clean". |
| `USGS_ENABLED`, `GDACS_ENABLED` | Default `true` | Earthquakes and disaster alerts (no keys). |
| `NEWS_API_KEY`, `GNEWS_API_KEY` | Optional | Extra news providers. |
| `ENABLE_GOOGLE_NEWS_RSS` | Default `true` | Keyless news feed. |
| `DATA_MODE` | Default `auto` | `auto`: live, labelled sample headlines if all news fails. `live`: never sample. `sample`: offline demo. |
| `CACHE_TTL_SECONDS` | Default `900` | Cache for successful results (weather is capped at 15 min; failures retry after 60 s). |
| `HTTP_RETRIES` | Default `2` | Retries for timeouts, 429 and 5xx only. |
| `CORS_ORIGINS` | Default `http://localhost:3000,http://127.0.0.1:3000` | Browser origins allowed to call the API. |
| `NEXT_PUBLIC_API_BASE_URL` (frontend) | Only if the backend isn't on `127.0.0.1:8000` | Address used for report downloads. Not a secret. |

---

## Using the app

- **Top bar:** search for a city (press `/` or Ctrl+K), choose the traveller profile, **Refresh** to fetch fresh data (shows progress and the result), and see when data was last updated.
- **Overview:** active alerts banner; four summary cards (overall assessment, data coverage, active alerts, last updated); the **factor risk profile** (expand any factor for evidence, sources, time window, geographic match and freshness; switch between general and profile weighting); what drives the result; incidents over time (only when there are at least 5 incidents over 3 days); recent events; conditions now; source status; precautions.
- **Events:** search and filter by topic, severity, period and status; expandable details explain how each report was treated.
- **Crime watch:** crime and security news (clearly *not* crime statistics), types and weekly counts when there is enough data.
- **Weather:** current conditions, metric row, 48-hour temperature and precipitation charts in the city's local time, 7-day outlook, a separate official-alerts area, the source and its freshness. If no provider works, a plain explanation and **Try again**, and the weather factor is "not assessed", never "Low".
- **Air & hazards:** measured air quality with station distance and 72-hour PM2.5 trend; modelled estimate as context; earthquakes and disaster alerts near the city, with regional events listed separately.
- **City insights:** Wikipedia/Wikidata summary, facts, climate (long-term context, never current weather), transport, emergency numbers, profile tips.
- **Reports:** a preview and a PDF or printable HTML briefing built from the same API response.
- **How it works:** method, factors and weights, levels, data sources, limits and formulas.

Every chart has a **Show table** option, tooltips, units and an honest empty state.

---

## How the assessment works

Full details are on the **How it works** page and at `GET /api/methodology`.

1. **News factors** (crime, civil, transport; also feeding hazards and weather): each report is classified with a severity (−3…+3) and a separate confidence; reports that don't name the city are down-weighted or excluded; repeated coverage is merged into one incident; older reports fade (half-lives 2–14 days). Impacts combine as `P = max + min(2.5, 1.5·ln(1+Σrest))`, `R = 1 − exp(−P/8)`.
2. **Natural hazards:** USGS earthquakes (M ≥ 4 within 500 km, last 7 days; severity by magnitude × distance) and GDACS alerts within a hazard-specific radius (100–600 km), plus news. A news report of an event already in the feeds is not counted twice.
3. **Weather:** measured conditions and the 48-hour forecast (heat, very heavy rain using IMD rainfall bands, gales, poor visibility, storms) from OpenWeatherMap or Open-Meteo; weather news corroborates at half weight.
4. **Air quality:** OpenAQ station measurements only; the US EPA category of the latest hourly value, labelled *indicative*. Modelled values never change the result.
5. **Unknown is never low.** A factor without a working source is "not assessed" and shown hatched.
6. **Overall:** `a_f = relevance_f × R_f` (crime 1.0, hazards 1.0, civil 0.8, weather 0.8, transport 0.6, air 0.6); `R = a₁ + (1 − a₁)·0.35·(1 − Π(1 − a_rest))`. Levels: Low < 0.15 ≤ Guarded < 0.35 ≤ Elevated < 0.60 ≤ High.
7. **Critical alerts are never averaged away:** GDACS red → at least High; GDACS orange, USGS PAGER orange/red, a severe nearby earthquake or a credible severe incident (< 72 h) → at least Elevated; any official weather alert → at least Guarded (weather factor ≥ Elevated). They also appear in a banner.
8. **Index** (−10 to +10, an evidence summary, not a probability): `10 − 20R`; a favourable value is multiplied by the coverage factor (good 1.0, limited 0.5) **and** by the share of factor weight actually assessed.
9. **Coverage:** *insufficient* when less than 35 % of the factor weight could be assessed; *good* when ≥ 80 %, news coverage is good, live weather works and nothing is stale; otherwise *limited*. Sample data is capped at limited. A low result with less than good coverage reads "No major concerns in the available sources".
10. **Traveller profiles** reweigh existing evidence (`R' = 1 − (1 − R)^w`); they never add risk where there is none.

Weights and thresholds are reasoned defaults, not calibrated probabilities.

---

## API

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/health`, `/api/ready` | Liveness and readiness |
| GET | `/api/cities` | Cities and traveller profiles |
| GET | `/api/cities/{city}/overview?persona=` | Full assessment (factors, alerts, coverage, sources, timeline) |
| GET | `/api/cities/{city}/events` | Filterable, paginated events |
| GET | `/api/cities/{city}/weather` | Current, hourly, daily, alerts, provider and freshness |
| GET | `/api/cities/{city}/air-quality` | Measured and modelled air quality |
| GET | `/api/cities/{city}/disasters` | USGS/GDACS events near the city and regional context |
| GET | `/api/cities/{city}/crime` | Crime watch |
| GET | `/api/cities/{city}/insights` | City information |
| GET | `/api/cities/{city}/coverage` | Source-by-source coverage |
| POST | `/api/cities/{city}/refresh` | Clear cached data for the city |
| GET | `/api/cities/{city}/report?persona=&format=pdf\|html` | Travel briefing |
| GET | `/api/methodology` | Method, formulas, parameters |
| GET | `/api/diagnostics/providers` | Configuration status (names only, never values) |
| POST | `/api/diagnostics/providers/test?city=` | Live provider check (local requests only) |

Source states used everywhere: `available`, `stale`, `broader_region`, `no_data`, `unavailable`, `not_configured`, `not_applicable`, `sample`.

---

## Tests

```powershell
cd TravelSafe\backend
.\.venv\Scripts\Activate.ps1
pip install -r requirements-dev.txt
python -m pytest -q

cd ..\frontend
npm run lint
npm run typecheck
npm run build
```

The backend tests use fixed clocks and mocked HTTP in each provider's documented response format; no network is needed. See [`TEST_RESULTS.md`](TEST_RESULTS.md).

---

## Troubleshooting

- **`Activate.ps1 cannot be loaded because running scripts is disabled`**: run `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` once (answer `Y`), or activate with `.\.venv\Scripts\activate.bat` from Command Prompt.
- **`py` not found**: use `python` instead, or install Python from python.org with "Add to PATH" ticked.
- **Weather says it isn't set up although you have a key:** open `/api/diagnostics/providers`. Typical causes it reports: the file is `.env.txt` (Windows hides extensions; in Explorer enable *View → File name extensions* and rename to `.env`), the key is in `frontend\.env.local`, the value is still a placeholder, or a legacy variable name.
- **Weather service rejected the key (401):** new OpenWeatherMap keys can take a while to activate. Meanwhile the app uses Open-Meteo automatically. Re-test later with `POST /api/diagnostics/providers/test`.
- **Official alerts "not set up":** alerts need OpenWeatherMap's One Call 3.0 subscription; the free plan covers current weather and forecast only. Check your national weather service (IMD in India).
- **Port already in use:** find the process with `netstat -ano | findstr :8000` and stop it (`taskkill /PID <pid> /F`), or run the backend on `--port 8001` and create `frontend\.env.local` with `NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:8001` and `API_BASE_URL=http://127.0.0.1:8001`. For the frontend use `npm run dev -- --port 3001` and add `http://localhost:3001` to `CORS_ORIGINS`.
- **"The TravelSafe service isn't responding"** in the app: the backend isn't running, or is on another address. Check http://127.0.0.1:8000/api/health.
- **CORS error on report download:** add the exact frontend origin to `CORS_ORIGINS` in `backend\.env` and restart the backend.
- **Quotas:** OpenWeatherMap free plan 60 calls/min; Open-Meteo ~10 000/day non-commercial; OpenAQ rate-limited per key; NewsAPI/GNews developer tiers are limited. Results are cached for 15–30 minutes to stay well inside these.
- **Everything shows sample data:** every news provider failed; check internet access and `backend\logs\`.

---

## Project structure

```
TravelSafe/
├─ backend/
│  ├─ app/            FastAPI app, routers, Pydantic schemas, serializers
│  ├─ core/
│  │  ├─ env.py               settings, .env loading, hot reload, config checks
│  │  ├─ http.py              timeouts, retries with backoff + jitter, error mapping
│  │  ├─ providers/           weather.py, air.py, disasters.py (provider adapters)
│  │  ├─ weather_service.py   OpenWeatherMap → Open-Meteo fallback, conditions
│  │  ├─ environment_service.py  air quality and hazard feeds
│  │  ├─ news_client.py, classifier.py, location.py, dedup.py, scoring.py  news pipeline
│  │  ├─ factors.py           multi-factor model, critical alerts, timeline
│  │  ├─ coverage.py          source states, overall coverage
│  │  ├─ pipeline.py          caching, stale fallback, analysis
│  │  └─ reports.py           PDF/HTML briefing
│  ├─ sample_data/    labelled synthetic headlines (5 cities)
│  └─ tests/          pytest suite and provider fixtures
├─ frontend/
│  ├─ app/            pages: /, events, crime, weather, environment, insights, reports, how-it-works
│  ├─ components/     ui/ (shadcn), shell/, charts/, factors/, events/, common/
│  └─ lib/            API client (server-only), types, formatting
└─ docs/DATA_SOURCES.md
```

---

## Known limitations

- No live provider could be reached from the environment this version was built in, so integrations are verified against documented response formats. Use the diagnostics endpoints to confirm live access on your machine.
- IMD official warnings are not integrated (access terms and schemas unverified); official alerts come from OpenWeatherMap One Call 3.0 where subscribed.
- News coverage is not incidence, keyword classification can misread unusual phrasing, and cities are not directly comparable when coverage differs.
- Air-quality categories are indicative (latest hourly value, not the 24-hour average used for official AQI).
- The cache is in-memory, per process.

## Disclaimer and licence

Created as an educational college mini-project. TravelSafe summarises signals in news, weather, air-quality and hazard data. It is not a guarantee of personal safety, not a crime rate and not an official advisory. Always consult official travel advisories and local authorities. News content belongs to its publishers and is linked, not republished. Weather data by OpenWeather and Open-Meteo.com (CC BY 4.0); air-quality measurements via OpenAQ; earthquake data from the USGS; disaster alerts from GDACS; city information from Wikipedia (CC BY-SA 4.0) and Wikidata (CC0).
