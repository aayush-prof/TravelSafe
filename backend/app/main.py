"""
TravelSafe API
==============

Run from the ``backend`` directory::

    uvicorn app.main:app --reload --port 8000

Interactive docs: http://127.0.0.1:8000/docs
"""

from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from core.cache import cache
from core.config import APP_VERSION, config_issues, refresh_settings, settings
from core.logging_setup import configure_logging, get_logger

from .routers import city, meta, report

configure_logging(logging.INFO)
log = get_logger("api")

app = FastAPI(
    title="TravelSafe API",
    version=APP_VERSION,
    description=(
        "City travel-conditions assessment from news, weather, air-quality and natural-hazard data. Scores are "
        "heuristic, explainable indications for trip research – not crime rates and not guarantees of safety."
    ),
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)


@app.middleware("http")
async def reload_env(request: Request, call_next):
    # Pick up edits to .env without a restart (uvicorn --reload ignores .env files).
    if refresh_settings():
        cache.clear()
        log.info("Configuration changed; settings reloaded and cached results cleared "
                 "(weather=%s, OpenAQ=%s).", "configured" if settings.weather_configured else "not configured",
                 "configured" if settings.openaq_api_key else "not configured")
    return await call_next(request)


@app.exception_handler(Exception)
async def unhandled(request: Request, exc: Exception) -> JSONResponse:
    # Log the full error server-side; return a generic message (no stack traces or secrets).
    log.exception("Unhandled error on %s %s", request.method, request.url.path)
    return JSONResponse(status_code=500, content={"detail": "Internal server error. See backend logs."})


app.include_router(meta.router)
app.include_router(city.router)
app.include_router(report.router)


@app.get("/", include_in_schema=False)
def root() -> dict:
    return {"name": "TravelSafe API", "version": APP_VERSION, "docs": "/docs", "health": "/api/health"}


log.info("TravelSafe API %s starting (data_mode=%s, news=%s, OpenWeatherMap=%s%s, Open-Meteo=%s, OpenAQ=%s)",
         APP_VERSION, settings.data_mode, settings.news_providers or "none",
         "configured" if settings.weather_configured else "not configured",
         f" via {settings.openweather_key_name}" if settings.openweather_key_name else "",
         "on" if settings.open_meteo_enabled else "off",
         "configured" if settings.openaq_api_key else "not configured")
for _issue in config_issues():
    log.warning("Configuration: %s", _issue["message"])
