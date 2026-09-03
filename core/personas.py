"""
TravelSafe Personas Module
==========================

This module defines traveler personas and their risk weight multipliers.
Different types of travelers have different safety concerns:

- A solo female traveler may be more concerned about crime
- An elderly traveler may prioritize weather and health hazards
- A backpacker may be more tolerant of certain risks

Each persona has weight multipliers for each event type that adjust
the base safety index to reflect their specific concerns.

Weight Interpretation:
- weight = 1.0: Standard concern (same as base index)
- weight > 1.0: Higher concern (makes index worse for this event type)
- weight < 1.0: Lower concern (less impact from this event type)
"""

from typing import Dict, List
from .models import Persona, ClassifiedEvent, EventType


def _create_student_persona() -> Persona:
    """
    Create the Student traveler persona.
    
    Students typically:
    - Travel on a budget
    - May stay in hostels or shared accommodations
    - Are concerned about crime but somewhat risk-tolerant
    - Less concerned about weather inconveniences
    """
    return Persona(
        name="student",
        display_name="Student Traveler",
        description="Budget-conscious travelers, often staying in hostels. "
                    "Moderately concerned about crime, flexible with minor inconveniences.",
        weights={
            "crime": 1.2,      # Slightly elevated concern
            "protest": 1.0,    # Standard concern
            "accident": 0.8,   # Lower concern (young, healthy)
            "disaster": 1.0,   # Standard concern
            "weather": 0.8,    # Can handle weather issues
            "positive": 1.0,   # Standard
            "neutral": 1.0     # Standard
        }
    )


def _create_solo_female_persona() -> Persona:
    """
    Create the Solo Female traveler persona.
    
    Solo female travelers typically:
    - Have heightened safety concerns
    - Prioritize crime and personal safety
    - May avoid areas with civil unrest
    - Generally more cautious
    """
    return Persona(
        name="solo_female",
        display_name="Solo Female Traveler",
        description="Women traveling alone with heightened safety awareness. "
                    "High priority on crime and personal safety concerns.",
        weights={
            "crime": 1.8,      # Very high concern
            "protest": 1.3,    # Elevated concern (crowds, unrest)
            "accident": 1.0,   # Standard concern
            "disaster": 1.0,   # Standard concern
            "weather": 0.9,    # Slightly lower concern
            "positive": 1.0,   # Standard
            "neutral": 1.0     # Standard
        }
    )


def _create_family_persona() -> Persona:
    """
    Create the Family traveler persona.
    
    Family travelers typically:
    - Travel with children
    - Very concerned about all safety aspects
    - Need predictable, safe environments
    - Avoid any areas with potential danger
    """
    return Persona(
        name="family",
        display_name="Family Traveler",
        description="Families traveling with children. High concern for all "
                    "safety aspects, need predictable and secure environments.",
        weights={
            "crime": 1.5,      # High concern (protecting children)
            "protest": 1.4,    # High concern (avoiding crowds)
            "accident": 1.3,   # Elevated concern
            "disaster": 1.5,   # High concern
            "weather": 1.2,    # Elevated concern (children's health)
            "positive": 1.1,   # Slightly elevated (family activities)
            "neutral": 1.0     # Standard
        }
    )


def _create_backpacker_persona() -> Persona:
    """
    Create the Backpacker traveler persona.
    
    Backpackers typically:
    - Are adventurous and risk-tolerant
    - Travel light and flexible
    - May seek authentic local experiences
    - Less concerned about minor incidents
    """
    return Persona(
        name="backpacker",
        display_name="Backpacker",
        description="Adventure-seeking travelers who are flexible and risk-tolerant. "
                    "May embrace local experiences despite minor safety concerns.",
        weights={
            "crime": 1.0,      # Standard concern
            "protest": 0.8,    # Lower concern (may find interesting)
            "accident": 0.9,   # Slightly lower concern
            "disaster": 1.2,   # Elevated concern (practical reasons)
            "weather": 1.1,    # Slightly elevated (outdoor activities)
            "positive": 1.2,   # Values local culture/events
            "neutral": 1.0     # Standard
        }
    )


def _create_elderly_persona() -> Persona:
    """
    Create the Elderly traveler persona.
    
    Elderly travelers typically:
    - Have health and mobility considerations
    - Prioritize comfort and safety
    - Very concerned about weather extremes
    - May have medical needs requiring stable conditions
    """
    return Persona(
        name="elderly",
        display_name="Elderly Traveler",
        description="Senior travelers with health and mobility considerations. "
                    "High priority on weather, disasters, and overall stability.",
        weights={
            "crime": 1.3,      # Elevated concern
            "protest": 1.2,    # Elevated concern (mobility issues in crowds)
            "accident": 1.4,   # High concern
            "disaster": 1.6,   # Very high concern
            "weather": 1.5,    # Very high concern (health impact)
            "positive": 1.0,   # Standard
            "neutral": 1.0     # Standard
        }
    )


