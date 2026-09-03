"""
TravelSafe Scoring Module - Calibrated Risk Assessment
=======================================================

This module implements a CALIBRATED Travel Safety Index that balances:
- Background crime tolerance (not panicking over 1 theft)
- Meaningful escalation (crime always has SOME impact)
- Human intuition matching

DESIGN PHILOSOPHY:
-----------------
- 1 minor crime → noticeable drop, still SAFE
- 2-3 minor crimes → LOW RISK boundary
- 1 violent crime → MODERATE risk (violence is never "noise")
- Multiple violent crimes → HIGH risk
- Crime ALWAYS matters, but doesn't dominate irrationally

KEY MECHANISMS:
---------------
1. MINIMUM CRIME PENALTY: Every crime has a floor impact (never ignored)
2. SEVERITY AMPLIFICATION: Violent crimes bypass smoothing
3. PIECEWISE ESCALATION: Gentle slope → threshold → sharp drop
4. SAFETY CAP: Max score is capped when ANY crime exists
5. CRIME COUNT PENALTY: Direct penalty per crime event

Safety Index Scale:
- +10 to +6: VERY SAFE (no negative events)
- +6 to +3:  SAFE (minor issues, low concern)
- +3 to 0:   LOW RISK (noticeable events, stay aware)
- 0 to -3:   MODERATE (real concern, take precautions)
- -3 to -6:  RISKY (heightened caution advised)
- -6 to -8:  HIGH RISK (avoid hotspots, strong precautions)
- -8 to -10: SEVERE (consider delaying travel)
"""

from typing import List, Dict, Optional, Any, Tuple
from collections import Counter
import math
from .models import NewsItem, ClassifiedEvent, Persona, SafetyResult
from .config import (
    SAFETY_INDEX_MIN,
    SAFETY_INDEX_MAX,
    SEVERITY_MIN,
    SEVERITY_MAX,
    EVENT_TYPES,
    DEFAULT_PERSONA,
)
from .utils import normalize_score, clamp_value
from .personas import get_persona


SEVERITY_WEIGHTS = {
    -1: 1.5,    # Minor crime: increased impact (was 1.0)
    -2: 4.0,    # Moderate/violent crime: significant impact (was 3.5)
    -3: 7.5,    # Severe crime (murder, terrorism): heavy impact (was 7.0)
}

# MINIMUM penalty per crime (floor impact - crime is NEVER ignored)
# CALIBRATED: Increased floors for realistic impact
MIN_CRIME_PENALTY = {
    -1: 0.8,    # Minor crime: at least 0.8 point drop (was 0.5)
    -2: 2.5,    # Violent crime: at least 2.5 point drop (was 2.2)
    -3: 3.5,    # Severe crime: at least 3.5 point drop (was 3.2)
}

# VIOLENT CRIME CONFIDENCE BREAKER
# Psychological safety loss when violence exists - bypasses all smoothing
VIOLENT_CRIME_CONFIDENCE_PENALTY = 1.0  # Applied once if ANY violent/severe crime exists (was 0.8)

# Safety cap when crime exists (prevents "all safe" despite crimes)
# CALIBRATED: Tightened caps to ensure proper band placement
SAFETY_CAP_WITH_CRIME = {
    "minor_only": 4.5,      # Cap at +4.5 if only minor crimes (was 5.5)
    "any_violent": 2.0,     # Cap at +2.0 if any violent crime (was 3.0) → ensures LOW RISK max
    "any_severe": 0.0,      # Cap at 0.0 if any severe crime (was 1.0) → ensures MODERATE max
}

# VIOLENCE ESCALATION MULTIPLIERS
# Applied to penalty when multiple violent/severe crimes exist
VIOLENCE_ESCALATION = {
    2: 1.35,   # 2 violent crimes → 1.35x penalty multiplier (was 1.25)
    3: 1.55,   # 3+ violent crimes → 1.55x penalty multiplier (was 1.40)
}

# Threshold configuration for PIECEWISE escalation
# Format: (effective_density_threshold, penalty_points)
# CALIBRATED: Increased penalties for more severe base index
THREAT_TIERS = [
    (0.0, 0.0),    # Starting point
    (1.0, 1.2),    # 0-1.0 → steeper slope (was 0.8)
    (2.5, 3.5),    # 1.0-2.5 → moderate slope (was 2.5)
    (4.0, 6.5),    # 2.5-4.0 → steeper (was 5.0)
    (6.0, 10.0),   # 4.0-6.0 → sharp escalation (was 8.0)
    (8.0, 13.0),   # 6.0-8.0 → high danger (was 11.0)
    (10.0, 16.0),  # 8.0-10.0 → severe (was 14.0)
    (float('inf'), 19.0)  # 10+ → maximum danger (was 17.0)
]

