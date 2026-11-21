"""
TravelSafe configuration
========================

Central place for city metadata, environment-driven settings and provider
configuration. Scoring parameters live in ``core/scoring_params.py``.

Environment variables (see ``.env.example``):

    NEWS_API_KEY          NewsAPI.org key (legacy alias: NEWSAPI_KEY)
    GNEWS_API_KEY         GNews.io key
    OPENWEATHER_API_KEY   OpenWeatherMap key (aliases: OPENWEATHERMAP_API_KEY, WEATHER_API_KEY, OWM_API_KEY)
    OPENAQ_API_KEY        OpenAQ v3 key (measured air quality, optional)
    OPEN_METEO_ENABLED / USGS_ENABLED / GDACS_ENABLED   keyless providers (default true)
    DATA_MODE             auto | live | sample   (default: auto)
    USE_LIVE_NEWS         legacy flag: False -> DATA_MODE=sample
    ENABLE_GOOGLE_NEWS_RSS  true/false (default true; keyless live news)
    NEWS_FETCH_LIMIT      articles requested per provider (default 30)
    CACHE_TIMEOUT         seconds to cache a successful analysis (default 900)
    CORS_ORIGINS          comma-separated browser origins (default localhost:3000)
"""

from __future__ import annotations

from typing import Dict, List, Optional

from .env import BACKEND_DIR, Settings, config_issues, refresh_settings, settings  # noqa: F401

APP_VERSION = "5.0.0"
METHODOLOGY_VERSION = "2026.11-r2"

# ---------------------------------------------------------------------------
# Cities
# ---------------------------------------------------------------------------

SUPPORTED_CITIES_INDIA: List[str] = [
    "Delhi", "Mumbai", "Bangalore", "Chennai", "Hyderabad", "Kolkata", "Pune",
    "Ahmedabad", "Jaipur", "Lucknow", "Chandigarh", "Kochi", "Patna", "Indore",
    "Bhopal", "Surat", "Vizag", "Coimbatore", "Guwahati", "Nagpur", "Goa",
    "Thiruvananthapuram", "Varanasi", "Amritsar", "Udaipur", "Mysore", "Agra",
    "Shimla", "Rishikesh", "Darjeeling",
]

SUPPORTED_CITIES_INTERNATIONAL: List[str] = [
    "Dubai", "Singapore", "London", "Paris", "New York", "Tokyo", "Bangkok",
    "Sydney", "Toronto", "Hong Kong", "Bali", "Amsterdam", "Rome", "Berlin",
    "Barcelona",
]

SUPPORTED_CITIES: List[str] = SUPPORTED_CITIES_INDIA + SUPPORTED_CITIES_INTERNATIONAL
DEFAULT_CITY = "Delhi"

# Alternate names used in news text. Used for location matching only.
CITY_ALIASES: Dict[str, List[str]] = {
    "Delhi": ["Delhi", "New Delhi", "Delhi NCR"],
    "Mumbai": ["Mumbai", "Bombay"],
    "Bangalore": ["Bangalore", "Bengaluru"],
    "Chennai": ["Chennai", "Madras"],
    "Hyderabad": ["Hyderabad", "Secunderabad"],
    "Kolkata": ["Kolkata", "Calcutta"],
    "Pune": ["Pune", "Poona"],
    "Vizag": ["Vizag", "Visakhapatnam"],
    "Mysore": ["Mysore", "Mysuru"],
    "Kochi": ["Kochi", "Cochin", "Ernakulam"],
    "Thiruvananthapuram": ["Thiruvananthapuram", "Trivandrum"],
    "Varanasi": ["Varanasi", "Banaras", "Benares"],
    "Goa": ["Goa", "Panaji", "Panjim"],
    "Guwahati": ["Guwahati", "Gauhati"],
    "Bali": ["Bali", "Denpasar"],
    "New York": ["New York", "NYC", "Manhattan", "Brooklyn"],
    "Hong Kong": ["Hong Kong"],
}

CITY_COUNTRIES: Dict[str, str] = {
    **{c: "India" for c in SUPPORTED_CITIES_INDIA},
    "Dubai": "United Arab Emirates", "Singapore": "Singapore", "London": "United Kingdom",
    "Paris": "France", "New York": "United States", "Tokyo": "Japan", "Bangkok": "Thailand",
    "Sydney": "Australia", "Toronto": "Canada", "Hong Kong": "Hong Kong SAR, China",
    "Bali": "Indonesia", "Amsterdam": "Netherlands", "Rome": "Italy", "Berlin": "Germany",
    "Barcelona": "Spain",
}

