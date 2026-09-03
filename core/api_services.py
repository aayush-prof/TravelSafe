"""
TravelSafe - Real-time API Services
=====================================

Centralized API service layer for real-time data fetching.
Implements caching, error handling, and fallback mechanisms.

APIs:
- Weather: OpenWeatherMap (current conditions + alerts)
- Crime News: GNews API / Google News RSS (filtered by crime keywords)

All responses are cached for 15 minutes using st.cache_data.
Fallback to local sample data if API calls fail.
"""

import os
import requests
import streamlit as st
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
from dataclasses import dataclass
import xml.etree.ElementTree as ET
from urllib.parse import quote_plus
import random
import time
from collections import Counter

# Load environment variables from .env file
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # dotenv not installed, use system env vars

# Import logging (with fallback if services not yet created)
try:
    from .services.logger import log_info, log_error, log_warning, log_api_call
except ImportError:
    def log_info(msg, module="api"): pass
    def log_error(msg, module="api", exc=None): pass
    def log_warning(msg, module="api"): pass
    def log_api_call(api, city, success, duration=None): pass

# Import config for API key validation
from .config import check_api_keys, get_api_status_for_module, DEFAULT_PERSONA, EVENT_TYPES, SAFETY_INDEX_MIN, SAFETY_INDEX_MAX, SEVERITY_MIN, SEVERITY_MAX
from .personas import get_persona
from .news_client import fetch_news_for_city
from .classifier import classify_news_list
from .scoring import compute_safety_result, compute_base_index, compute_persona_index
from .models import SafetyResult, ClassifiedEvent
from .utils import clamp_value

OPENWEATHER_API_KEY = os.getenv("OPENWEATHER_API_KEY", "")
GNEWS_API_KEY = os.getenv("GNEWS_API_KEY", "")

# Cache TTL (15 minutes)
CACHE_TTL_SECONDS = 900

# API Endpoints
OPENWEATHER_CURRENT_URL = "https://api.openweathermap.org/data/2.5/weather"
OPENWEATHER_ONECALL_URL = "https://api.openweathermap.org/data/3.0/onecall"
GNEWS_API_URL = "https://gnews.io/api/v4/search"
GOOGLE_NEWS_RSS_URL = "https://news.google.com/rss/search"

# Crime keywords for filtering news
CRIME_KEYWORDS = [
    "crime", "murder", "robbery", "theft", "assault", "arrest",
    "police", "shooting", "stabbing", "burglary", "kidnap",
    "fraud", "scam", "drug", "gang", "violence", "attack"
]

# City coordinates for weather API
CITY_COORDINATES = {
    # Indian Cities
    "Delhi": {"lat": 28.6139, "lon": 77.2090},
    "Mumbai": {"lat": 19.0760, "lon": 72.8777},
    "Bangalore": {"lat": 12.9716, "lon": 77.5946},
    "Chennai": {"lat": 13.0827, "lon": 80.2707},
    "Kolkata": {"lat": 22.5726, "lon": 88.3639},
    "Hyderabad": {"lat": 17.3850, "lon": 78.4867},
    "Pune": {"lat": 18.5204, "lon": 73.8567},
    "Ahmedabad": {"lat": 23.0225, "lon": 72.5714},
    "Jaipur": {"lat": 26.9124, "lon": 75.7873},
    "Lucknow": {"lat": 26.8467, "lon": 80.9462},
    "Chandigarh": {"lat": 30.7333, "lon": 76.7794},
    "Goa": {"lat": 15.2993, "lon": 74.1240},
    "Kochi": {"lat": 9.9312, "lon": 76.2673},
    "Varanasi": {"lat": 25.3176, "lon": 82.9739},
    "Amritsar": {"lat": 31.6340, "lon": 74.8723},
    "Udaipur": {"lat": 24.5854, "lon": 73.7125},
    "Shimla": {"lat": 31.1048, "lon": 77.1734},
    "Darjeeling": {"lat": 27.0360, "lon": 88.2627},
    "Rishikesh": {"lat": 30.0869, "lon": 78.2676},
    "Mysore": {"lat": 12.2958, "lon": 76.6394},
    # International Cities
    "New York": {"lat": 40.7128, "lon": -74.0060},
    "London": {"lat": 51.5074, "lon": -0.1278},
    "Paris": {"lat": 48.8566, "lon": 2.3522},
    "Tokyo": {"lat": 35.6762, "lon": 139.6503},
    "Singapore": {"lat": 1.3521, "lon": 103.8198},
    "Dubai": {"lat": 25.2048, "lon": 55.2708},
    "Sydney": {"lat": -33.8688, "lon": 151.2093},
    "Bangkok": {"lat": 13.7563, "lon": 100.5018},
    "Hong Kong": {"lat": 22.3193, "lon": 114.1694},
    "Los Angeles": {"lat": 34.0522, "lon": -118.2437},
    "San Francisco": {"lat": 37.7749, "lon": -122.4194},
    "Toronto": {"lat": 43.6532, "lon": -79.3832},
    "Berlin": {"lat": 52.5200, "lon": 13.4050},
    "Amsterdam": {"lat": 52.3676, "lon": 4.9041},
    "Rome": {"lat": 41.9028, "lon": 12.4964},
}