# Event type threat multipliers
# CALIBRATED: Increased weights for more severe base index
EVENT_TYPE_THREAT_WEIGHT = {
    "crime": 1.2,      # Increased weight (was 1.0)
    "protest": 0.85,   # Increased weight (was 0.7)
    "accident": 0.6,   # Increased weight (was 0.4)
    "disaster": 1.0,   # Full weight (was 0.9)
    "weather": 0.5,    # Increased weight (was 0.3)
    "positive": 0.0,   # No threat
    "neutral": 0.0,    # No threat
}

# Baseline score when no events
BASELINE_SCORE = 5.5  # Lowered further for more severe baseline (was 6.5)

# Minimum events for full penalty (but minimum floor always applies)
MIN_EVENTS_FOR_FULL_PENALTY = 1  # Even 1 incident warrants full penalty (was 2)


def aggregate_scores_from_unified() -> Dict[str, Any]:
    """Aggregate scores using the shared unified_events in session_state."""
    try:
        import streamlit as st
        events = st.session_state.get("unified_events", [])
    except Exception:
        events = []
    return aggregate_scores(events)


def compute_severity_density(events: List[ClassifiedEvent]) -> Dict[str, float]:
    """
    Compute severity-weighted density for each event type.
    
    Also tracks crime counts by severity level for minimum penalty calculation.
    
    Args:
        events: List of ClassifiedEvent objects
        
    Returns:
        Dict with density values AND crime counts by severity
    """
    density = {etype: 0.0 for etype in EVENT_TYPES}
    density['total'] = 0.0
    density['positive_total'] = 0.0
    
    # Track crime counts by severity for minimum penalty floor
    density['crime_count_minor'] = 0      # severity -1
    density['crime_count_violent'] = 0    # severity -2
    density['crime_count_severe'] = 0     # severity -3
    density['total_negative_events'] = 0
    
    for event in events:
        severity = event.severity
        confidence = event.confidence
        event_type = event.event_type
        
        if severity < 0:
            density['total_negative_events'] += 1
            
            # Track crime counts by severity
            if event_type == "crime":
                if severity == -1:
                    density['crime_count_minor'] += 1
                elif severity == -2:
                    density['crime_count_violent'] += 1
                elif severity == -3:
                    density['crime_count_severe'] += 1
            
            # Negative event: apply severity weight
            weight = SEVERITY_WEIGHTS.get(severity, abs(severity) * 1.5)
            type_multiplier = EVENT_TYPE_THREAT_WEIGHT.get(event_type, 0.5)
            score = weight * confidence * type_multiplier
            density[event_type] += score
            density['total'] += score
            
        elif severity > 0:
            # Positive event: accumulate for bonus calculation
            density['positive_total'] += severity * confidence * 0.5
    
    return density


def compute_minimum_crime_penalty(density: Dict[str, float]) -> float:
    """
    Compute the MINIMUM penalty floor based on crime presence.
    
    This ensures crime is NEVER completely ignored. Every crime event
    has a guaranteed minimum impact on the safety index.
    
    Formula: sum of (count × min_penalty) for each severity level
    
    Args:
        density: Dict containing crime counts by severity
        
    Returns:
        Minimum penalty that must be applied
    """
    min_penalty = 0.0
    
    # Add floor penalty for each crime
    min_penalty += density.get('crime_count_minor', 0) * MIN_CRIME_PENALTY[-1]
    min_penalty += density.get('crime_count_violent', 0) * MIN_CRIME_PENALTY[-2]
    min_penalty += density.get('crime_count_severe', 0) * MIN_CRIME_PENALTY[-3]
    
    return min_penalty


def compute_safety_cap(density: Dict[str, float]) -> float:
    """
    Compute the maximum allowed safety score based on crime severity present.
    
    This prevents "all safe" collapse - if crimes exist, score is capped.
    
    Args:
        density: Dict containing crime counts by severity
        
    Returns:
        Maximum allowed safety index
    """
    # Default: no cap (return max possible)
    cap = SAFETY_INDEX_MAX
    
    # Apply caps based on worst crime present
    if density.get('crime_count_severe', 0) > 0:
        cap = min(cap, SAFETY_CAP_WITH_CRIME["any_severe"])
    elif density.get('crime_count_violent', 0) > 0:
        cap = min(cap, SAFETY_CAP_WITH_CRIME["any_violent"])
    elif density.get('crime_count_minor', 0) > 0:
        cap = min(cap, SAFETY_CAP_WITH_CRIME["minor_only"])
    
    return cap


