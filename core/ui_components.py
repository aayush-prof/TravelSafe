"""
TravelSafe Shared UI Components
================================

Reusable UI components and helper functions shared across all pages.
This module centralizes common rendering logic to avoid duplication.

Components:
- apply_page_config: Apply page-specific configuration
- render_page_header: Render consistent page headers
- get_safety_data: Cached data fetching
- render_metric_card: Reusable metric card component
- get_chart_config: Plotly chart configurations
- render_footer: Footer with data source indicator
"""

import streamlit as st
from datetime import datetime
from typing import Tuple, Optional
import plotly.graph_objects as go

from .config import (
    SUPPORTED_CITIES,
    DEFAULT_CITY,
    DEFAULT_PERSONA,
    EVENT_TYPES,
    EVENT_TYPE_LABELS,
    EVENT_TYPE_COLORS,
    check_api_keys,
    get_api_status_for_module,
)
from .models import SafetyResult
from .personas import get_all_personas, get_persona
from .news_client import fetch_news_for_city, get_data_source_info
from .classifier import classify_news_list
from .scoring import compute_safety_result, get_index_interpretation


@st.cache_data(ttl=300, show_spinner=False)
def get_city_safety_data(city: str, persona_name: str) -> SafetyResult:
    """
    Fetch and process safety data for a city.
    Cached to avoid repeated API calls (5 min TTL).
    """
    news_items = fetch_news_for_city(city)
    classified_events = classify_news_list(news_items)
    # Keep a consolidated list of all classified events across pages
    st.session_state["all_events"] = st.session_state.get("all_events", []) + classified_events
    persona = get_persona(persona_name)
    result = compute_safety_result(city, classified_events, persona)
    return result


def get_selected_city() -> str:
    """Get currently selected city from session state."""
    return st.session_state.get('selected_city', DEFAULT_CITY)


def get_selected_persona() -> str:
    """Get currently selected persona from session state."""
    return st.session_state.get('selected_persona', DEFAULT_PERSONA)


def render_page_header(title: str, subtitle: str, icon: str = "🛡️"):
    """
    Render a consistent page header across all pages.
    
    Args:
        title: Main page title
        subtitle: Subtitle/description
        icon: Emoji icon for the page
    """
    city = get_selected_city()
    persona = get_selected_persona()
    
    persona_labels = {
        "student": "🎓 Student",
        "solo_female": "👩 Solo Female",
        "family": "👨‍👩‍👧‍👦 Family",
        "backpacker": "🎒 Backpacker",
        "elderly": "👴 Senior",
    }
    
    st.markdown(f"""
    <div class="main-header animate-fade-in">
        <div class="page-header">{icon} {title}</div>
        <div class="header-divider"></div>
        <div class="page-subheader">{subtitle}</div>
    </div>
    """, unsafe_allow_html=True)
    
    # City and Persona Badges
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.markdown(f"""
        <div style="text-align: center; margin-bottom: 2rem;">
            <span class="city-badge">📍 {city}</span>
            &nbsp;&nbsp;
            <span class="persona-badge">{persona_labels.get(persona, persona)}</span>
        </div>
        """, unsafe_allow_html=True)


def get_safety_status(index: float) -> Tuple[str, str, str, str]:
    """
    Return status info based on safety index.
    Aligned with scoring.py thresholds.
    
    Returns:
        Tuple of (status_text, color, card_class, icon)
    """
    if index >= 6:
        return "VERY SAFE", "#10b981", "metric-card-safe", "✅"
    elif index >= 2:
        return "SAFE", "#34d399", "metric-card-safe", "👍"
    elif index >= 0:
        return "LOW RISK", "#a3e635", "metric-card-warning", "🟢"
    elif index >= -3:
        return "MODERATE", "#f59e0b", "metric-card-warning", "⚠️"
    elif index >= -6:
        return "RISKY", "#f97316", "metric-card-danger", "🟠"
    elif index >= -8:
        return "HIGH RISK", "#ef4444", "metric-card-danger", "🚨"
    else:
        return "SEVERE / DANGEROUS", "#b91c1c", "metric-card-danger", "⛔"


def render_metric_card(
    label: str,
    value: str,
    delta: Optional[str] = None,
    delta_type: str = "neutral",
    color: str = "#a8d8ff",
    card_class: str = ""
):
    """
    Render a premium metric card.
    
    Args:
        label: Card label/title
        value: Main value to display
        delta: Optional delta/change text
        delta_type: "positive", "negative", or "neutral"
        color: Color for the value
        card_class: Additional CSS class (e.g., "metric-card-safe")
    """
    delta_class = {
        "positive": "delta-positive",
        "negative": "delta-negative",
        "neutral": ""
    }.get(delta_type, "")
    
    delta_html = f'<div class="metric-delta {delta_class}">{delta}</div>' if delta else ""
    
    st.markdown(f"""
    <div class="metric-card {card_class}">
        <div class="metric-label">{label}</div>
        <div class="metric-value" style="color: {color};">{value}</div>
        {delta_html}
    </div>
    """, unsafe_allow_html=True)


