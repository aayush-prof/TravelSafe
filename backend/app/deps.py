"""Shared request validation."""

from __future__ import annotations

from fastapi import HTTPException, Path, Query

from core.config import DEFAULT_PERSONA, resolve_city
from core.personas import get_persona_names


def valid_city(city: str = Path(..., description="City name, alias or slug, e.g. 'new-york'")) -> str:
    resolved = resolve_city(city)
    if resolved is None:
        raise HTTPException(status_code=404, detail=f"Unsupported city: {city[:60]}")
    return resolved


def valid_persona(persona: str = Query(DEFAULT_PERSONA, description="Traveller profile id")) -> str:
    if persona not in get_persona_names():
        raise HTTPException(status_code=422, detail=f"Unknown persona '{persona[:40]}'. "
                            f"Use one of: {', '.join(get_persona_names())}")
    return persona