@dataclass
class WeatherData:
    """Weather data structure."""
    city: str
    temperature: float
    feels_like: float
    humidity: int
    wind_speed: float
    description: str
    icon: str
    visibility: int
    pressure: int
    clouds: int
    sunrise: str
    sunset: str
    alerts: List[Dict[str, Any]]
    fetched_at: str
    source: str


@dataclass
class CrimeNewsItem:
    """Crime news item structure."""
    title: str
    description: str
    url: str
    source: str
    published_at: str
    image_url: Optional[str] = None


@dataclass
class CrimeData:
    """Crime data structure."""
    city: str
    news_items: List[CrimeNewsItem]
    total_count: int
    fetched_at: str
    source: str


@st.cache_data(ttl=CACHE_TTL_SECONDS, show_spinner=False)
def fetch_weather_data(city: str) -> WeatherData:
    """
    Fetch real-time weather data from OpenWeatherMap API.
    
    Args:
        city: City name to fetch weather for
        
    Returns:
        WeatherData object with current conditions and alerts
        
    Notes:
        - Cached for 15 minutes
        - Falls back to sample data if API fails or key not configured
    """
    start_time = time.time()
    
    # Check API key availability first
    api_status = check_api_keys()
    if not api_status["weather_available"]:
        log_warning("OpenWeatherMap API key not configured - using sample data", module="weather")
        return _generate_sample_weather(city, "API key not configured - using sample data")
    
    # Try to get coordinates for the city
    coords = CITY_COORDINATES.get(city)
    
    if not coords:
        # Try geocoding API if coordinates not in our list
        coords = _geocode_city(city)
    
    if not coords:
        log_warning(f"City coordinates not found: {city}", module="weather")
        return _generate_sample_weather(city, "City not found - using sample data")
    
    try:
        # Fetch current weather
        params = {
            "lat": coords["lat"],
            "lon": coords["lon"],
            "appid": OPENWEATHER_API_KEY,
            "units": "metric"
        }
        
        response = requests.get(OPENWEATHER_CURRENT_URL, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        duration_ms = (time.time() - start_time) * 1000
        log_api_call("OpenWeatherMap", city, True, duration_ms)
        
        # Parse weather data
        weather = WeatherData(
            city=city,
            temperature=round(data["main"]["temp"], 1),
            feels_like=round(data["main"]["feels_like"], 1),
            humidity=data["main"]["humidity"],
            wind_speed=round(data["wind"]["speed"] * 3.6, 1),  # Convert m/s to km/h
            description=data["weather"][0]["description"].title(),
            icon=_get_weather_icon(data["weather"][0]["icon"]),
            visibility=data.get("visibility", 10000) // 1000,  # Convert to km
            pressure=data["main"]["pressure"],
            clouds=data["clouds"]["all"],
            sunrise=datetime.fromtimestamp(data["sys"]["sunrise"]).strftime("%H:%M"),
            sunset=datetime.fromtimestamp(data["sys"]["sunset"]).strftime("%H:%M"),
            alerts=_fetch_weather_alerts(coords["lat"], coords["lon"]),
            fetched_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            source="OpenWeatherMap API"
        )
        
        return weather
        
    except requests.exceptions.Timeout:
        duration_ms = (time.time() - start_time) * 1000
        log_api_call("OpenWeatherMap", city, False, duration_ms)
        log_error(f"Weather API timeout for {city}", module="weather")
        return _generate_sample_weather(city, "API timeout - using sample data")
    except requests.exceptions.RequestException as e:
        duration_ms = (time.time() - start_time) * 1000
        log_api_call("OpenWeatherMap", city, False, duration_ms)
        log_error(f"Weather API error for {city}", module="weather", exc=e)
        return _generate_sample_weather(city, f"API error: {str(e)[:50]}")
    except (KeyError, ValueError) as e:
        log_error(f"Weather data parsing error for {city}", module="weather", exc=e)
        return _generate_sample_weather(city, f"Data parsing error: {str(e)[:50]}")


def _fetch_weather_alerts(lat: float, lon: float) -> List[Dict[str, Any]]:
    """
    Fetch weather alerts using OneCall API (if available).
    Falls back to empty list if not available.
    """
    if not OPENWEATHER_API_KEY:
        return []
    
    try:
        params = {
            "lat": lat,
            "lon": lon,
            "appid": OPENWEATHER_API_KEY,
            "exclude": "minutely,hourly,daily"
        }
        
        response = requests.get(OPENWEATHER_ONECALL_URL, params=params, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            alerts = data.get("alerts", [])
            
            return [
                {
                    "event": alert.get("event", "Weather Alert"),
                    "sender": alert.get("sender_name", "Weather Service"),
                    "start": datetime.fromtimestamp(alert.get("start", 0)).strftime("%Y-%m-%d %H:%M"),
                    "end": datetime.fromtimestamp(alert.get("end", 0)).strftime("%Y-%m-%d %H:%M"),
                    "description": alert.get("description", "")[:200]
                }
                for alert in alerts[:5]  # Limit to 5 alerts
            ]
        
        return []
        
    except Exception:
        return []


def _geocode_city(city: str) -> Optional[Dict[str, float]]:
    """
    Geocode a city name to coordinates using OpenWeatherMap Geo API.
    """
    if not OPENWEATHER_API_KEY:
        return None
    
    try:
        url = f"http://api.openweathermap.org/geo/1.0/direct"
        params = {
            "q": city,
            "limit": 1,
            "appid": OPENWEATHER_API_KEY
        }
        
        response = requests.get(url, params=params, timeout=5)
        response.raise_for_status()
        data = response.json()
        
        if data:
            return {"lat": data[0]["lat"], "lon": data[0]["lon"]}
        
        return None
        
    except Exception:
        return None


def _get_weather_icon(icon_code: str) -> str:
    """Map OpenWeatherMap icon codes to emoji."""
    icon_map = {
        "01d": "☀️", "01n": "🌙",  # Clear
        "02d": "⛅", "02n": "☁️",  # Few clouds
        "03d": "☁️", "03n": "☁️",  # Scattered clouds
        "04d": "☁️", "04n": "☁️",  # Broken clouds
        "09d": "🌧️", "09n": "🌧️",  # Shower rain
        "10d": "🌦️", "10n": "🌧️",  # Rain
        "11d": "⛈️", "11n": "⛈️",  # Thunderstorm
        "13d": "🌨️", "13n": "🌨️",  # Snow
        "50d": "🌫️", "50n": "🌫️",  # Mist
    }
    return icon_map.get(icon_code, "🌡️")


def _generate_sample_weather(city: str, reason: str) -> WeatherData:
    """
    Generate sample weather data when API is unavailable.
    Uses realistic randomized values.
    """
    # Base temperature varies by rough latitude estimation
    base_temp = 25  # Default tropical
    
    if city in ["Delhi", "Jaipur", "Lucknow", "Varanasi"]:
        base_temp = random.randint(20, 35)
    elif city in ["Mumbai", "Chennai", "Kolkata", "Hyderabad"]:
        base_temp = random.randint(25, 32)
    elif city in ["Bangalore", "Pune"]:
        base_temp = random.randint(22, 28)
    elif city in ["Shimla", "Darjeeling"]:
        base_temp = random.randint(10, 20)
    elif city in ["London", "Paris", "Berlin", "Amsterdam"]:
        base_temp = random.randint(8, 18)
    elif city in ["New York", "Toronto"]:
        base_temp = random.randint(5, 20)
    elif city in ["Tokyo", "Hong Kong"]:
        base_temp = random.randint(15, 28)
    elif city in ["Singapore", "Bangkok", "Dubai"]:
        base_temp = random.randint(28, 35)
    else:
        base_temp = random.randint(20, 30)
    
    conditions = [
        ("Clear Sky", "☀️"),
        ("Partly Cloudy", "⛅"),
        ("Cloudy", "☁️"),
        ("Light Rain", "🌧️"),
        ("Humid", "💧"),
    ]
    
    condition = random.choice(conditions)
    
    return WeatherData(
        city=city,
        temperature=base_temp + random.uniform(-2, 2),
        feels_like=base_temp + random.uniform(-1, 3),
        humidity=random.randint(40, 85),
        wind_speed=random.uniform(5, 25),
        description=condition[0],
        icon=condition[1],
        visibility=random.randint(5, 10),
        pressure=random.randint(1005, 1020),
        clouds=random.randint(0, 80),
        sunrise="06:15",
        sunset="18:30",
        alerts=[],
        fetched_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        source=f"Sample Data ({reason})"
    )


@st.cache_data(ttl=CACHE_TTL_SECONDS, show_spinner=False)
def fetch_crime_news(city: str, max_results: int = 15) -> CrimeData:
    """
    Fetch real-time crime news from GNews API or Google News RSS.
    
    Args:
        city: City name to filter crime news for
        max_results: Maximum number of news items to return
        
    Returns:
        CrimeData object with crime-related news items
        
    Notes:
        - Cached for 15 minutes
        - Checks API key availability first
        - Tries GNews API first, then Google News RSS
        - Falls back to sample data if all APIs fail
    """
    # Check API key availability
    api_status = check_api_keys()
    has_news_api = api_status["any_news_key"]
    
    if not has_news_api:
        log_warning("No news API keys configured for crime data - using sample data", module="crime")
    
    # Try GNews API first (if key available)
    if api_status["keys"].get("GNEWS_API_KEY", False):
        result = _fetch_from_gnews(city, max_results)
        if result and result.news_items:
            return result
    
    # Fallback to Google News RSS (free, no API key needed)
    result = _fetch_from_google_news_rss(city, max_results)
    if result and result.news_items:
        return result
    
    # Final fallback to sample data
    log_info(f"Using sample crime data for {city}", module="crime")
    return _generate_sample_crime_news(city)


def _fetch_from_gnews(city: str, max_results: int) -> Optional[CrimeData]:
    """
    Fetch crime news from GNews API.
    """
    try:
        # Build search query with crime keywords
        query = f"({' OR '.join(CRIME_KEYWORDS[:5])}) AND {city}"
        
        params = {
            "q": query,
            "lang": "en",
            "max": min(max_results, 10),
            "token": GNEWS_API_KEY
        }
        
        response = requests.get(GNEWS_API_URL, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        articles = data.get("articles", [])
        
        news_items = [
            CrimeNewsItem(
                title=article.get("title", ""),
                description=article.get("description", "")[:200] if article.get("description") else "",
                url=article.get("url", ""),
                source=article.get("source", {}).get("name", "Unknown"),
                published_at=article.get("publishedAt", "")[:10],
                image_url=article.get("image")
            )
            for article in articles
            if _is_crime_related(article.get("title", "") + " " + (article.get("description") or ""))
        ]
        
        if news_items:
            return CrimeData(
                city=city,
                news_items=news_items[:max_results],
                total_count=len(news_items),
                fetched_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                source="GNews API"
            )
        
        return None
        
    except Exception:
        return None


def _fetch_from_google_news_rss(city: str, max_results: int) -> Optional[CrimeData]:
    """
    Fetch crime news from Google News RSS feed (free, no API key).
    """
    try:
        # Build search query
        query = f"crime OR police OR arrest {city}"
        encoded_query = quote_plus(query)
        
        url = f"{GOOGLE_NEWS_RSS_URL}?q={encoded_query}&hl=en-IN&gl=IN&ceid=IN:en"
        
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        }
        
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        
        # Parse RSS XML
        root = ET.fromstring(response.content)
        items = root.findall(".//item")
        
        news_items = []
        
        for item in items[:max_results * 2]:  # Get extra to filter
            title = item.find("title")
            link = item.find("link")
            pub_date = item.find("pubDate")
            source = item.find("source")
            
            title_text = title.text if title is not None else ""
            
            # Filter for crime-related content
            if _is_crime_related(title_text):
                news_items.append(CrimeNewsItem(
                    title=title_text,
                    description="",
                    url=link.text if link is not None else "",
                    source=source.text if source is not None else "Google News",
                    published_at=_parse_rss_date(pub_date.text if pub_date is not None else ""),
                    image_url=None
                ))
            
            if len(news_items) >= max_results:
                break
        
        if news_items:
            return CrimeData(
                city=city,
                news_items=news_items,
                total_count=len(news_items),
                fetched_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                source="Google News RSS"
            )
        
        return None
        
    except Exception:
        return None


def _is_crime_related(text: str) -> bool:
    """
    Check if text contains crime-related keywords.
    """
    text_lower = text.lower()
    return any(keyword in text_lower for keyword in CRIME_KEYWORDS)


def _parse_rss_date(date_str: str) -> str:
    """
    Parse RSS date format to simple date string.
    """
    try:
        # RSS format: "Wed, 04 Dec 2025 10:30:00 GMT"
        dt = datetime.strptime(date_str, "%a, %d %b %Y %H:%M:%S %Z")
        return dt.strftime("%Y-%m-%d")
    except Exception:
        try:
            # Try alternative format
            dt = datetime.strptime(date_str[:25], "%a, %d %b %Y %H:%M:%S")
            return dt.strftime("%Y-%m-%d")
        except Exception:
            return datetime.now().strftime("%Y-%m-%d")


def _generate_sample_crime_news(city: str) -> CrimeData:
    """
    Generate sample crime news when APIs are unavailable.
    """
    sample_templates = [
        ("Police arrest suspect in {city} theft case", "Theft"),
        ("Traffic violation drive conducted in {city}", "Traffic"),
        ("{city} police crack down on fraud ring", "Fraud"),
        ("Security increased in {city} ahead of festival", "Security"),
        ("Cybercrime awareness camp held in {city}", "Awareness"),
        ("{city} reports decrease in street crimes", "Positive"),
        ("Police patrol increased in {city} neighborhoods", "Security"),
        ("Community policing initiative launched in {city}", "Initiative"),
        ("{city} installs new CCTV cameras for safety", "Infrastructure"),
        ("Anti-drug operation conducted in {city}", "Drugs"),
    ]
    
    news_items = []
    used_templates = random.sample(sample_templates, min(8, len(sample_templates)))
    
    for i, (template, category) in enumerate(used_templates):
        days_ago = random.randint(0, 7)
        pub_date = (datetime.now() - timedelta(days=days_ago)).strftime("%Y-%m-%d")
        
        news_items.append(CrimeNewsItem(
            title=template.format(city=city),
            description=f"Sample {category.lower()} news for {city}. Real-time data unavailable.",
            url="#",
            source="Sample Data",
            published_at=pub_date,
            image_url=None
        ))
    
    return CrimeData(
        city=city,
        news_items=news_items,
        total_count=len(news_items),
        fetched_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        source="Sample Data (APIs unavailable)"
    )


def clear_weather_cache():
    """Clear the weather data cache."""
    fetch_weather_data.clear()


def clear_crime_cache():
    """Clear the crime news cache."""
    fetch_crime_news.clear()


def clear_all_caches():
    """Clear all API caches."""
    clear_weather_cache()
    clear_crime_cache()


def get_cache_status() -> Dict[str, str]:
    """Get current cache status information."""
    api_status = check_api_keys()
    return {
        "cache_ttl": f"{CACHE_TTL_SECONDS // 60} minutes",
        "weather_api": "Configured" if api_status["weather_available"] else "Not configured",
        "gnews_api": "Configured" if api_status["keys"].get("GNEWS_API_KEY") else "Not configured",
        "google_rss": "Available (free)"
    }


def get_weather_api_status() -> tuple:
    """
    Get current weather API status for UI display.
    
    Returns:
        Tuple of (is_live: bool, source_text: str, color: str)
    """
    api_status = check_api_keys()
    is_live = api_status["weather_available"]
    
    if is_live:
        return True, "Live API", "#10b981"
    else:
        return False, "Sample Data", "#f59e0b"


def get_crime_api_status() -> tuple:
    """
    Get current crime news API status for UI display.
    
    Returns:
        Tuple of (is_live: bool, source_text: str, color: str)
    """
    api_status = check_api_keys()
    # Crime uses news APIs or Google RSS (RSS is always available)
    is_live = api_status["any_news_key"]
    
    if is_live:
        return True, "Live API", "#10b981"
    else:
        # Google RSS is always available as fallback
        return False, "RSS/Sample", "#f59e0b"


DEFAULT_PERSONA = "default"

# Safety index clamping values
SAFETY_INDEX_MIN = -10
SAFETY_INDEX_MAX = 10

# Event types for categorization
EVENT_TYPES = [
    "theft", "robbery", "assault", "murder", "shooting",
    "burglary", "kidnap", "scam", "fraud", "drug",
    "gang", "violence", "traffic", "fire", "explosion",
    "natural_disaster", "civil_unrest", "accident", "other"
]


def clamp_value(value: float, min_value: float, max_value: float) -> float:
    """Clamp a value between min and max bounds."""
    return max(min_value, min(value, max_value))


def compute_base_index(events: List[CrimeNewsItem]) -> float:
    """
    Compute the unweighted safety index based on event counts.
    
    Each event type contributes equally to the index.
    """
    if not events:
        return 0.0
    
    total_events = len(events)
    event_weights = {
        "theft": -1,
        "robbery": -2,
        "assault": -3,
        "murder": -5,
        "shooting": -4,
        "burglary": -2,
        "kidnap": -3,
        "scam": -1,
        "fraud": -1,
        "drug": -2,
        "gang": -3,
        "violence": -4,
        "traffic": -1,
        "fire": -1,
        "explosion": -2,
        "natural_disaster": -3,
        "civil_unrest": -2,
        "accident": -1,
        "other": 0
    }
    
    index = sum(event_weights.get(e.title.lower(), 0) for e in events)
    
    return index / total_events if total_events > 0 else 0.0


def compute_persona_index(events: List[CrimeNewsItem], persona: Dict[str, Any]) -> float:
    """
    Compute the persona-weighted safety index based on event impacts.
    
    Considers the selected persona's sensitivity to different event types.
    """
    if not events or not persona:
        return 0.0
    
    total_events = len(events)
    sensitivity_weights = persona.get("sensitivity", {})
    
    index = sum(sensitivity_weights.get(e.title.lower(), 0) for e in events)
    
    return index / total_events if total_events > 0 else 0.0


def aggregate_scores(events_list: List[CrimeNewsItem]) -> Dict[str, Any]:
    """
    Aggregate safety metrics from a list of classified events.

    Returns a summary dict containing:
    - index: persona-weighted safety index (clamped to [-10, 10])
    - base_index: unweighted safety index (clamped to [-10, 10])
    - total_events: count of events processed
    - category_counts: counts per event type
    """
    events = events_list or []
    category_counts = Counter(e.event_type for e in events)
    total_events = len(events)

    try:
        import streamlit as st  # Lazy import to avoid hard dependency
        persona_name = st.session_state.get("selected_persona", DEFAULT_PERSONA)
    except Exception:
        persona_name = DEFAULT_PERSONA

    persona = get_persona(persona_name)

    base_index = clamp_value(
        compute_base_index(events),
        SAFETY_INDEX_MIN,
        SAFETY_INDEX_MAX,
    )

    persona_index = clamp_value(
        compute_persona_index(events, persona),
        SAFETY_INDEX_MIN,
        SAFETY_INDEX_MAX,
    )

    return {
        "index": persona_index,
        "base_index": base_index,
        "total_events": total_events,
        "category_counts": {etype: category_counts.get(etype, 0) for etype in EVENT_TYPES},
    }


__all__ = [
    # Data classes
    "WeatherData",
    "CrimeNewsItem",
    "CrimeData",
    # Weather functions
    "fetch_weather_data",
    "clear_weather_cache",
    # Crime functions
    "fetch_crime_news",
    "clear_crime_cache",
    # Utilities
    "clear_all_caches",
    "get_cache_status",
    "get_weather_api_status",
    "get_crime_api_status",
    # Safety scores
    "aggregate_scores",
    # Constants
    "CACHE_TTL_SECONDS",
    "CITY_COORDINATES",
]

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