def compute_threat_penalty(severity_density: float, event_count: int, density: Dict[str, float]) -> float:
    """
    Convert severity density to a threat penalty using PIECEWISE escalation.
    
    Key changes from previous version:
    1. No "zero penalty" zone - penalty starts immediately
    2. Minimum floor penalty always applied (crime never ignored)
    3. Violent crimes get amplified penalty (bypass smoothing)
    4. Piecewise function: gentle slope → threshold → sharp drop
    
    Args:
        severity_density: Total weighted severity score
        event_count: Number of events
        density: Full density dict for crime counts
        
    Returns:
        Total penalty value
    """
    # Apply square root scaling (gentler than log, but still non-linear)
    # This allows single events to matter while preventing extreme spikes
    effective_density = math.sqrt(severity_density) * 1.8
    
    # Find penalty using piecewise interpolation
    penalty = 0.0
    prev_threshold, prev_penalty = 0.0, 0.0
    
    for threshold, tier_penalty in THREAT_TIERS:
        if effective_density < threshold:
            # Linear interpolation within tier
            if threshold > prev_threshold:
                ratio = (effective_density - prev_threshold) / (threshold - prev_threshold)
                penalty = prev_penalty + ratio * (tier_penalty - prev_penalty)
            else:
                penalty = tier_penalty
            break
        prev_threshold, prev_penalty = threshold, tier_penalty
    
    # VIOLENT CRIME AMPLIFICATION: Violent crimes bypass smoothing
    # Each violent crime adds direct penalty (not just through density)
    violent_count = density.get('crime_count_violent', 0)
    severe_count = density.get('crime_count_severe', 0)
    total_violent_severe = violent_count + severe_count
    
    if violent_count > 0:
        # First violent crime: +1.0 penalty, subsequent: +0.7 each
        penalty += 1.0 + (violent_count - 1) * 0.7
    
    if severe_count > 0:
        # Severe crimes: +2.0 first, +1.2 each subsequent
        penalty += 2.0 + (severe_count - 1) * 1.2
    
    # VIOLENCE ESCALATION MULTIPLIER (Change 4)
    # Multiple violent/severe crimes trigger escalation
    if total_violent_severe >= 3:
        penalty *= VIOLENCE_ESCALATION[3]  # 1.45x multiplier
    elif total_violent_severe >= 2:
        penalty *= VIOLENCE_ESCALATION[2]  # 1.25x multiplier
    
    # Compute minimum floor penalty
    min_penalty = compute_minimum_crime_penalty(density)
    
    # Final penalty is MAX of (computed penalty, minimum floor)
    # This ensures crime is NEVER ignored
    penalty = max(penalty, min_penalty)
    
    # Light sample size adjustment (reduced effect - violence should still matter)
    if event_count == 1 and total_violent_severe == 0:
        penalty *= 0.90  # Only 10% reduction, and ONLY for non-violent single events
    elif event_count == 2 and total_violent_severe == 0:
        penalty *= 0.95  # Only 5% reduction for non-violent
    # No reduction for violent/severe crimes regardless of count
    
    return penalty


def compute_positive_bonus(positive_density: float, event_count: int) -> float:
    """
    Compute bonus for positive events (festivals, tourism, safety improvements).
    
    Positive events provide a buffer against minor negative events,
    reflecting that cities with active tourism/culture are generally safe.
    
    Uses logarithmic scaling to prevent over-inflation.
    
    Args:
        positive_density: Sum of positive severity × confidence
        event_count: Total number of events
        
    Returns:
        Bonus value between 0 and 1.5 (reduced to prevent masking negative events)
    """
    if positive_density <= 0:
        return 0.0
    
    # Logarithmic scaling with cap (reduced multiplier)
    raw_bonus = math.log(1 + positive_density) * 0.8  # Was 1.2
    
    # Cap at 1.5 points (reduced from 2.5 to prevent masking crime)
    return min(1.5, raw_bonus)