def get_all_personas() -> Dict[str, Persona]:
    """
    Get all available traveler personas.
    
    Returns:
        Dictionary mapping persona name to Persona object
        
    Example:
        >>> personas = get_all_personas()
        >>> print(personas.keys())
        dict_keys(['student', 'solo_female', 'family', 'backpacker', 'elderly'])
        >>> print(personas['student'].display_name)
        'Student Traveler'
    """
    return {
        "student": _create_student_persona(),
        "solo_female": _create_solo_female_persona(),
        "family": _create_family_persona(),
        "backpacker": _create_backpacker_persona(),
        "elderly": _create_elderly_persona()
    }


def get_persona(name: str) -> Persona:
    """
    Get a specific persona by name.
    
    Args:
        name: Persona identifier (e.g., 'student', 'solo_female')
        
    Returns:
        Persona object
        
    Raises:
        KeyError: If persona name is not found
        
    Example:
        >>> persona = get_persona('family')
        >>> print(persona.weights['crime'])
        1.5
    """
    personas = get_all_personas()
    if name not in personas:
        raise KeyError(f"Persona '{name}' not found. Available: {list(personas.keys())}")
    return personas[name]


def get_persona_names() -> List[str]:
    """
    Get list of all persona names.
    
    Returns:
        List of persona identifier strings
        
    Example:
        >>> names = get_persona_names()
        >>> print(names)
        ['student', 'solo_female', 'family', 'backpacker', 'elderly']
    """
    return list(get_all_personas().keys())


def get_persona_display_names() -> Dict[str, str]:
    """
    Get mapping of persona names to display names.
    
    Returns:
        Dictionary mapping name to display_name
        
    Example:
        >>> display_names = get_persona_display_names()
        >>> print(display_names['solo_female'])
        'Solo Female Traveler'
    """
    return {
        name: persona.display_name 
        for name, persona in get_all_personas().items()
    }


def apply_persona_weights(
    events: List[ClassifiedEvent], 
    persona: Persona
) -> float:
    """
    Apply persona-specific weights to compute a weighted severity score.
    
    This function takes classified events and applies the persona's weight
    multipliers to compute a raw weighted score. The score is NOT normalized
    to [-10, 10] here - that happens in scoring.py.
    
    Algorithm:
    1. For each event, multiply severity by:
       - confidence (how sure is the classifier)
       - persona weight for the event type
    2. Sum all weighted severities
    3. Divide by number of events (if any)
    
    Args:
        events: List of classified events
        persona: Persona with weight multipliers
        
    Returns:
        Raw weighted score (not normalized)
        
    Example:
        >>> events = [event1, event2, event3]
        >>> persona = get_persona('solo_female')
        >>> raw_score = apply_persona_weights(events, persona)
        >>> print(raw_score)  # e.g., -1.85
    """
    if not events:
        return 0.0
    
    total_weighted_severity = 0.0
    
    for event in events:
        # Get the persona's weight for this event type
        weight = persona.get_weight(event.event_type)
        
        # Calculate weighted severity:
        # severity * confidence * persona_weight
        weighted_severity = event.severity * event.confidence * weight
        
        total_weighted_severity += weighted_severity
    
    # Return average weighted severity
    return total_weighted_severity / len(events)


def get_weight_explanation(persona: Persona) -> str:
    """
    Generate a human-readable explanation of persona weights.
    
    Used in the UI to explain why a persona sees different risk levels.
    
    Args:
        persona: Persona to explain
        
    Returns:
        Multi-line string explanation
        
    Example:
        >>> explanation = get_weight_explanation(get_persona('elderly'))
        >>> print(explanation)
    """
    lines = [f"**{persona.display_name}** weight multipliers:"]
    
    # Sort weights by value (highest concern first)
    sorted_weights = sorted(
        persona.weights.items(), 
        key=lambda x: x[1], 
        reverse=True
    )
    
    for event_type, weight in sorted_weights:
        if weight > 1.2:
            concern = "⚠️ High concern"
        elif weight > 1.0:
            concern = "📊 Elevated"
        elif weight < 1.0:
            concern = "✅ Lower concern"
        else:
            concern = "➖ Standard"
            
        lines.append(f"- {event_type.capitalize()}: {weight}x ({concern})")
    
    return "\n".join(lines)


def compare_personas(
    events: List[ClassifiedEvent], 
    persona_names: List[str] = None
) -> Dict[str, float]:
    """
    Compare raw weighted scores across multiple personas.
    
    Useful for showing how different travelers perceive the same events.
    
    Args:
        events: List of classified events
        persona_names: Names of personas to compare (default: all)
        
    Returns:
        Dictionary mapping persona name to raw weighted score
        
    Example:
        >>> scores = compare_personas(events)
        >>> for name, score in scores.items():
        ...     print(f"{name}: {score:.2f}")
    """
    all_personas = get_all_personas()
    
    if persona_names is None:
        persona_names = list(all_personas.keys())
    
    results = {}
    for name in persona_names:
        if name in all_personas:
            persona = all_personas[name]
            results[name] = apply_persona_weights(events, persona)
    
    return results
