"""
Travel tips and do/don't planner
================================

Ported from the Streamlit City Insights page. Changes:

* Items are triggered by a category's *assessed level* (guarded or higher),
  not by the mere existence of one article in that category.
* Emoji prefixes were removed (the UI uses an icon system).
"""

from __future__ import annotations

from typing import Dict, List

PERSONA_TIPS: Dict[str, Dict[str, object]] = {
    "student": {
        "priority": "Budget-friendly, flexible travel",
        "tips": [
            "Carry your student ID for discounts at museums and attractions.",
            "Prefer well-reviewed hostels or budget hotels in central areas.",
            "Use public transport, and keep your phone and wallet in front pockets in crowds.",
            "Download offline maps and a translation app.",
            "Free walking tours are a good way to learn the city's layout.",
        ],
    },
    "solo_female": {
        "priority": "Personal safety and reliable transport",
        "tips": [
            "Share your live location and itinerary with someone you trust.",
            "Book accommodation in well-lit, central areas with good reviews from women travellers.",
            "Use verified ride-hailing apps rather than street hails at night.",
            "Keep emergency numbers saved offline.",
            "Trust your instincts: if a situation feels wrong, leave.",
        ],
    },
    "family": {
        "priority": "Predictability, comfort and health",
        "tips": [
            "Choose family-friendly accommodation with child amenities.",
            "Identify the nearest hospital and pharmacy to where you stay.",
            "Agree on a meeting point in case anyone gets separated.",
            "Leave rest time in the schedule; avoid peak-heat hours with children.",
            "Book skip-the-line tickets for crowded attractions.",
        ],
    },
    "backpacker": {
        "priority": "Flexibility and local experience",
        "tips": [
            "Keep digital copies of passport, visas and insurance.",
            "Carry some cash for places without card payment.",
            "Ask hostel staff about areas to avoid at night.",
            "Check weather before outdoor or remote trips.",
            "Stay flexible: strikes and weather can change routes quickly.",
        ],
    },
    "elderly": {
        "priority": "Comfort, accessibility and health",
        "tips": [
            "Choose accommodation with lifts and step-free access.",
            "Keep medication in carry-on luggage with a copy of prescriptions.",
            "Carry a medical information card, ideally in the local language.",
            "Prefer guided tours and pre-booked transport.",
            "Get comprehensive travel insurance that covers medical evacuation.",
        ],
    },
}

_ELEVATED = {"guarded", "elevated", "high"}


def planner(levels: Dict[str, str], persona: str) -> Dict[str, List[str]]:
    """Return {"dos": [...], "donts": [...]} from category levels and persona."""
    dos = [
        "Keep copies of important documents separately from the originals.",
        "Save local emergency numbers and your accommodation address offline.",
    ]
    donts = [
        "Don't leave bags unattended in public places.",
        "Don't display expensive jewellery or electronics unnecessarily.",
    ]
    if levels.get("crime") in _ELEVATED:
        dos += ["Stay alert in crowded markets, stations and tourist spots.",
                "Use hotel safes for valuables; carry only what you need."]
        donts += ["Don't walk alone through unfamiliar, poorly lit areas late at night.",
                  "Don't accept unsolicited help with ATMs or luggage."]
    if levels.get("weather") in _ELEVATED:
        dos += ["Check the forecast each morning and keep an indoor backup plan."]
        donts += ["Don't ignore official weather warnings."]
    if levels.get("accident") in _ELEVATED or levels.get("disaster") in _ELEVATED:
        dos += ["Note emergency exits at your accommodation.",
                "Allow extra travel time for disruptions."]
        donts += ["Don't take risks for photos near water, cliffs or traffic."]
    if levels.get("environment") in _ELEVATED:
        dos += ["Check the air-quality reading before long outdoor activities; plan them for cleaner hours."]
        donts += ["Don't do strenuous exercise outdoors while air quality is unhealthy."]
    if levels.get("protest") in _ELEVATED:
        dos += ["Check local news for planned strikes or marches before travelling across the city."]
        donts += ["Don't join or photograph demonstrations; move away from crowds that grow tense."]
    if persona == "solo_female":
        dos += ["Share your plans with a trusted contact and check in regularly."]
        donts += ["Don't share accommodation details with strangers."]
    elif persona == "family":
        dos += ["Keep children's ID and a contact card on them."]
        donts += ["Don't over-pack the daily schedule."]
    elif persona == "elderly":
        dos += ["Schedule regular rest and hydration breaks."]
        donts += ["Don't skip prescribed medication when routines change."]
    return {"dos": dos[:9], "donts": donts[:9]}