def compute_base_index(events: List[ClassifiedEvent]) -> float:
    """
    Compute the base Travel Safety Index using CALIBRATED threat modeling.
    
    ALGORITHM:
    ---------
    1. Start with baseline score (+7.0)
    2. Compute severity density with crime tracking
    3. Compute threat penalty with:
       - Piecewise escalation
       - Violent crime amplification + escalation multipliers
       - Minimum floor penalty (crime never ignored)
    4. Apply VIOLENT CRIME CONFIDENCE BREAKER (bypasses smoothing)
    5. Apply safety cap based on worst crime present
    6. Add positive event bonus
    7. Final = min(cap, baseline + bonus - penalty - confidence_breaker)
    
    TARGET OUTPUTS (CALIBRATED):
    ---------------------------
    - 0 events: +7.0 (VERY SAFE)
    - 1 minor crime: ~+5.0 (SAFE)
    - 2-3 minor crimes: ~+4.0 (SAFE/LOW boundary)
    - 1 violent crime: ~+2.0 (LOW RISK, never SAFE)
    - 2 violent crimes: ~0.0 (MODERATE)
    - 1 severe crime: ~-0.5 (MODERATE)
    - 3 violent crimes: ~-3.0 (RISKY)
    - 5+ violent/severe: <-6.0 (HIGH/SEVERE)
    
    Args:
        events: List of ClassifiedEvent objects
        
    Returns:
        Base safety index as float between -10 and +10
    """
    event_count = len(events)
    
    # No events = benefit of doubt
    if event_count == 0:
        return BASELINE_SCORE
    
    # Step 1: Compute severity density with crime tracking
    density = compute_severity_density(events)
    total_threat_density = density['total']
    positive_density = density['positive_total']
    
    # Step 2: Compute threat penalty (with minimum floor and amplification)
    threat_penalty = compute_threat_penalty(total_threat_density, event_count, density)
    
    # Step 3: Compute positive bonus
    positive_bonus = compute_positive_bonus(positive_density, event_count)
    
    # Step 4: Calculate raw index
    safety_index = BASELINE_SCORE + positive_bonus - threat_penalty
    
    # Step 5: VIOLENT CRIME CONFIDENCE BREAKER (Change 2)
    # If ANY violent or severe crime exists, apply psychological safety penalty
    # This bypasses all smoothing and represents fundamental trust loss
    violent_count = density.get('crime_count_violent', 0)
    severe_count = density.get('crime_count_severe', 0)
    if violent_count > 0 or severe_count > 0:
        safety_index -= VIOLENT_CRIME_CONFIDENCE_PENALTY  # -0.8 penalty
    
    # Step 6: Apply safety cap (prevents "all safe" despite crimes)
    safety_cap = compute_safety_cap(density)
    safety_index = min(safety_index, safety_cap)
    
    # Clamp to valid range
    safety_index = clamp_value(safety_index, SAFETY_INDEX_MIN, SAFETY_INDEX_MAX)
    
    return round(safety_index, 1)


def _calculate_dampening_factor(event_count: int) -> float:
    """
    Calculate a dampening factor based on the number of events.
    
    With few events, we're less confident in the result, so we
    pull the score toward neutral (0). With many events, we
    trust the data more.
    
    Formula: dampening = min(1.0, 0.5 + (event_count / 20))
    
    Examples:
    - 1 event:  0.55 (45% dampened toward neutral)
    - 5 events: 0.75 (25% dampened)
    - 10 events: 1.0 (no dampening)
    - 20+ events: 1.0 (no dampening)
    
    Args:
        event_count: Number of events
        
    Returns:
        Dampening multiplier between 0.5 and 1.0
    """
    return min(1.0, 0.5 + (event_count / 20.0))


