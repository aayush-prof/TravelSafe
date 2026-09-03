"""
TravelSafe Configuration Module
===============================

This module contains all configuration constants and settings for the
TravelSafe application. Centralizing configuration makes it easy to
modify settings without changing code across multiple files.

Constants defined here:
- SUPPORTED_CITIES: List of cities the app supports
- EVENT_TYPES: Categories for news classification
- SAFETY_INDEX_MIN/MAX: Bounds for the safety index
- DEFAULT_PERSONA: Default traveler persona
- USE_LIVE_NEWS: Flag to switch between sample and live data
- API configuration for news fetching
"""

import os
from typing import List
from dotenv import load_dotenv

# Load environment variables from .env file (if it exists)
load_dotenv()


# List of supported cities (30+ Indian and International cities)
# This list is editable - add or remove cities as needed
# Format: "City Name" (will be used for news search queries)

SUPPORTED_CITIES_INDIA = [
    "Delhi",
    "Mumbai",
    "Bangalore",
    "Chennai",
    "Hyderabad",
    "Kolkata",
    "Pune",
    "Ahmedabad",
    "Jaipur",
    "Lucknow",
    "Chandigarh",
    "Kochi",
    "Patna",
    "Indore",
    "Bhopal",
    "Surat",
    "Vizag",
    "Coimbatore",
    "Guwahati",
    "Nagpur",
    "Goa",
    "Thiruvananthapuram",
    "Varanasi",
    "Amritsar",
    "Udaipur",
    "Mysore",
    "Agra",
    "Shimla",
    "Rishikesh",
    "Darjeeling",
]

SUPPORTED_CITIES_INTERNATIONAL = [
    "Dubai",
    "Singapore",
    "London",
    "Paris",
    "New York",
    "Tokyo",
    "Bangkok",
    "Sydney",
    "Toronto",
    "Hong Kong",
    "Bali",
    "Amsterdam",
    "Rome",
    "Berlin",
    "Barcelona",
]

# Combined list of all supported cities
SUPPORTED_CITIES: List[str] = SUPPORTED_CITIES_INDIA + SUPPORTED_CITIES_INTERNATIONAL

# Default city to show when the app loads
DEFAULT_CITY: str = "Delhi"


def add_city(city_name: str, is_international: bool = False) -> bool:
    """
    Add a new city to the supported cities list.
    
    Args:
        city_name: Name of the city to add
        is_international: True if international city, False for Indian
        
    Returns:
        True if added successfully, False if already exists
    """
    global SUPPORTED_CITIES
    if city_name not in SUPPORTED_CITIES:
        if is_international:
            SUPPORTED_CITIES_INTERNATIONAL.append(city_name)
        else:
            SUPPORTED_CITIES_INDIA.append(city_name)
        SUPPORTED_CITIES = SUPPORTED_CITIES_INDIA + SUPPORTED_CITIES_INTERNATIONAL
        return True
    return False


def remove_city(city_name: str) -> bool:
    """
    Remove a city from the supported cities list.
    
    Args:
        city_name: Name of the city to remove
        
    Returns:
        True if removed successfully, False if not found
    """
    global SUPPORTED_CITIES
    if city_name in SUPPORTED_CITIES_INDIA:
        SUPPORTED_CITIES_INDIA.remove(city_name)
        SUPPORTED_CITIES = SUPPORTED_CITIES_INDIA + SUPPORTED_CITIES_INTERNATIONAL
        return True
    elif city_name in SUPPORTED_CITIES_INTERNATIONAL:
        SUPPORTED_CITIES_INTERNATIONAL.remove(city_name)
        SUPPORTED_CITIES = SUPPORTED_CITIES_INDIA + SUPPORTED_CITIES_INTERNATIONAL
        return True
    return False


def get_city_region(city_name: str) -> str:
    """
    Get the region (India/International) for a city.
    
    Args:
        city_name: Name of the city
        
    Returns:
        'India', 'International', or 'Unknown'
    """
    if city_name in SUPPORTED_CITIES_INDIA:
        return "India"
    elif city_name in SUPPORTED_CITIES_INTERNATIONAL:
        return "International"
    return "Unknown"