# Indian state / territory for each Indian city (region-level news matching).
CITY_STATES: Dict[str, str] = {
    "Delhi": "Delhi", "Mumbai": "Maharashtra", "Bangalore": "Karnataka",
    "Chennai": "Tamil Nadu", "Hyderabad": "Telangana", "Kolkata": "West Bengal",
    "Pune": "Maharashtra", "Ahmedabad": "Gujarat", "Jaipur": "Rajasthan",
    "Lucknow": "Uttar Pradesh", "Chandigarh": "Chandigarh", "Kochi": "Kerala",
    "Patna": "Bihar", "Indore": "Madhya Pradesh", "Bhopal": "Madhya Pradesh",
    "Surat": "Gujarat", "Vizag": "Andhra Pradesh", "Coimbatore": "Tamil Nadu",
    "Guwahati": "Assam", "Nagpur": "Maharashtra", "Goa": "Goa",
    "Thiruvananthapuram": "Kerala", "Varanasi": "Uttar Pradesh", "Amritsar": "Punjab",
    "Udaipur": "Rajasthan", "Mysore": "Karnataka", "Agra": "Uttar Pradesh",
    "Shimla": "Himachal Pradesh", "Rishikesh": "Uttarakhand", "Darjeeling": "West Bengal",
    "Dubai": "Dubai", "Bali": "Bali", "New York": "New York State",
}

CITY_AREAS: Dict[str, str] = {
    "Delhi": "North India", "Mumbai": "West India", "Bangalore": "South India",
    "Chennai": "South India", "Hyderabad": "South India", "Kolkata": "East India",
    "Pune": "West India", "Ahmedabad": "West India", "Jaipur": "North India",
    "Lucknow": "North India", "Chandigarh": "North India", "Kochi": "South India",
    "Patna": "East India", "Indore": "Central India", "Bhopal": "Central India",
    "Surat": "West India", "Vizag": "South India", "Coimbatore": "South India",
    "Guwahati": "Northeast India", "Nagpur": "Central India", "Goa": "West India",
    "Thiruvananthapuram": "South India", "Varanasi": "North India",
    "Amritsar": "North India", "Udaipur": "North India", "Mysore": "South India",
    "Agra": "North India", "Shimla": "North India", "Rishikesh": "North India",
    "Darjeeling": "East India",
    "Dubai": "Middle East", "Singapore": "Southeast Asia", "London": "Europe",
    "Paris": "Europe", "New York": "North America", "Tokyo": "East Asia",
    "Bangkok": "Southeast Asia", "Sydney": "Oceania", "Toronto": "North America",
    "Hong Kong": "East Asia", "Bali": "Southeast Asia", "Amsterdam": "Europe",
    "Rome": "Europe", "Berlin": "Europe", "Barcelona": "Europe",
}

CITY_COORDINATES: Dict[str, Dict[str, float]] = {
    "Delhi": {"lat": 28.6139, "lon": 77.2090}, "Mumbai": {"lat": 19.0760, "lon": 72.8777},
    "Bangalore": {"lat": 12.9716, "lon": 77.5946}, "Chennai": {"lat": 13.0827, "lon": 80.2707},
    "Hyderabad": {"lat": 17.3850, "lon": 78.4867}, "Kolkata": {"lat": 22.5726, "lon": 88.3639},
    "Pune": {"lat": 18.5204, "lon": 73.8567}, "Ahmedabad": {"lat": 23.0225, "lon": 72.5714},
    "Jaipur": {"lat": 26.9124, "lon": 75.7873}, "Lucknow": {"lat": 26.8467, "lon": 80.9462},
    "Chandigarh": {"lat": 30.7333, "lon": 76.7794}, "Kochi": {"lat": 9.9312, "lon": 76.2673},
    "Patna": {"lat": 25.5941, "lon": 85.1376}, "Indore": {"lat": 22.7196, "lon": 75.8577},
    "Bhopal": {"lat": 23.2599, "lon": 77.4126}, "Surat": {"lat": 21.1702, "lon": 72.8311},
    "Vizag": {"lat": 17.6868, "lon": 83.2185}, "Coimbatore": {"lat": 11.0168, "lon": 76.9558},
    "Guwahati": {"lat": 26.1445, "lon": 91.7362}, "Nagpur": {"lat": 21.1458, "lon": 79.0882},
    "Goa": {"lat": 15.2993, "lon": 74.1240},
    "Thiruvananthapuram": {"lat": 8.5241, "lon": 76.9366},
    "Varanasi": {"lat": 25.3176, "lon": 82.9739}, "Amritsar": {"lat": 31.6340, "lon": 74.8723},
    "Udaipur": {"lat": 24.5854, "lon": 73.7125}, "Mysore": {"lat": 12.2958, "lon": 76.6394},
    "Agra": {"lat": 27.1767, "lon": 78.0081}, "Shimla": {"lat": 31.1048, "lon": 77.1734},
    "Rishikesh": {"lat": 30.0869, "lon": 78.2676}, "Darjeeling": {"lat": 27.0360, "lon": 88.2627},
    "Dubai": {"lat": 25.2048, "lon": 55.2708}, "Singapore": {"lat": 1.3521, "lon": 103.8198},
    "London": {"lat": 51.5074, "lon": -0.1278}, "Paris": {"lat": 48.8566, "lon": 2.3522},
    "New York": {"lat": 40.7128, "lon": -74.0060}, "Tokyo": {"lat": 35.6762, "lon": 139.6503},
    "Bangkok": {"lat": 13.7563, "lon": 100.5018}, "Sydney": {"lat": -33.8688, "lon": 151.2093},
    "Toronto": {"lat": 43.6532, "lon": -79.3832}, "Hong Kong": {"lat": 22.3193, "lon": 114.1694},
    "Bali": {"lat": -8.6705, "lon": 115.2126}, "Amsterdam": {"lat": 52.3676, "lon": 4.9041},
    "Rome": {"lat": 41.9028, "lon": 12.4964}, "Berlin": {"lat": 52.5200, "lon": 13.4050},
    "Barcelona": {"lat": 41.3874, "lon": 2.1686},
}

