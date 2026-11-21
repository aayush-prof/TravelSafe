"""
Traveller personas
==================

Personas adjust how *relevant* each risk category is to a traveller. They
never create risk: a category with no adverse signal stays at zero for every
persona (see ``scoring.apply_persona``).

Weights are exponents applied to the "no-risk" share of a category:

    persona_risk = 1 - (1 - base_risk) ** weight

* weight 1.0 -> unchanged
* weight > 1 -> the same evidence matters more to this traveller
* weight < 1 -> it matters less

The five original profiles are retained. Their weights were reviewed and
narrowed from the original range (0.8–1.8) to 0.85–1.5: with the old 1.8
crime weight, two street-crime reports moved a city from "Elevated" to
"High" for one profile, which is the persona manufacturing alarm rather than
re-weighting relevance. With the new range a profile shifts a category by at
most about one level (e.g. 0.35 -> 0.48 at weight 1.5). The old extra
"sensitivity offset", which lowered cautious personas' scores even without
relevant events, was removed. Weights are planning heuristics, not claims
about any group's actual victimisation risk.
"""

from __future__ import annotations

from typing import Dict, List

from .models import Persona

_PERSONAS: Dict[str, Persona] = {
    "student": Persona(
        name="student",
        display_name="Student",
        description="Budget travellers, often in hostels and on public transport.",
        weights={"crime": 1.15, "protest": 1.0, "accident": 0.9, "disaster": 1.0, "weather": 0.9, "environment": 1.0},
        rationale={
            "crime": "Shared accommodation and late public transport increase exposure to petty theft.",
            "accident": "Typically flexible about minor transport disruption.",
            "weather": "Usually able to adapt plans to weather.",
        },
    ),
    "solo_female": Persona(
        name="solo_female",
        display_name="Solo female",
        description="Women travelling alone who prioritise personal safety.",
        weights={"crime": 1.5, "protest": 1.2, "accident": 1.0, "disaster": 1.0, "weather": 0.95, "environment": 1.0},
        rationale={
            "crime": "Reports of harassment, snatching and street crime are weighted more heavily.",
            "protest": "Crowds and unrest are weighted more heavily.",
            "weather": "Weather is weighted slightly less.",
        },
    ),
    "family": Persona(
        name="family",
        display_name="Family",
        description="Travelling with children; needs predictable, low-disruption conditions.",
        weights={"crime": 1.3, "protest": 1.3, "accident": 1.2, "disaster": 1.3, "weather": 1.15, "environment": 1.3},
        rationale={
            "environment": "Children are more sensitive to air pollution.",
            "crime": "Higher priority on avoiding any incident with children present.",
            "protest": "Crowds and transport shutdowns are harder to navigate with children.",
            "accident": "Road and transport incidents are weighted more heavily.",
            "disaster": "Evacuation and disruption are harder for families.",
            "weather": "Children are more affected by heat, cold and heavy rain.",
        },
    ),
    "backpacker": Persona(
        name="backpacker",
        display_name="Backpacker",
        description="Flexible, outdoors-oriented travellers with higher tolerance for disruption.",
        weights={"crime": 1.0, "protest": 0.85, "accident": 0.95, "disaster": 1.15, "weather": 1.1, "environment": 1.1},
        rationale={
            "environment": "More time outdoors means more exposure to polluted air.",
            "protest": "Usually able to route around strikes and marches.",
            "disaster": "Outdoor and remote activities increase exposure to natural hazards.",
            "weather": "Outdoor plans are more weather-dependent.",
        },
    ),
    "elderly": Persona(
        name="elderly",
        display_name="Senior",
        description="Older travellers with health and mobility considerations.",
        weights={"crime": 1.15, "protest": 1.15, "accident": 1.25, "disaster": 1.4, "weather": 1.4, "environment": 1.4},
        rationale={
            "environment": "Poor air quality has a greater health impact for older adults.",
            "crime": "Slightly higher priority on avoiding street crime.",
            "protest": "Crowds are harder to move through.",
            "accident": "Transport incidents have greater health impact.",
            "disaster": "Evacuation and disruption carry greater health risk.",
            "weather": "Heat waves, cold and poor air quality have greater health impact.",
        },
    ),
}


def get_all_personas() -> Dict[str, Persona]:
    return dict(_PERSONAS)


def get_persona(name: str) -> Persona:
    if name not in _PERSONAS:
        raise KeyError(f"Persona '{name}' not found. Available: {list(_PERSONAS)}")
    return _PERSONAS[name]


def get_persona_names() -> List[str]:
    return list(_PERSONAS)