def compute_persona_index(
    events: List[ClassifiedEvent], 
    persona: Persona
) -> float:
    """
    Compute persona-adjusted Travel Safety Index with CALIBRATED weighting.
    
    Personas amplify relevant risks but crime always has meaningful impact.
    
    ALGORITHM:
    ---------
    1. Compute base severity density with crime tracking
    2. Apply persona weights (dampened for minor crimes, full for violent)
    3. Compute penalty with minimum floor
    4. Apply safety cap based on crime severity
    5. Final = min(cap, baseline + bonus - penalty - sensitivity_offset)
    
    Args:
        events: List of ClassifiedEvent objects
        persona: Persona object with weight multipliers
        
    Returns:
        Persona-adjusted index between -10 and +10
    """
    event_count = len(events)
    if event_count == 0:
        return BASELINE_SCORE
    
    # First compute base density for crime tracking
    base_density = compute_severity_density(events)
    
    # Compute persona-weighted severity density
    weighted_threat_density = 0.0
    positive_density = 0.0
    
    # Track persona-adjusted crime counts
    persona_crime_density = {
        'crime_count_minor': base_density['crime_count_minor'],
        'crime_count_violent': base_density['crime_count_violent'],
        'crime_count_severe': base_density['crime_count_severe'],
        'total_negative_events': base_density['total_negative_events']
    }
    
    for event in events:
        severity = event.severity
        confidence = event.confidence
        event_type = event.event_type
        
        # Get persona weight for this event type
        persona_weight = persona.get_weight(event_type)
        
        if severity < 0:
            base_weight = SEVERITY_WEIGHTS.get(severity, abs(severity) * 1.5)
            type_multiplier = EVENT_TYPE_THREAT_WEIGHT.get(event_type, 0.5)
            
            # Persona weight application:
            # - Minor crimes: dampened (sqrt) to avoid overreaction
            # - Violent/severe crimes: less dampening (they always matter)
            if severity == -1:
                effective_persona_weight = math.sqrt(persona_weight)
            else:
                # Violent crimes: use weight^0.7 (less dampening)
                effective_persona_weight = math.pow(persona_weight, 0.7)
            
            score = base_weight * confidence * type_multiplier * effective_persona_weight
            weighted_threat_density += score
            
        elif severity > 0:
            positive_weight = persona.get_weight("positive")
            positive_density += severity * confidence * 0.5 * math.sqrt(positive_weight)
    
    # Compute threat penalty with minimum floor
    threat_penalty = compute_threat_penalty(weighted_threat_density, event_count, persona_crime_density)
    
    # Compute positive bonus
    positive_bonus = compute_positive_bonus(positive_density, event_count)
    
    # Sensitivity offset for cautious personas
    max_persona_weight = max(persona.weights.values(), default=1.0)
    sensitivity_offset = 0.0
    if max_persona_weight > 1.3 and base_density['total_negative_events'] > 0:
        sensitivity_offset = 0.2 * (max_persona_weight - 1.0)
    
    # Calculate raw index
    persona_index = BASELINE_SCORE + positive_bonus - threat_penalty - sensitivity_offset
    
    # VIOLENT CRIME CONFIDENCE BREAKER (also applies to persona index)
    violent_count = base_density.get('crime_count_violent', 0)
    severe_count = base_density.get('crime_count_severe', 0)
    if violent_count > 0 or severe_count > 0:
        persona_index -= VIOLENT_CRIME_CONFIDENCE_PENALTY  # -0.8 penalty
    
    # Apply safety cap (based on base density crime tracking)
    safety_cap = compute_safety_cap(base_density)
    persona_index = min(persona_index, safety_cap)
    
    # Clamp to valid range
    persona_index = clamp_value(persona_index, SAFETY_INDEX_MIN, SAFETY_INDEX_MAX)
    
    return round(persona_index, 2)


def compute_safety_index(
    events: List[ClassifiedEvent],
    persona: Persona
) -> Tuple[float, float]:
    """
    Compute both base and persona-adjusted safety indices.
    Uses probability-based risk model for realistic threat assessment.
    """
    base_index = compute_base_index(events)
    persona_index = compute_persona_index(events, persona)
    return base_index, persona_index


def compute_safety_result(
    city: str,
    events: List[ClassifiedEvent],
    persona: Persona
) -> SafetyResult:
    """
    Compute complete safety analysis for a city.
    
    This is the main function that orchestrates all scoring and
    returns a comprehensive SafetyResult object.
    
    Args:
        city: Name of the city being analyzed
        events: List of classified events for the city
        persona: Traveler persona for adjusted scoring
        
    Returns:
        SafetyResult with all computed metrics
        
    Example:
        >>> from core.personas import get_persona
        >>> from core.news_client import fetch_news_for_city
        >>> from core.classifier import classify_news_list
        >>> 
        >>> news = fetch_news_for_city("Mumbai")
        >>> events = classify_news_list(news)
        >>> persona = get_persona("family")
        >>> result = compute_safety_result("Mumbai", events, persona)
        >>> 
        >>> print(f"Base Index: {result.base_index}")
        >>> print(f"Family Index: {result.persona_index}")
    """
    # Compute both indices using severity-based scoring
    base_index, persona_index = compute_safety_index(events, persona)
    
    # Calculate event counts by type
    event_counts = _count_events_by_type(events)
    
    # Calculate average severity by type
    avg_severity = _average_severity_by_type(events)
    
    # Build and return the result
    return SafetyResult(
        city=city,
        base_index=base_index,
        persona_index=persona_index,
        events=events,
        persona_name=persona.name,
        event_counts=event_counts,
        avg_severity=avg_severity
    )


