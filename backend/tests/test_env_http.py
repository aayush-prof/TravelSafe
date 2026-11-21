"""Configuration loading (the v4 weather root cause), diagnostics that never
reveal secrets, HTTP retry policy and CORS."""

from __future__ import annotations

import dataclasses
import logging
import os
import time

import pytest
import requests
from fastapi.testclient import TestClient

import core.env as env
from core.config import settings
from core.http import HttpPolicy, ProviderError, get_json

from .provider_fixtures import FakeResp, Router

KEY = "0123456789abcdef0123456789abcdef"


@pytest.fixture
def project(tmp_path, monkeypatch):
    """A throw-away project layout: <tmp>/.env, <tmp>/backend/.env, <tmp>/frontend/."""
    (tmp_path / "backend").mkdir()
    (tmp_path / "frontend").mkdir()
    snapshot = dataclasses.asdict(settings)
    monkeypatch.setattr(env, "PROJECT_DIR", tmp_path)
    monkeypatch.setattr(env, "BACKEND_DIR", tmp_path / "backend")
    monkeypatch.setattr(env, "ENV_FILES", [tmp_path / ".env", tmp_path / "backend" / ".env"])
    monkeypatch.setattr(env, "_OS_ENV", {})
    yield tmp_path
    for k, v in snapshot.items():
        setattr(settings, k, v)


def codes():
    return {i["code"] for i in env.config_issues()}


def test_canonical_name(project):
    (project / "backend" / ".env").write_text(f"OPENWEATHER_API_KEY={KEY}\n")
    env.refresh_settings(force=True)
    assert settings.weather_configured and settings.openweather_key_name == "OPENWEATHER_API_KEY"
    assert codes() == set()


@pytest.mark.parametrize("name", ["OPENWEATHERMAP_API_KEY", "WEATHER_API_KEY", "OWM_API_KEY"])
def test_legacy_names_are_accepted_and_flagged(project, name):
    (project / "backend" / ".env").write_text(f"{name}={KEY}\n")
    env.refresh_settings(force=True)
    assert settings.weather_configured and settings.openweather_key_name == name
    assert "legacy_name" in codes()


def test_root_env_is_read_and_backend_wins(project):
    (project / ".env").write_text(f"OPENWEATHER_API_KEY={'1' * 32}\nOPENAQ_API_KEY=aq-root\n")
    (project / "backend" / ".env").write_text(f"OPENWEATHER_API_KEY={KEY}\n")
    env.refresh_settings(force=True)
    assert settings.openweather_api_key == KEY and settings.openaq_api_key == "aq-root"


def test_process_environment_wins(project, monkeypatch):
    (project / "backend" / ".env").write_text(f"OPENWEATHER_API_KEY={KEY}\n")
    monkeypatch.setattr(env, "_OS_ENV", {"OPENWEATHER_API_KEY": "f" * 32})
    env.refresh_settings(force=True)
    assert settings.openweather_api_key == "f" * 32


def test_env_txt_is_detected(project):
    (project / "backend" / ".env.txt").write_text(f"OPENWEATHER_API_KEY={KEY}\n")
    env.refresh_settings(force=True)
    assert not settings.weather_configured
    assert {"wrong_file_name", "no_env_file"} <= codes()


def test_key_in_frontend_is_detected(project):
    (project / "frontend" / ".env.local").write_text(f"OPENWEATHER_API_KEY={KEY}\nNEXT_PUBLIC_API_BASE=x\n")
    env.refresh_settings(force=True)
    assert not settings.weather_configured and "key_in_frontend" in codes()


@pytest.mark.parametrize("value", ["your_openweather_key_here", "<paste-key>", "changeme"])
def test_placeholder_is_not_used(project, value):
    (project / "backend" / ".env").write_text(f"OPENWEATHER_API_KEY={value}\n")
    env.refresh_settings(force=True)
    assert not settings.weather_configured and "placeholder" in codes()


def test_unexpected_shape_is_flagged(project):
    (project / "backend" / ".env").write_text("OPENWEATHER_API_KEY=abc123\n")
    env.refresh_settings(force=True)
    assert settings.weather_configured and "unexpected_shape" in codes()


def test_hot_reload_after_editing_env(project):
    f = project / "backend" / ".env"
    f.write_text("DATA_MODE=auto\n")
    env.refresh_settings(force=True)
    assert not settings.weather_configured
    assert env.refresh_settings() is False  # unchanged file: no reload
    f.write_text(f"DATA_MODE=auto\nOPENWEATHER_API_KEY={KEY}\n")
    os.utime(f, (time.time() + 5, time.time() + 5))
    assert env.refresh_settings() is True and settings.weather_configured