# Event categories. "positive" and "neutral" are kept for context but never
# contribute to (or offset) risk.
RISK_CATEGORIES: List[str] = ["crime", "protest", "accident", "disaster", "weather"]
CONTEXT_CATEGORIES: List[str] = ["positive", "neutral"]
EVENT_TYPES: List[str] = RISK_CATEGORIES + CONTEXT_CATEGORIES

CATEGORY_LABELS: Dict[str, str] = {
    "crime": "Crime",
    "protest": "Protests & civil disruption",
    "accident": "Accidents & service disruption",
    "disaster": "Disasters & public health",
    "weather": "Weather",
    "positive": "Positive / civic",
    "neutral": "General news",
}

DEFAULT_PERSONA = "student"


def get_city_region(city: str) -> str:
    if city in SUPPORTED_CITIES_INDIA:
        return "India"
    if city in SUPPORTED_CITIES_INTERNATIONAL:
        return "International"
    return "Unknown"


def resolve_city(name: str) -> Optional[str]:
    """Return the canonical city name for a user-supplied name/alias/slug."""
    if not name:
        return None
    key = name.strip().lower().replace("-", " ").replace("_", " ")
    for city in SUPPORTED_CITIES:
        if city.lower() == key:
            return city
        for alias in CITY_ALIASES.get(city, []):
            if alias.lower() == key:
                return city
    return None


def city_slug(city: str) -> str:
    return city.lower().replace(" ", "-")


def city_aliases(city: str) -> List[str]:
    return CITY_ALIASES.get(city, [city])




# ---------------------------------------------------------------------------
# Reference metadata shown on City insights (static, factual)
# ---------------------------------------------------------------------------

CITY_TIMEZONES: Dict[str, str] = {
    **{c: "Asia/Kolkata" for c in SUPPORTED_CITIES_INDIA},
    "Dubai": "Asia/Dubai", "Singapore": "Asia/Singapore", "London": "Europe/London",
    "Paris": "Europe/Paris", "New York": "America/New_York", "Tokyo": "Asia/Tokyo",
    "Bangkok": "Asia/Bangkok", "Sydney": "Australia/Sydney", "Toronto": "America/Toronto",
    "Hong Kong": "Asia/Hong_Kong", "Bali": "Asia/Makassar", "Amsterdam": "Europe/Amsterdam",
    "Rome": "Europe/Rome", "Berlin": "Europe/Berlin", "Barcelona": "Europe/Madrid",
}

# National emergency numbers (official, widely published). Shown with a
# "confirm locally" note. Keys are values of CITY_COUNTRIES.
EMERGENCY_NUMBERS: Dict[str, List[Dict[str, str]]] = {
    "India": [{"service": "All emergencies", "number": "112"},
              {"service": "Ambulance", "number": "108"},
              {"service": "Women's helpline", "number": "1091"}],
    "United Arab Emirates": [{"service": "Police", "number": "999"},
                             {"service": "Ambulance", "number": "998"},
                             {"service": "Fire", "number": "997"}],
    "Singapore": [{"service": "Police", "number": "999"},
                  {"service": "Ambulance and fire", "number": "995"}],
    "United Kingdom": [{"service": "All emergencies", "number": "999 or 112"}],
    "France": [{"service": "All emergencies", "number": "112"},
               {"service": "Medical (SAMU)", "number": "15"},
               {"service": "Police", "number": "17"}],
    "United States": [{"service": "All emergencies", "number": "911"}],
    "Japan": [{"service": "Police", "number": "110"},
              {"service": "Fire and ambulance", "number": "119"}],
    "Thailand": [{"service": "Police", "number": "191"},
                 {"service": "Tourist police", "number": "1155"},
                 {"service": "Medical emergencies", "number": "1669"}],
    "Australia": [{"service": "All emergencies", "number": "000 (112 from mobiles)"}],
    "Canada": [{"service": "All emergencies", "number": "911"}],
    "Hong Kong SAR, China": [{"service": "All emergencies", "number": "999"}],
    "Indonesia": [{"service": "All emergencies", "number": "112"}],
    "Netherlands": [{"service": "All emergencies", "number": "112"}],
    "Italy": [{"service": "All emergencies", "number": "112"}],
    "Germany": [{"service": "All emergencies", "number": "112"},
                {"service": "Police", "number": "110"}],
    "Spain": [{"service": "All emergencies", "number": "112"}],
}
