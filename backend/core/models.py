"""
Domain models
=============

Pydantic models shared by the pipeline. These extend the original
``NewsItem`` / ``ClassifiedEvent`` / ``Persona`` models with the metadata the
redesigned scoring needs (provenance, URLs, location/temporal quality).
"""

from __future__ import annotations

from datetime import datetime
from typing import Dict, List, Literal, Optional

from pydantic import BaseModel, Field, field_validator

EventType = Literal["crime", "protest", "accident", "disaster", "weather", "positive", "neutral"]
DataOrigin = Literal["live", "sample"]


class NewsItem(BaseModel):
    """A raw article from a provider or from the sample dataset."""

    title: str = Field(..., min_length=1)
    description: Optional[str] = None
    city: str = Field(..., min_length=1, description="City the article was retrieved for")
    source: str = "Unknown"
    url: Optional[str] = None
    # Timezone-aware UTC; None when the provider gave no usable timestamp.
    published_at: Optional[datetime] = None
    # Incident date if a provider supplies one (none of the current ones do).
    incident_at: Optional[datetime] = None
    provider: str = "unknown"
    origin: DataOrigin = "live"

    @field_validator("title", "city")
    @classmethod
    def _strip(cls, v: str) -> str:
        return v.strip()

    def get_full_text(self) -> str:
        return f"{self.title}. {self.description}" if self.description else self.title


class ClassifiedEvent(BaseModel):
    """A news item after classification and quality assessment."""

    id: str
    news_item: NewsItem
    event_type: EventType
    subtype: str = "general"
    # -3 (severe negative) .. +3 (positive). Severity describes the event;
    # confidence describes how sure we are about the classification.
    severity: int = Field(..., ge=-3, le=3)
    confidence: float = Field(..., ge=0.0, le=1.0)
    matched_terms: List[str] = Field(default_factory=list)
    flags: List[str] = Field(default_factory=list)
    is_historical: bool = False
    is_resolved: bool = False

    # Location quality
    location_confidence: float = 1.0
    location_note: str = ""

    # Deduplication
    duplicate_count: int = 1
    sources: List[str] = Field(default_factory=list)
    urls: List[str] = Field(default_factory=list)

    # Filled in by scoring
    date_basis: Literal["incident", "published", "unknown"] = "published"
    age_hours: Optional[float] = None
    recency_weight: float = 1.0
    impact: float = 0.0
    counted: bool = True
    exclusion_reason: Optional[str] = None


class Persona(BaseModel):
    name: str
    display_name: str
    description: str = ""
    weights: Dict[str, float]
    rationale: Dict[str, str] = Field(default_factory=dict)

    @field_validator("weights")
    @classmethod
    def _validate(cls, v: Dict[str, float]) -> Dict[str, float]:
        for k, w in v.items():
            if not 0.5 <= w <= 2.0:
                raise ValueError(f"Persona weight for {k} must be within [0.5, 2.0]")
        return v

    def get_weight(self, event_type: str) -> float:
        return self.weights.get(event_type, 1.0)