# Event types for news classification
# Each news item will be classified into one of these categories
EVENT_TYPES: List[str] = [
    "crime",      # Murders, theft, assault, robbery, etc.
    "protest",    # Rallies, strikes, demonstrations, riots
    "accident",   # Road accidents, fires, industrial accidents
    "disaster",   # Earthquakes, floods, cyclones, natural disasters
    "weather",    # Storms, heatwaves, heavy rain, fog
    "positive",   # Festivals, achievements, tourism, celebrations
    "neutral"     # General news, non-safety-related
]

# Human-readable labels for event types (for UI display)
EVENT_TYPE_LABELS = {
    "crime": "🚨 Crime",
    "protest": "📢 Protest",
    "accident": "🚗 Accident",
    "disaster": "🌊 Disaster",
    "weather": "🌧️ Weather",
    "positive": "🎉 Positive",
    "neutral": "📰 Neutral"
}

# Colors for event types (for charts)
EVENT_TYPE_COLORS = {
    "crime": "#e74c3c",      # Red
    "protest": "#f39c12",    # Orange
    "accident": "#9b59b6",   # Purple
    "disaster": "#c0392b",   # Dark Red
    "weather": "#3498db",    # Blue
    "positive": "#27ae60",   # Green
    "neutral": "#95a5a6"     # Gray
}


# Safety index bounds
# The final safety index will always be within this range
SAFETY_INDEX_MIN: float = -10.0  # Very unsafe
SAFETY_INDEX_MAX: float = 10.0   # Very safe

# Severity score bounds (per individual event)
SEVERITY_MIN: int = -5  # Very negative event
SEVERITY_MAX: int = 5   # Very positive event

# Thresholds for interpreting safety index
# Used to display risk level text in the UI
SAFETY_THRESHOLDS = {
    "very_safe": 7.0,      # Index >= 7.0
    "safe": 4.0,           # Index >= 4.0
    "moderate": 0.0,       # Index >= 0.0
    "risky": -4.0,         # Index >= -4.0
    "very_risky": -7.0,    # Index >= -7.0
    # Below -7.0 is "dangerous"
}


# Default traveler persona when app loads
DEFAULT_PERSONA: str = "student"

# List of all available personas
AVAILABLE_PERSONAS: List[str] = [
    "student",
    "solo_female",
    "family",
    "backpacker",
    "elderly"
]


# Flag to switch between sample data and live API
# Set to True to fetch real news (requires API key)
# Set to False to use sample_data/sample_news.json
USE_LIVE_NEWS: bool = False

# News API configuration
# We use NewsAPI.org as an example, but this can be changed
NEWS_API_KEY: str = os.getenv("NEWS_API_KEY", "")
NEWS_API_BASE_URL: str = "https://newsapi.org/v2/everything"

# Number of news articles to fetch per city
NEWS_FETCH_LIMIT: int = 20

# Path to sample news data (relative to project root)
SAMPLE_NEWS_PATH: str = "sample_data/sample_news.json"


# Streamlit page configuration
APP_TITLE: str = "TravelSafe - City Travel Safety Index"
APP_ICON: str = "🌍"
APP_LAYOUT: str = "wide"

# Cache timeout for news data (in seconds)
# Set to 0 to disable caching
CACHE_TIMEOUT: int = 300  # 5 minutes


# API Key names and their requirements
API_KEY_CONFIG = {
    "GNEWS_API_KEY": {"required": False, "module": "news"},
    "NEWSDATA_API_KEY": {"required": False, "module": "news"},
    "OPENWEATHER_API_KEY": {"required": False, "module": "weather"},
    "NEWSAPI_KEY": {"required": False, "module": "news"},
    "GOOGLE_MAPS_API_KEY": {"required": False, "module": "maps"},
}