def test_middleware_reloads_on_request(project, monkeypatch):
    import importlib
    main = importlib.import_module("app.main")
    monkeypatch.setattr(main, "refresh_settings", env.refresh_settings)
    app = main.app
    f = project / "backend" / ".env"
    f.write_text("OPENAQ_API_KEY=\n")
    env.refresh_settings(force=True)
    f.write_text("OPENAQ_API_KEY=aq-new-key\n")
    os.utime(f, (time.time() + 5, time.time() + 5))
    d = TestClient(app).get("/api/diagnostics/providers").json()
    aq = next(p for p in d["providers"] if p["provider"] == "OpenAQ")
    assert aq["state"] == "configured" and aq["key_variable"] == "OPENAQ_API_KEY"


def test_diagnostics_never_return_values(project):
    from app.main import app
    (project / "backend" / ".env").write_text(f"OPENWEATHERMAP_API_KEY={KEY}\nOPENAQ_API_KEY=secret-aq-value\n")
    (project / "frontend" / ".env.local").write_text("NEWS_API_KEY=secret-news-value\n")
    env.refresh_settings(force=True)
    body = TestClient(app).get("/api/diagnostics/providers").text
    assert KEY not in body and "secret-aq-value" not in body and "secret-news-value" not in body
    assert "OPENWEATHERMAP_API_KEY" in body and "key_in_frontend" in body


def test_provider_test_endpoint_reports_error_class(monkeypatch):
    from app.main import app
    monkeypatch.setattr(settings, "openweather_api_key", KEY)
    monkeypatch.setattr(requests, "get", Router({"data/2.5/weather": FakeResp(401, {"cod": 401, "message": "Invalid API key"})}))
    r = TestClient(app).post("/api/diagnostics/providers/test?city=Pune")
    assert r.status_code == 200 and KEY not in r.text
    owm = next(x for x in r.json()["results"] if x["provider"] == "OpenWeatherMap")
    assert owm["ok"] is False and owm["kind"] == "unauthorized" and owm["http_status"] == 401


def test_key_is_not_logged(monkeypatch, caplog):
    from core.weather_service import fetch_weather
    monkeypatch.setattr(settings, "openweather_api_key", KEY)
    monkeypatch.setattr(requests, "get", Router({"data/2.5/weather": FakeResp(401, {"cod": 401})}))
    with caplog.at_level(logging.DEBUG):
        fetch_weather("Pune", settings)
    assert KEY not in caplog.text and "appid" not in caplog.text


# --- HTTP policy -------------------------------------------------------------

def test_backoff_grows_with_jitter_and_caps(monkeypatch):
    delays = []
    monkeypatch.setattr(requests, "get", Router({"x": FakeResp(503, {})}))
    with pytest.raises(ProviderError) as ei:
        get_json("P", "https://x/", policy=HttpPolicy(retries=4, backoff_base=0.5, backoff_cap=2.0),
                 sleep=delays.append)
    assert ei.value.kind == "unavailable" and len(delays) == 4
    assert 0.25 <= delays[0] <= 0.5 and 0.5 <= delays[1] <= 1.0 and all(d <= 2.0 for d in delays)


@pytest.mark.parametrize("status,kind", [(401, "unauthorized"), (403, "forbidden"), (404, "not_found"),
                                         (400, "bad_response")])
def test_permanent_errors_are_not_retried(monkeypatch, status, kind):
    r = Router({"x": FakeResp(status, {"message": "nope"})})
    monkeypatch.setattr(requests, "get", r)
    with pytest.raises(ProviderError) as ei:
        get_json("P", "https://x/", policy=HttpPolicy(retries=3), sleep=lambda s: None)
    assert ei.value.kind == kind and ei.value.status == status and r.count("x") == 1


def test_public_message_hides_detail():
    e = ProviderError("OpenWeatherMap", "unauthorized", 401, "Invalid API key 0123")
    assert "0123" not in e.public_message


# --- CORS ------------------------------------------------------------------------

def test_cors_allows_frontend_and_rejects_others():
    from app.main import app
    c = TestClient(app)
    ok = c.get("/api/health", headers={"Origin": "http://localhost:3000"})
    bad = c.get("/api/health", headers={"Origin": "https://evil.example"})
    assert ok.headers.get("access-control-allow-origin") == "http://localhost:3000"
    assert "access-control-allow-origin" not in bad.headers


def test_readiness():
    from app.main import app
    d = TestClient(app).get("/api/ready").json()
    assert d["ready"] is True and all(d["checks"].values())
