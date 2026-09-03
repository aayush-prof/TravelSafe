"""
TravelSafe Data Models
======================

This module defines the Pydantic data models used throughout the TravelSafe
application. Using Pydantic provides:

1. Type validation - Ensures data conforms to expected types
2. Data parsing - Automatically converts compatible types
3. Serialization - Easy conversion to/from JSON
4. Documentation - Self-documenting data structures

Models defined:
- NewsItem: Raw news article from API or sample data
- ClassifiedEvent: News item after NLP classification
- Persona: Traveler profile with risk weights
- SafetyResult: Final safety analysis for a city
"""

from datetime import datetime
from typing import Dict, List, Optional, Literal
from pydantic import BaseModel, Field, field_validator


# Type alias for valid event types
# Using Literal ensures only these values are accepted
EventType = Literal["crime", "protest", "accident", "disaster", "weather", "positive", "neutral"]


class NewsItem(BaseModel):
    """
    Represents a raw news article fetched from an API or sample data.
    
    This is the input to the classification pipeline. Each news item
    contains the article text and metadata needed for processing.
    
    Attributes:
        title: Headline of the news article
        description: Brief summary or first paragraph (may be None)
        city: City this news is associated with
        source: Name of the news source/publisher
        published_at: When the article was published
        
    Example:
        >>> item = NewsItem(
        ...     title="Heavy rainfall causes flooding in Delhi",
        ...     description="Several areas waterlogged after 3 hours of rain",
        ...     city="Delhi",
        ...     source="Times of India",
        ...     published_at=datetime.now()
        ... )
    """
    
    title: str = Field(
        ...,  # Required field
        min_length=1,
        description="Headline of the news article"
    )
    
    description: Optional[str] = Field(
        default=None,
        description="Brief summary or first paragraph of the article"
    )
    
    city: str = Field(
        ...,
        min_length=1,
        description="City this news is associated with"
    )
    
    source: str = Field(
        default="Unknown",
        description="Name of the news source/publisher"
    )
    
    published_at: datetime = Field(
        default_factory=datetime.now,
        description="When the article was published"
    )
    
    @field_validator('title', 'city')
    @classmethod
    def strip_whitespace(cls, v: str) -> str:
        """Remove leading/trailing whitespace from string fields."""
        return v.strip()
    
    def get_full_text(self) -> str:
        """
        Combine title and description for classification.
        
        Returns:
            Combined text string for NLP processing
        """
        if self.description:
            return f"{self.title} {self.description}"
        return self.title
    
    class Config:
        """Pydantic model configuration."""
        json_schema_extra = {
            "example": {
                "title": "Two arrested in Bangalore ATM robbery case",
                "description": "Police apprehended suspects within 24 hours of the incident",
                "city": "Bangalore",
                "source": "Deccan Herald",
                "published_at": "2025-12-01T10:30:00"
            }
        }


class ClassifiedEvent(BaseModel):
    """
    Represents a news item after NLP classification.
    
    This model extends the raw NewsItem with classification results:
    - Event type (what kind of safety-relevant event)
    - Severity score (how impactful is this event)
    - Confidence (how sure is the classifier)
    
    Attributes:
        news_item: The original news article
        event_type: Category of the event (crime, protest, etc.)
        severity: Impact score from -3 (very bad) to +3 (positive)
        confidence: Classifier confidence from 0.0 to 1.0
        
    Example:
        >>> event = ClassifiedEvent(
        ...     news_item=news_item,
        ...     event_type="weather",
        ...     severity=-2,
        ...     confidence=0.85
        ... )
    """
    
    news_item: NewsItem = Field(
        ...,
        description="The original news article that was classified"
    )
    
    event_type: EventType = Field(
        ...,
        description="Category of the event"
    )
    
    severity: int = Field(
        ...,
        ge=-5,  # Greater than or equal to -5
        le=5,   # Less than or equal to 5
        description="Impact score from -5 (very negative) to +5 (very positive)"
    )
    
    confidence: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Classification confidence from 0.0 to 1.0"
    )
    
    def get_weighted_severity(self, weight: float = 1.0) -> float:
        """
        Calculate severity weighted by confidence and optional multiplier.
        
        Args:
            weight: Optional multiplier (e.g., from persona weights)
            
        Returns:
            Weighted severity score
        """
        return self.severity * self.confidence * weight
    
    class Config:
        """Pydantic model configuration."""
        json_schema_extra = {
            "example": {
                "news_item": {
                    "title": "Protest march disrupts traffic in Chennai",
                    "description": "Thousands gather for peaceful demonstration",
                    "city": "Chennai",
                    "source": "The Hindu",
                    "published_at": "2025-12-02T14:00:00"
                },
                "event_type": "protest",
                "severity": -1,
                "confidence": 0.92
            }
        }