def render_mini_card(icon: str, title: str, value: str, subtitle: str, color: str = "#6b7280"):
    """Render a smaller category card."""
    st.markdown(f"""
    <div class="metric-card" style="text-align: center; padding: 1rem;">
        <div style="font-size: 2rem; margin-bottom: 0.5rem;">{icon}</div>
        <div style="font-weight: 600; color: {color}; text-transform: capitalize; font-size: 0.85rem;">{title}</div>
        <div style="font-size: 1.5rem; font-weight: 700; color: #fff; margin: 0.5rem 0;">{value}</div>
        <div style="font-size: 0.75rem; color: #888;">{subtitle}</div>
    </div>
    """, unsafe_allow_html=True)


def get_dark_chart_layout(title: str = "", height: int = 400) -> dict:
    """
    Get standard dark theme layout for Plotly charts.
    
    Args:
        title: Chart title
        height: Chart height in pixels
        
    Returns:
        Layout dictionary for Plotly
    """
    return dict(
        title=dict(text=title, font=dict(size=16, color="#fff"), x=0.5) if title else None,
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(color="#fff"),
        margin=dict(t=60, b=60, l=60, r=20),
        height=height,
        xaxis=dict(gridcolor="rgba(255,255,255,0.1)"),
        yaxis=dict(gridcolor="rgba(255,255,255,0.1)"),
    )


def get_event_color_map() -> dict:
    """Get consistent color mapping for event types."""
    return {
        "crime": "#ef4444",
        "protest": "#f97316",
        "accident": "#eab308",
        "disaster": "#dc2626",
        "weather": "#3b82f6",
        "positive": "#10b981",
        "neutral": "#6b7280",
    }


def get_event_icon_map() -> dict:
    """Get consistent icon mapping for event types."""
    return {
        "crime": "🚔",
        "protest": "📢",
        "accident": "🚗",
        "disaster": "🌪️",
        "weather": "⛈️",
        "positive": "🎉",
        "neutral": "📰",
    }


def render_data_source_badge(module: str = "news"):
    """
    Render a small data source indicator badge.
    
    Args:
        module: Module name ('news', 'weather', 'crime', 'maps')
    """
    is_live, status_text, color = get_api_status_for_module(module)
    
    icon = "🟢" if is_live else "🟡"
    
    st.markdown(f"""
    <div style="display: inline-flex; align-items: center; gap: 0.4rem; 
                background: rgba(255,255,255,0.05); padding: 0.35rem 0.75rem; 
                border-radius: 20px; border: 1px solid {color}40;">
        <span style="font-size: 0.7rem;">{icon}</span>
        <span style="color: {color}; font-size: 0.75rem; font-weight: 500;">Data: {status_text}</span>
    </div>
    """, unsafe_allow_html=True)


def render_footer(module: str = "news"):
    """
    Render consistent footer across all pages with data source indicator.
    
    Args:
        module: Module name for API status ('news', 'weather', 'crime')
    """
    is_live, status_text, color = get_api_status_for_module(module)
    icon = "🟢" if is_live else "🟡"
    
    st.markdown("---")
    st.markdown(f"""
    <div style="text-align: center; padding: 1rem 0; color: #666;">
        <div style="font-size: 0.9rem; margin-bottom: 0.5rem;">
            🛡️ <strong>TravelSafe</strong> — Your AI-powered travel safety companion
        </div>
        <div style="font-size: 0.75rem; margin-bottom: 0.75rem;">
            Data refreshes every 5 minutes • Powered by real-time news analysis
        </div>
        <div style="display: inline-flex; align-items: center; gap: 0.4rem; 
                    background: rgba(255,255,255,0.05); padding: 0.35rem 0.85rem; 
                    border-radius: 20px; border: 1px solid {color}40;">
            <span style="font-size: 0.75rem;">{icon}</span>
            <span style="color: {color}; font-size: 0.8rem; font-weight: 500;">Data source: {status_text}</span>
        </div>
    </div>
    """, unsafe_allow_html=True)


def filter_events_by_type(result: SafetyResult, event_types: list) -> list:
    """
    Filter events by specified types.
    
    Args:
        result: SafetyResult object
        event_types: List of event types to include
        
    Returns:
        Filtered list of ClassifiedEvent objects
    """
    return [e for e in result.events if e.event_type in event_types]


def get_events_by_severity(result: SafetyResult, min_sev: int = -3, max_sev: int = 3) -> list:
    """
    Filter events by severity range.
    
    Args:
        result: SafetyResult object
        min_sev: Minimum severity (inclusive)
        max_sev: Maximum severity (inclusive)
        
    Returns:
        Filtered list of ClassifiedEvent objects
    """
    return [e for e in result.events if min_sev <= e.severity <= max_sev]
