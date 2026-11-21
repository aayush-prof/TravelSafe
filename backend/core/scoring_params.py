"""
Scoring parameters
==================

Every constant used by the risk model lives here so it can be reviewed,
documented and changed in one place. These are *heuristic* settings chosen
from the design principles in the README (proportionality, recency,
confidence, bounded aggregation). They are NOT statistically calibrated
probabilities and must not be presented as such.

No city-specific values exist anywhere in the model.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Tuple


@dataclass(frozen=True)
class ScoringParams:
    # -- Event impact ------------------------------------------------------
    # Impact units per severity level. Convex on purpose: one severe event
    # (-3) outweighs many minor ones (-1).
    impact_by_severity: Dict[int, float] = field(
        default_factory=lambda: {-1: 1.0, -2: 3.0, -3: 10.0}
    )
    # Multiplier for events flagged as historical (anniversaries, verdicts
    # about past incidents, "years ago").
    historical_factor: float = 0.15
    # Multiplier for crimes that the report itself says were resolved by an
    # arrest/bust. The incident still happened, but the report is partly
    # about enforcement rather than an ongoing threat.
    resolved_factor: float = 0.6
    # Recency weight used when an article has no usable timestamp.
    unknown_date_weight: float = 0.5
    # Confidence multiplier for timestamps in the future (clock skew/bad data).
    future_timestamp_confidence: float = 0.8

    # -- Recency (exponential half-life, days) -----------------------------
    half_life_days: Dict[str, float] = field(
        default_factory=lambda: {
            "crime": 14.0,
            "protest": 5.0,
            "accident": 3.0,
            "disaster": 10.0,
            "weather": 2.0,
        }
    )
    # Events older than this are excluded (crime weight at 90 days ≈ 1%).
    max_event_age_days: float = 90.0
    # Period shown to users / used for coverage counts.
    window_days: int = 30

    # -- Location ----------------------------------------------------------
    min_location_confidence: float = 0.4

    # -- Category aggregation ---------------------------------------------
    # pressure = top_event + volume_weight * ln(1 + sum(other events)),
    # where the volume term is capped. This separates the impact of the
    # worst event from the amount of coverage.
    volume_weight: float = 1.5
    volume_cap: float = 2.5
    # risk = 1 - exp(-pressure / saturation)  -> bounded in [0, 1)
    saturation: float = 8.0

    # -- Overall aggregation ----------------------------------------------
    # Relevance of each category to a general traveller's overall picture.
    category_relevance: Dict[str, float] = field(
        default_factory=lambda: {
            "crime": 1.0,
            "disaster": 1.0,
            "protest": 0.8,
            "weather": 0.8,
            "accident": 0.6,
        }
    )
    # Overall = strongest category + damped contribution of the rest.
    secondary_damping: float = 0.35

    # -- Levels ------------------------------------------------------------
    # (upper bound exclusive, level key)
    level_thresholds: Tuple[Tuple[float, str], ...] = (
        (0.15, "low"),
        (0.65, "guarded"),
        (0.85, "elevated"),
        (1.01, "high"),
    )

    # -- Coverage ----------------------------------------------------------
    good_min_articles: int = 15
    some_min_articles: int = 6
    fresh_hours: float = 72.0
    stale_after_days: float = 30.0
    # Positive side of the index is multiplied by this factor per coverage
    # state: absence of reports is weak evidence when coverage is limited.
    coverage_positive_factor: Dict[str, float] = field(
        default_factory=lambda: {"good": 1.0, "limited": 0.5}
    )

    # -- Live weather condition scoring -----------------------------------
    weather_saturation: float = 6.0

    # -- Deduplication -----------------------------------------------------
    dedup_similarity: float = 0.6
    dedup_window_hours: float = 72.0


PARAMS = ScoringParams()


def level_for(risk: float, params: ScoringParams = PARAMS) -> str:
    for bound, key in params.level_thresholds:
        if risk < bound:
            return key
    return "high"


LEVEL_LABELS = {
    "low": "Low",
    "guarded": "Guarded",
    "elevated": "Elevated",
    "high": "High",
    "insufficient": "Insufficient data",
}

OVERALL_LABELS = {
    "low": "Few adverse signals",
    "guarded": "Some adverse signals",
    "elevated": "Elevated adverse signals",
    "high": "High adverse signals",
    "insufficient": "Insufficient data",
}