class Persona(BaseModel):
    """
    Represents a traveler persona with specific risk preferences.
    
    Different travelers have different concerns. A solo female traveler
    may be more concerned about crime, while an elderly person may
    prioritize weather and health-related events. This model captures
    these preferences as weight multipliers.
    
    Attributes:
        name: Identifier for the persona (e.g., "solo_female")
        display_name: Human-readable name for UI
        description: Brief explanation of the persona
        weights: Multipliers for each event type (higher = more concern)
        
    Example:
        >>> persona = Persona(
        ...     name="family",
        ...     display_name="Family Traveler",
        ...     description="Traveling with children",
        ...     weights={"crime": 1.5, "protest": 1.4, ...}
        ... )
    """
    
    name: str = Field(
        ...,
        min_length=1,
        description="Unique identifier for the persona"
    )
    
    display_name: str = Field(
        ...,
        min_length=1,
        description="Human-readable name for display in UI"
    )
    
    description: str = Field(
        default="",
        description="Brief explanation of this traveler type"
    )
    
    weights: Dict[str, float] = Field(
        ...,
        description="Weight multipliers for each event type"
    )
    
    @field_validator('weights')
    @classmethod
    def validate_weights(cls, v: Dict[str, float]) -> Dict[str, float]:
        """Ensure all weights are positive numbers."""
        for event_type, weight in v.items():
            if weight < 0:
                raise ValueError(f"Weight for {event_type} must be non-negative")
        return v
    
    def get_weight(self, event_type: str) -> float:
        """
        Get the weight multiplier for a specific event type.
        
        Args:
            event_type: Type of event (crime, protest, etc.)
            
        Returns:
            Weight multiplier (defaults to 1.0 if not found)
        """
        return self.weights.get(event_type, 1.0)
    
    class Config:
        """Pydantic model configuration."""
        json_schema_extra = {
            "example": {
                "name": "solo_female",
                "display_name": "Solo Female Traveler",
                "description": "Women traveling alone",
                "weights": {
                    "crime": 1.8,
                    "protest": 1.3,
                    "accident": 1.0,
                    "disaster": 1.0,
                    "weather": 0.9,
                    "neutral": 1.0
                }
            }
        }


class SafetyResult(BaseModel):
    """
    Final safety analysis result for a city.
    
    This model contains all the computed safety metrics for display
    in the dashboard, including both base and persona-adjusted indices.
    
    Attributes:
        city: Name of the analyzed city
        base_index: Safety index without persona adjustment (-10 to +10)
        persona_index: Safety index adjusted for persona (-10 to +10)
        events: List of classified events used in calculation
        persona_name: Name of the persona used for adjustment
        event_counts: Count of events by type
        avg_severity: Average severity by event type
        
    Example:
        >>> result = SafetyResult(
        ...     city="Mumbai",
        ...     base_index=2.5,
        ...     persona_index=1.8,
        ...     events=[...],
        ...     persona_name="family"
        ... )
    """
    
    city: str = Field(
        ...,
        description="Name of the analyzed city"
    )
    
    base_index: float = Field(
        ...,
        ge=-10.0,
        le=10.0,
        description="Safety index without persona adjustment"
    )
    
    persona_index: float = Field(
        ...,
        ge=-10.0,
        le=10.0,
        description="Safety index adjusted for selected persona"
    )
    
    events: List[ClassifiedEvent] = Field(
        default_factory=list,
        description="List of classified events used in calculation"
    )
    
    persona_name: str = Field(
        ...,
        description="Name of the persona used for adjustment"
    )
    
    event_counts: Optional[Dict[str, int]] = Field(
        default=None,
        description="Count of events by type"
    )
    
    avg_severity: Optional[Dict[str, float]] = Field(
        default=None,
        description="Average severity by event type"
    )
    
    def get_total_events(self) -> int:
        """Return the total number of events analyzed."""
        return len(self.events)
    
    def get_event_breakdown(self) -> Dict[str, int]:
        """
        Count events by type.
        
        Returns:
            Dictionary mapping event_type to count
        """
        if self.event_counts:
            return self.event_counts
            
        counts: Dict[str, int] = {}
        for event in self.events:
            event_type = event.event_type
            counts[event_type] = counts.get(event_type, 0) + 1
        return counts
    
    class Config:
        """Pydantic model configuration."""
        json_schema_extra = {
            "example": {
                "city": "Hyderabad",
                "base_index": 3.25,
                "persona_index": 2.10,
                "events": [],
                "persona_name": "student",
                "event_counts": {
                    "crime": 3,
                    "weather": 2,
                    "neutral": 5
                }
            }
        }