def check_api_keys() -> dict:
    """
    Check availability of all API keys from environment variables.
    
    Returns:
        Dictionary containing:
        - 'keys': Dict mapping key names to True/False availability
        - 'live_mode': Dict mapping modules to True/False based on key availability
        - 'any_news_key': True if any news API key is available
        - 'weather_available': True if weather API key is available
        
    Example:
        >>> status = check_api_keys()
        >>> status['keys']['OPENWEATHER_API_KEY']
        True
        >>> status['live_mode']['weather']
        True
    """
    key_status = {}
    
    # Check each API key
    for key_name in API_KEY_CONFIG:
        value = os.getenv(key_name, "").strip()
        # Key is valid if it exists and is not empty/placeholder
        is_valid = bool(value) and value not in ["", "your_api_key_here", "YOUR_API_KEY", "xxx"]
        key_status[key_name] = is_valid
    
    # Determine live mode for each module
    live_mode = {
        "news": any([
            key_status.get("GNEWS_API_KEY", False),
            key_status.get("NEWSDATA_API_KEY", False),
            key_status.get("NEWSAPI_KEY", False),
        ]),
        "weather": key_status.get("OPENWEATHER_API_KEY", False),
        "maps": key_status.get("GOOGLE_MAPS_API_KEY", False),
    }
    
    return {
        "keys": key_status,
        "live_mode": live_mode,
        "any_news_key": live_mode["news"],
        "weather_available": live_mode["weather"],
    }


def get_api_status_for_module(module: str) -> tuple:
    """
    Get API availability status for a specific module.
    
    Args:
        module: Module name ('news', 'weather', 'maps', 'crime')
        
    Returns:
        Tuple of (is_live: bool, status_text: str, status_color: str)
        
    Example:
        >>> is_live, text, color = get_api_status_for_module('weather')
        >>> print(f"{text}")  # "Live API" or "Sample Data"
    """
    status = check_api_keys()
    
    # Crime module uses news API
    if module == "crime":
        module = "news"
    
    is_live = status["live_mode"].get(module, False)
    
    if is_live:
        return True, "Live API", "#10b981"  # Green
    else:
        return False, "Sample Data", "#f59e0b"  # Yellow/Orange


def get_risk_level(index: float) -> str:
    """
    Convert a safety index value to a human-readable risk level.
    
    Args:
        index: Safety index value between -10 and 10
        
    Returns:
        String describing the risk level
        
    Example:
        >>> get_risk_level(5.5)
        'Safe'
        >>> get_risk_level(-8.0)
        'Dangerous'
    """
    if index >= SAFETY_THRESHOLDS["very_safe"]:
        return "Very Safe"
    elif index >= SAFETY_THRESHOLDS["safe"]:
        return "Safe"
    elif index >= SAFETY_THRESHOLDS["moderate"]:
        return "Moderate Risk"
    elif index >= SAFETY_THRESHOLDS["risky"]:
        return "Risky"
    elif index >= SAFETY_THRESHOLDS["very_risky"]:
        return "Very Risky"
    else:
        return "Dangerous"


def get_risk_color(index: float) -> str:
    """
    Get a color code based on the safety index value.
    Used for UI elements to visually indicate risk level.
    
    Args:
        index: Safety index value between -10 and 10
        
    Returns:
        Hex color code string
        
    Example:
        >>> get_risk_color(5.5)
        '#27ae60'  # Green
    """
    if index >= SAFETY_THRESHOLDS["very_safe"]:
        return "#27ae60"  # Green
    elif index >= SAFETY_THRESHOLDS["safe"]:
        return "#2ecc71"  # Light Green
    elif index >= SAFETY_THRESHOLDS["moderate"]:
        return "#f1c40f"  # Yellow
    elif index >= SAFETY_THRESHOLDS["risky"]:
        return "#e67e22"  # Orange
    elif index >= SAFETY_THRESHOLDS["very_risky"]:
        return "#e74c3c"  # Red
    else:
        return "#c0392b"  # Dark Red