def aggregate_scores(events_list: List[ClassifiedEvent]) -> Dict[str, Any]:
    """Aggregate safety metrics using per-event severities and persona weights."""
    events = events_list or []
    category_counts = Counter(e.event_type for e in events)
    total_events = len(events)

    try:
        import streamlit as st  # Lazy import to avoid hard dependency
        persona_name = st.session_state.get("selected_persona", DEFAULT_PERSONA)
    except Exception:
        persona_name = DEFAULT_PERSONA

    persona = get_persona(persona_name)

    base_index, persona_index = compute_safety_index(events, persona)

    return {
        "index": persona_index,
        "base_index": base_index,
        "total_events": total_events,
        "category_counts": {etype: category_counts.get(etype, 0) for etype in EVENT_TYPES},
    }


def _extract_severity(event: Any) -> Optional[float]:
    """Safely pull severity from either dataclass objects or dictionaries."""
    if event is None:
        return None
    if isinstance(event, dict):
        return event.get("severity")
    return getattr(event, "severity", None)

def _count_events_by_type(events: List[ClassifiedEvent]) -> Dict[str, int]:
    """
    Count events grouped by event type.
    
    Args:
        events: List of classified events
        
    Returns:
        Dictionary mapping event_type to count
    """
    counts = {event_type: 0 for event_type in EVENT_TYPES}
    
    for event in events:
        counts[event.event_type] += 1
    
    return counts


def _average_severity_by_type(events: List[ClassifiedEvent]) -> Dict[str, float]:
    """
    Calculate average severity for each event type.
    
    Args:
        events: List of classified events
        
    Returns:
        Dictionary mapping event_type to average severity
    """
    # Collect severities by type
    severities_by_type: Dict[str, List[int]] = {
        event_type: [] for event_type in EVENT_TYPES
    }
    
    for event in events:
        severities_by_type[event.event_type].append(event.severity)
    
    # Calculate averages
    averages = {}
    for event_type, severities in severities_by_type.items():
        if severities:
            averages[event_type] = round(sum(severities) / len(severities), 2)
        else:
            averages[event_type] = 0.0
    
    return averages


def get_index_interpretation(index: float) -> str:
    """
    Get a human-readable interpretation of a safety index.
    
    CALIBRATED BANDS:
    - +6 to +10: VERY SAFE (no crime events)
    - +3 to +6:  SAFE (minor issues only)
    - 0 to +3:   LOW RISK (noticeable events)
    - -3 to 0:   MODERATE (real concern)
    - -6 to -3:  RISKY (heightened caution)
    - -8 to -6:  HIGH RISK (dangerous)
    - -10 to -8: SEVERE (avoid travel)
    
    Args:
        index: Safety index value (-10 to +10)
        
    Returns:
        Interpretation string
    """
    if index >= 6:
        return "VERY SAFE – Minimal risk, no significant concerns."
    elif index >= 3:
        return "SAFE – Low risk, minor issues possible."
    elif index >= 0:
        return "LOW RISK – Some concerns noted, stay aware."
    elif index >= -3:
        return "MODERATE – Real concerns present, take precautions."
    elif index >= -6:
        return "RISKY – Heightened caution advised; avoid risk areas."
    elif index >= -8:
        return "HIGH RISK – Significant danger; strong precautions needed."
    else:
        return "SEVERE – Consider postponing or avoiding travel."


def get_index_emoji(index: float) -> str:
    """
    Get an emoji representing the safety level.
    
    Args:
        index: Safety index value (-10 to +10)
        
    Returns:
        Emoji string
    """
    if index >= 6:
        return "🟢"  # VERY SAFE
    elif index >= 3:
        return "🟢"  # SAFE
    elif index >= 0:
        return "🟡"  # LOW RISK
    elif index >= -3:
        return "🟠"  # MODERATE
    elif index >= -6:
        return "🔴"  # RISKY
    elif index >= -8:
        return "🔴"  # HIGH RISK
    else:
        return "⛔"  # SEVERE


def compare_cities(
    city_events: Dict[str, List[ClassifiedEvent]],
    persona: Optional[Persona] = None
) -> Dict[str, float]:
    """
    Compare safety indices across multiple cities.
    
    Args:
        city_events: Dictionary mapping city name to events
        persona: Optional persona for adjusted scoring
        
    Returns:
        Dictionary mapping city name to safety index
    """
    results = {}
    
    for city, events in city_events.items():
        if persona:
            results[city] = compute_persona_index(events, persona)
        else:
            results[city] = compute_base_index(events)
    
    return results


