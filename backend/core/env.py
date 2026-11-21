"""
Environment settings with live reload and misconfiguration detection
=====================================================================

Why this module exists (v4 weather bug): settings were read once at import
from ``backend/.env``, only the names OPENWEATHER_API_KEY/WEATHER_API_KEY were
accepted, and ``uvicorn --reload`` does not restart on ``.env`` edits. A key
saved as ``OPENWEATHERMAP_API_KEY``, in ``.env.txt`` (Windows Notepad), in
``frontend/.env.local`` or added while the server was running was silently
ignored, and the UI could only say "not set up".

Now:
* values are read from the real environment first, then ``backend/.env``,
  then a project-root ``.env`` (a value in the real environment always wins;
  ``backend/.env`` wins over the root file);
* ``refresh_settings()`` re-reads the files whenever their modification time
  changes (called on every API request), updating the shared ``settings``
  object in place;
* ``config_issues()`` reports likely mistakes by file and variable name –
  never by value.
"""

from __future__ import annotations

import os
import re
import threading
from dataclasses import dataclass, field, fields
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from dotenv import dotenv_values

BACKEND_DIR = Path(__file__).resolve().parent.parent
PROJECT_DIR = BACKEND_DIR.parent
ENV_FILES = [PROJECT_DIR / ".env", BACKEND_DIR / ".env"]  # later files override earlier ones

# Snapshot of the real process environment (values set in the shell win).
_OS_ENV = {k: v for k, v in os.environ.items() if v.strip()}

# Canonical name first, then accepted legacy aliases.
KEY_NAMES: Dict[str, Tuple[str, ...]] = {
    "openweather": ("OPENWEATHER_API_KEY", "OPENWEATHERMAP_API_KEY", "WEATHER_API_KEY", "OWM_API_KEY"),
    "openaq": ("OPENAQ_API_KEY",),
    "newsapi": ("NEWS_API_KEY", "NEWSAPI_KEY"),
    "gnews": ("GNEWS_API_KEY",),
}
_PLACEHOLDER = re.compile(r"^(your[_-]|<|xxx|changeme|replace|insert|paste|api[_-]?key[_-]?here|none$|null$)", re.I)


def _read_files() -> Dict[str, str]:
    merged: Dict[str, str] = {}
    for path in ENV_FILES:
        if path.is_file():
            try:
                for k, v in dotenv_values(path).items():
                    if v is not None:
                        merged[k] = v
            except (OSError, UnicodeDecodeError):
                continue
    return merged


def _mtimes() -> Tuple[float, ...]:
    return tuple(p.stat().st_mtime if p.is_file() else 0.0 for p in ENV_FILES)


class _Source:
    def __init__(self) -> None:
        self.values: Dict[str, str] = _read_files()

    def raw(self, name: str) -> Optional[str]:
        if name in _OS_ENV:
            return _OS_ENV[name]
        return self.values.get(name)

    def key(self, kind: str) -> Tuple[str, Optional[str]]:
        """Return (usable value, variable name it came from)."""
        for name in KEY_NAMES[kind]:
            v = (self.raw(name) or "").strip().strip('"').strip("'").strip()
            if v and not _PLACEHOLDER.match(v):
                return v, name
        return "", None

    def text(self, name: str, default: str = "") -> str:
        v = self.raw(name)
        return v.strip() if v and v.strip() else default

    def flag(self, name: str, default: bool) -> bool:
        v = self.raw(name)
        if v is None or not v.strip():
            return default
        return v.strip().lower() in {"1", "true", "yes", "on"}

    def int(self, name: str, default: int) -> int:
        try:
            return int(self.text(name, str(default)))
        except ValueError:
            return default


@dataclass
class Settings:
    news_api_key: str = ""
    gnews_api_key: str = ""
    openweather_api_key: str = ""
    openweather_key_name: Optional[str] = None
    openaq_api_key: str = ""
    open_meteo_enabled: bool = True
    usgs_enabled: bool = True
    gdacs_enabled: bool = True
    data_mode: str = "auto"  # auto | live | sample
    enable_google_rss: bool = True
    news_fetch_limit: int = 30
    cache_ttl_seconds: int = 900
    failure_cache_ttl_seconds: int = 60
    stale_max_age_seconds: int = 6 * 3600
    request_timeout_seconds: float = 8.0
    connect_timeout_seconds: float = 4.0
    http_retries: int = 2
    cors_origins: List[str] = field(default_factory=list)
    sample_news_path: Path = BACKEND_DIR / "sample_data" / "sample_news.json"

    @property
    def news_providers(self) -> List[str]:
        providers = []
        if self.news_api_key:
            providers.append("NewsAPI")
        if self.gnews_api_key:
            providers.append("GNews")
        if self.enable_google_rss:
            providers.append("Google News RSS")
        return providers

    @property
    def weather_configured(self) -> bool:
        return bool(self.openweather_api_key)

    @property
    def any_weather_provider(self) -> bool:
        return self.weather_configured or self.open_meteo_enabled


