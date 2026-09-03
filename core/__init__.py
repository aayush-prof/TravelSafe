"""
TravelSafe Core Module
======================

This package contains the core logic for the TravelSafe application:

- config.py        : Configuration constants and settings
- models.py        : Pydantic data models for type safety
- personas.py      : Traveler persona definitions and weighting logic
- news_client.py   : Functions to fetch news from APIs or sample data
- classifier.py    : NLP pipeline for event classification
- scoring.py       : Travel Safety Index computation logic
- ui_components.py : Shared UI components for multi-page app
- utils.py         : Helper and utility functions
- api_services.py  : Real-time API services (weather, crime)
- services/        : Centralized services (logging, PDF, cache, errors)

Usage:
    from core.config import SUPPORTED_CITIES
    from core.models import NewsItem, ClassifiedEvent
    from core.personas import get_all_personas
    from core.news_client import fetch_news_for_city
    from core.classifier import classify_news_list
    from core.scoring import compute_base_index, compute_persona_index
    from core.ui_components import render_page_header, get_city_safety_data
    from core.services import log_info, generate_safety_report
"""

# Package version
__version__ = "2.1.0"

# Expose key components for easier imports
from .config import SUPPORTED_CITIES, EVENT_TYPES, DEFAULT_PERSONA, DEFAULT_CITY
from .models import NewsItem, ClassifiedEvent, Persona, SafetyResult
from .personas import get_all_personas, apply_persona_weights, get_persona
from .news_client import fetch_news_for_city, get_data_source_info
from .classifier import classify_news_item, classify_news_list
from .scoring import compute_base_index, compute_persona_index, compute_safety_result, get_index_interpretation

# UI Components (for multi-page app)
from .ui_components import (
    get_city_safety_data,
    get_selected_city,
    get_selected_persona,
    render_page_header,
    render_metric_card,
    render_mini_card,
    render_footer,
    get_safety_status,
    get_dark_chart_layout,
    get_event_color_map,
    get_event_icon_map,
    filter_events_by_type,
    get_events_by_severity,
)

__all__ = [
    # Config
    "SUPPORTED_CITIES",
    "EVENT_TYPES", 
    "DEFAULT_PERSONA",
    "DEFAULT_CITY",
    # Models
    "NewsItem",
    "ClassifiedEvent",
    "Persona",
    "SafetyResult",
    # Personas
    "get_all_personas",
    "apply_persona_weights",
    "get_persona",
    # News
    "fetch_news_for_city",
    "get_data_source_info",
    # Classifier
    "classify_news_item",
    "classify_news_list",
    # Scoring
    "compute_base_index",
    "compute_persona_index",
    "compute_safety_result",
    "get_index_interpretation",
    # UI Components
    "get_city_safety_data",
    "get_selected_city",
    "get_selected_persona",
    "render_page_header",
    "render_metric_card",
    "render_mini_card",
    "render_footer",
    "get_safety_status",
    "get_dark_chart_layout",
    "get_event_color_map",
    "get_event_icon_map",
    "filter_events_by_type",
    "get_events_by_severity",
]