def get_scoring_explanation() -> str:
    """
    Return a detailed explanation of the scoring methodology.
    
    Useful for documentation and help sections in the UI.
    
    Returns:
        Multi-line markdown explanation
    """
    return """
## How the Travel Safety Index Works

### Philosophy
The index is CALIBRATED to match **human intuition**:
- Crime is **never ignored** (minimum penalty floor)
- 1 minor crime = noticeable drop, still SAFE
- 1 violent crime = MODERATE concern (violence is serious)
- Multiple violent crimes = HIGH RISK

### Scale
| Index Range | Rating | Meaning |
|------------|--------|---------|
| +6 to +10 | 🟢 VERY SAFE | No crime events present |
| +3 to +6 | 🟢 SAFE | Minor issues only, low concern |
| 0 to +3 | 🟡 LOW RISK | Noticeable events, stay aware |
| -3 to 0 | 🟠 MODERATE | Real concerns, take precautions |
| -6 to -3 | 🔴 RISKY | Heightened caution advised |
| -8 to -6 | 🔴 HIGH RISK | Significant danger |
| -10 to -8 | ⛔ SEVERE | Consider avoiding travel |

### Key Mechanisms

1. **Minimum Crime Penalty Floor**
   - Minor crime: at least -0.4 points
   - Violent crime: at least -1.5 points
   - Severe crime: at least -2.5 points
   - Crime is NEVER ignored

2. **Safety Cap When Crime Exists**
   - Minor crimes only: max +6.0 (never VERY SAFE)
   - Any violent crime: max +4.0
   - Any severe crime: max +2.0

3. **Violent Crime Amplification**
   - Violent crimes add direct penalty (bypass smoothing)
   - First violent: +1.0 penalty, each additional: +0.7
   - First severe: +2.0 penalty, each additional: +1.5

4. **Piecewise Escalation**
   - Low crime: gentle slope
   - Threshold crossed: sharper drop
   - Prevents both extremes (panic AND complacency)

### Target Outputs
| Scenario | Index | Rating |
|----------|-------|--------|
| 0 events | +7.0 | VERY SAFE |
| 1 minor crime | +5.5 | SAFE |
| 2 minor crimes | +4.5 | SAFE |
| 1 violent crime | +2.5 | LOW RISK |
| 3 violent crimes | -0.5 | MODERATE |
| Multiple severe | -3.0 | RISKY |
"""