def build_settings() -> Settings:
    src = _Source()
    data_mode = src.text("DATA_MODE").lower()
    if data_mode not in {"auto", "live", "sample"}:
        legacy = src.raw("USE_LIVE_NEWS")
        data_mode = "sample" if legacy is not None and not src.flag("USE_LIVE_NEWS", True) else "auto"
    origins = src.text("CORS_ORIGINS", src.text("FRONTEND_ORIGIN", "http://localhost:3000,http://127.0.0.1:3000"))
    ow_key, ow_name = src.key("openweather")
    return Settings(
        news_api_key=src.key("newsapi")[0],
        gnews_api_key=src.key("gnews")[0],
        openweather_api_key=ow_key,
        openweather_key_name=ow_name,
        openaq_api_key=src.key("openaq")[0],
        open_meteo_enabled=src.flag("OPEN_METEO_ENABLED", True),
        usgs_enabled=src.flag("USGS_ENABLED", True),
        gdacs_enabled=src.flag("GDACS_ENABLED", True),
        data_mode=data_mode,
        enable_google_rss=src.flag("ENABLE_GOOGLE_NEWS_RSS", True),
        news_fetch_limit=max(5, min(100, src.int("NEWS_FETCH_LIMIT", 30))),
        cache_ttl_seconds=max(0, src.int("CACHE_TTL_SECONDS", src.int("CACHE_TIMEOUT", 900))),
        http_retries=max(0, min(4, src.int("HTTP_RETRIES", 2))),
        cors_origins=[o.strip() for o in origins.split(",") if o.strip()],
    )


settings = build_settings()
_lock = threading.Lock()
_last_mtimes = _mtimes()


def refresh_settings(force: bool = False) -> bool:
    """Re-read .env files if they changed. Updates ``settings`` in place.
    Returns True when settings were reloaded."""
    global _last_mtimes
    now = _mtimes()
    if not force and now == _last_mtimes:
        return False
    with _lock:
        fresh = build_settings()
        for f in fields(Settings):
            setattr(settings, f.name, getattr(fresh, f.name))
        _last_mtimes = now
    return True


# ---------------------------------------------------------------------------
# Misconfiguration detection (names and files only – never values)
# ---------------------------------------------------------------------------

_OWM_KEY_SHAPE = re.compile(r"^[0-9a-f]{32}$")


def _scan_file_for_keys(path: Path) -> List[str]:
    try:
        vals = dotenv_values(path)
    except (OSError, UnicodeDecodeError):
        return []
    names = [n for kind in KEY_NAMES.values() for n in kind]
    return [k for k in vals if k in names and (vals.get(k) or "").strip()]


def config_issues() -> List[Dict[str, str]]:
    issues: List[Dict[str, str]] = []
    rel = lambda p: str(p.relative_to(PROJECT_DIR)).replace("\\", "/")  # noqa: E731
    if not any(p.is_file() for p in ENV_FILES) and not any(n in _OS_ENV for ks in KEY_NAMES.values() for n in ks):
        issues.append({"code": "no_env_file", "message": "No backend/.env file was found. Copy backend/.env.example to backend/.env and add your keys."})
    for folder in (BACKEND_DIR, PROJECT_DIR):
        for bad in (".env.txt", "env", ".env.example.txt", "env.txt"):
            p = folder / bad
            if p.is_file() and _scan_file_for_keys(p):
                issues.append({"code": "wrong_file_name",
                               "message": f"Found keys in {rel(p)}, which is not read. Rename it to .env "
                                          "(Windows may have added a hidden .txt extension)."})
    frontend = PROJECT_DIR / "frontend"
    for name in (".env", ".env.local", ".env.development", ".env.development.local"):
        p = frontend / name
        if p.is_file():
            keys = _scan_file_for_keys(p)
            if keys:
                issues.append({"code": "key_in_frontend",
                               "message": f"{', '.join(keys)} is set in frontend/{name}. API keys belong in "
                                          "backend/.env; the frontend never uses them."})
    src = _Source()
    for kind, names in KEY_NAMES.items():
        for n in names:
            raw = src.raw(n)
            if raw is None or not raw.strip():
                continue
            v = raw.strip()
            if _PLACEHOLDER.match(v.strip("'\"")):
                issues.append({"code": "placeholder", "message": f"{n} still contains placeholder text."})
            elif v != raw or v[:1] in "'\"":
                issues.append({"code": "whitespace", "message": f"{n} has extra spaces or quotes around it (they are ignored)."})
            if kind == "openweather" and not _OWM_KEY_SHAPE.match(v.strip("'\" ")) and not _PLACEHOLDER.match(v):
                issues.append({"code": "unexpected_shape",
                               "message": f"{n} doesn't look like an OpenWeatherMap key (32 letters and digits). "
                                          "Copy it again from your OpenWeatherMap account page."})
    if settings.openweather_key_name and settings.openweather_key_name != "OPENWEATHER_API_KEY":
        issues.append({"code": "legacy_name",
                       "message": f"The weather key was read from {settings.openweather_key_name}. "
                                  "It works, but OPENWEATHER_API_KEY is the recommended name."})
    return issues


def key_variable(kind: str) -> Optional[str]:
    """Name (never the value) of the variable that supplied a key, or None."""
    return _Source().key(kind)[1]


def env_files_found() -> List[str]:
    """Which .env files exist, as project-relative paths."""
    return [str(p.relative_to(PROJECT_DIR)).replace("\\", "/") for p in ENV_FILES if p.is_file()]