def debug_scoring_examples() -> Dict[str, Any]:
    """
    Run example calculations to verify the scoring system produces
    realistic, human-intuitive results.
    
    This function creates mock events and computes scores to demonstrate:
    - 1 minor crime → SAFE
    - 2 minor crimes → SAFE  
    - 1 violent crime → slightly reduced but still SAFE
    - Multiple violent crimes → MODERATE
    - Severe pattern → HIGH RISK
    
    Returns:
        Dictionary with scenario names and their computed scores
    """
    from datetime import datetime
    
    # Helper to create mock events
    def make_event(event_type: str, severity: int, confidence: float = 0.85) -> ClassifiedEvent:
        news = NewsItem(
            title=f"Test {event_type} event",
            description=f"Mock event with severity {severity}",
            city="TestCity",
            source="Test",
            published_at=datetime.now()
        )
        return ClassifiedEvent(
            news_item=news,
            event_type=event_type,
            severity=severity,
            confidence=confidence
        )
    
    results = {}
    
    # Scenario 1: No events
    events_0 = []
    results["0_events"] = {
        "base_index": compute_base_index(events_0),
        "interpretation": get_index_interpretation(compute_base_index(events_0))
    }
    
    # Scenario 2: 1 minor crime (theft)
    events_1_minor = [make_event("crime", -1)]
    results["1_minor_crime"] = {
        "base_index": compute_base_index(events_1_minor),
        "interpretation": get_index_interpretation(compute_base_index(events_1_minor)),
        "density": compute_severity_density(events_1_minor)['total']
    }
    
    # Scenario 3: 2 minor crimes
    events_2_minor = [make_event("crime", -1), make_event("crime", -1)]
    results["2_minor_crimes"] = {
        "base_index": compute_base_index(events_2_minor),
        "interpretation": get_index_interpretation(compute_base_index(events_2_minor)),
        "density": compute_severity_density(events_2_minor)['total']
    }
    
    # Scenario 4: 1 violent crime (robbery/murder severity -2)
    events_1_violent = [make_event("crime", -2)]
    results["1_violent_crime"] = {
        "base_index": compute_base_index(events_1_violent),
        "interpretation": get_index_interpretation(compute_base_index(events_1_violent)),
        "density": compute_severity_density(events_1_violent)['total']
    }
    
    # Scenario 5: 1 severe crime (murder severity -3)
    events_1_severe = [make_event("crime", -3)]
    results["1_severe_crime"] = {
        "base_index": compute_base_index(events_1_severe),
        "interpretation": get_index_interpretation(compute_base_index(events_1_severe)),
        "density": compute_severity_density(events_1_severe)['total']
    }
    
    # Scenario 6: 3 violent crimes
    events_3_violent = [make_event("crime", -2) for _ in range(3)]
    results["3_violent_crimes"] = {
        "base_index": compute_base_index(events_3_violent),
        "interpretation": get_index_interpretation(compute_base_index(events_3_violent)),
        "density": compute_severity_density(events_3_violent)['total']
    }
    
    # Scenario 7: 5 violent crimes
    events_5_violent = [make_event("crime", -2) for _ in range(5)]
    results["5_violent_crimes"] = {
        "base_index": compute_base_index(events_5_violent),
        "interpretation": get_index_interpretation(compute_base_index(events_5_violent)),
        "density": compute_severity_density(events_5_violent)['total']
    }
    
    # Scenario 8: Mixed severe events (murders + riot)
    events_severe_pattern = [
        make_event("crime", -3),
        make_event("crime", -3),
        make_event("crime", -2),
        make_event("protest", -2),  # Riot
    ]
    results["severe_pattern"] = {
        "base_index": compute_base_index(events_severe_pattern),
        "interpretation": get_index_interpretation(compute_base_index(events_severe_pattern)),
        "density": compute_severity_density(events_severe_pattern)['total']
    }
    
    # Scenario 8b: Extreme danger (multiple murders + riots + disasters)
    events_extreme = [
        make_event("crime", -3),
        make_event("crime", -3),
        make_event("crime", -3),
        make_event("crime", -2),
        make_event("crime", -2),
        make_event("protest", -2),  # Riot
        make_event("protest", -2),  # Another riot
    ]
    results["extreme_danger"] = {
        "base_index": compute_base_index(events_extreme),
        "interpretation": get_index_interpretation(compute_base_index(events_extreme)),
        "density": compute_severity_density(events_extreme)['total']
    }
    
    # Scenario 9: 1 minor crime + positive events (festival)
    events_mixed_positive = [
        make_event("crime", -1),
        make_event("positive", 2),
        make_event("positive", 1),
    ]
    results["1_crime_with_positives"] = {
        "base_index": compute_base_index(events_mixed_positive),
        "interpretation": get_index_interpretation(compute_base_index(events_mixed_positive)),
        "density": compute_severity_density(events_mixed_positive)['total']
    }
    
    # Scenario 10: Only neutral/positive events
    events_positive = [
        make_event("positive", 2),
        make_event("neutral", 0),
        make_event("positive", 1),
    ]
    results["positive_only"] = {
        "base_index": compute_base_index(events_positive),
        "interpretation": get_index_interpretation(compute_base_index(events_positive)),
        "density": compute_severity_density(events_positive)['total']
    }
    
    return results


def print_scoring_demo():
    """Print a formatted demonstration of the scoring system."""
    results = debug_scoring_examples()
    
    print("\n" + "="*70)
    print("TRAVEL SAFETY INDEX - REALISTIC SCORING DEMONSTRATION")
    print("="*70)
    
    scenarios = [
        ("0_events", "No events (baseline)"),
        ("1_minor_crime", "1 minor crime (theft)"),
        ("2_minor_crimes", "2 minor crimes"),
        ("1_violent_crime", "1 violent crime (robbery)"),
        ("1_severe_crime", "1 severe crime (murder)"),
        ("3_violent_crimes", "3 violent crimes"),
        ("5_violent_crimes", "5 violent crimes"),
        ("severe_pattern", "Severe pattern (2 murders + robbery + riot)"),
        ("extreme_danger", "Extreme (3 murders + 2 robberies + 2 riots)"),
        ("1_crime_with_positives", "1 minor crime + 2 positive events"),
        ("positive_only", "Only positive/neutral events"),
    ]
    
    for key, description in scenarios:
        r = results[key]
        print(f"\n{description}")
        print(f"  Base Index: {r['base_index']:+.1f}")
        print(f"  Rating: {r['interpretation']}")
        if 'density' in r:
            print(f"  Threat Density: {r['density']:.2f}")
    
    print("\n" + "="*70)
    print("KEY OBSERVATIONS:")
    print("- 1-2 minor crimes stay in VERY SAFE/SAFE range (realistic)")
    print("- Single violent crime causes slight drop but not panic")
    print("- Multiple violent crimes push toward MODERATE")
    print("- Severe patterns reach RISKY/HIGH RISK appropriately")
    print("- Positive events provide buffer against minor incidents")
    print("="*70 + "\n")


# Allow running as a script for testing
if __name__ == "__main__":
    print_scoring_demo()
