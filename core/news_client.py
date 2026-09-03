"""
TravelSafe News Client Module
=============================

This module handles fetching news data for cities from multiple sources.
It implements a fallback chain for reliability:

1. PRIMARY: NewsAPI.org (if API key available)
2. FALLBACK 1: Google News RSS (free, no key required)
3. FALLBACK 2: GNews API (if API key available)
4. FALLBACK 3: Local sample data

The module automatically switches between sources based on availability
and implements robust error handling for production reliability.
"""

import json
import os
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Optional, Dict
from urllib.parse import quote_plus
import requests

from .config import (
    USE_LIVE_NEWS,
    NEWS_API_KEY,
    NEWS_API_BASE_URL,
    NEWS_FETCH_LIMIT,
    SAMPLE_NEWS_PATH,
    SUPPORTED_CITIES,
    get_city_region,
    check_api_keys,
)
from .models import NewsItem


# GNews API (alternative free API)
GNEWS_API_KEY: str = os.getenv("GNEWS_API_KEY", "")
GNEWS_API_URL: str = "https://gnews.io/api/v4/search"

# Google News RSS (free, no API key needed)
GOOGLE_NEWS_RSS_URL: str = "https://news.google.com/rss/search"

# Request timeout
REQUEST_TIMEOUT: int = 15

# Cache for tracking which source was used
_last_data_source: str = "Unknown"


def _get_sample_data_path() -> Path:
    """Get the absolute path to the sample news JSON file."""
    current_file = Path(__file__).resolve()
    project_root = current_file.parent.parent
    return project_root / SAMPLE_NEWS_PATH


def _load_sample_news() -> List[dict]:
    """Load all sample news from the JSON file."""
    sample_path = _get_sample_data_path()
    
    if not sample_path.exists():
        print(f"Warning: Sample news file not found at {sample_path}")
        return []
    
    try:
        with open(sample_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return data.get("news", [])
    except (json.JSONDecodeError, IOError) as e:
        print(f"Warning: Failed to load sample news: {e}")
        return []


def _filter_news_by_city(news_list: List[dict], city: str) -> List[dict]:
    """Filter news items for a specific city (case-insensitive)."""
    city_lower = city.lower()
    return [
        news for news in news_list 
        if news.get("city", "").lower() == city_lower
    ]


def _generate_sample_for_city(city: str) -> List[dict]:
    """
    Generate synthetic sample news for cities without sample data.
    This ensures all 30+ cities have some news to display.
    """
    region = get_city_region(city)
    base_date = datetime.now()
    
    # Generic news templates that work for any city
    templates = [
        {
            "title": f"New metro line expansion announced in {city}",
            "description": f"City officials revealed plans for extending public transport infrastructure in {city}.",
            "source": "Local News",
            "severity_hint": "positive"
        },
        {
            "title": f"Traffic congestion reported in central {city}",
            "description": f"Heavy traffic during rush hours affecting commuters in {city}.",
            "source": "Traffic Updates",
            "severity_hint": "neutral"
        },
        {
            "title": f"Cultural festival draws tourists to {city}",
            "description": f"Annual cultural celebrations attract visitors from around the world to {city}.",
            "source": "Tourism Desk",
            "severity_hint": "positive"
        },
        {
            "title": f"Weather advisory issued for {city}",
            "description": f"Meteorological department advises residents to take precautions.",
            "source": "Weather Bureau",
            "severity_hint": "weather"
        },
        {
            "title": f"Local businesses thrive in {city} market district",
            "description": f"Economic growth reported in commercial areas of {city}.",
            "source": "Business Today",
            "severity_hint": "positive"
        },
        {
            "title": f"Minor road accident near {city} highway",
            "description": f"No serious injuries reported in the incident.",
            "source": "Traffic Police",
            "severity_hint": "accident"
        },
        {
            "title": f"Community cleanup drive organized in {city}",
            "description": f"Residents come together for environmental initiative.",
            "source": "Community News",
            "severity_hint": "positive"
        },
        {
            "title": f"Police increase patrols in {city} tourist areas",
            "description": f"Enhanced security measures for visitor safety.",
            "source": "Police Department",
            "severity_hint": "neutral"
        },
    ]
    
    generated_news = []
    for i, template in enumerate(templates):
        generated_news.append({
            "title": template["title"],
            "description": template["description"],
            "city": city,
            "source": template["source"],
            "published_at": (base_date - timedelta(hours=i*3)).strftime("%Y-%m-%dT%H:%M:%S")
        })
    
    return generated_news


def _parse_news_item(raw_news: dict) -> Optional[NewsItem]:
    """Parse a raw news dictionary into a NewsItem object."""
    try:
        published_str = raw_news.get("published_at", "")
        if published_str:
            for fmt in ["%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"]:
                try:
                    published_at = datetime.strptime(published_str, fmt)
                    break
                except ValueError:
                    continue
            else:
                published_at = datetime.now()
        else:
            published_at = datetime.now()
        
        return NewsItem(
            title=raw_news.get("title", "Untitled"),
            description=raw_news.get("description"),
            city=raw_news.get("city", "Unknown"),
            source=raw_news.get("source", "Unknown"),
            published_at=published_at
        )
    except Exception as e:
        print(f"Warning: Failed to parse news item: {e}")
        return None


def _fetch_from_newsapi(city: str) -> List[dict]:
    """
    Fetch news from NewsAPI.org (Primary source).
    Requires API key in NEWS_API_KEY environment variable.
    """
    global _last_data_source
    
    if not NEWS_API_KEY:
        return []
    
    try:
        region = get_city_region(city)
        search_query = f"{city} {'India' if region == 'India' else ''}"
        
        params = {
            "q": search_query,
            "apiKey": NEWS_API_KEY,
            "language": "en",
            "sortBy": "publishedAt",
            "pageSize": NEWS_FETCH_LIMIT
        }
        
        response = requests.get(
            NEWS_API_BASE_URL,
            params=params,
            timeout=REQUEST_TIMEOUT
        )
        response.raise_for_status()
        
        data = response.json()
        
        if data.get("status") != "ok":
            print(f"NewsAPI Error: {data.get('message', 'Unknown error')}")
            return []
        
        articles = data.get("articles", [])
        transformed = []
        
        for article in articles:
            if article.get("title") and article["title"] != "[Removed]":
                transformed.append({
                    "title": article.get("title", ""),
                    "description": article.get("description", ""),
                    "city": city,
                    "source": article.get("source", {}).get("name", "Unknown"),
                    "published_at": article.get("publishedAt", "")
                })
        
        if transformed:
            _last_data_source = "📡 NewsAPI (Live)"
        
        return transformed
        
    except requests.exceptions.Timeout:
        print("Warning: NewsAPI request timed out")
        return []
    except requests.exceptions.RequestException as e:
        print(f"Warning: NewsAPI request failed: {e}")
        return []
    except json.JSONDecodeError:
        print("Warning: Failed to parse NewsAPI response")
        return []


def _fetch_from_google_rss(city: str) -> List[dict]:
    """
    Fetch news from Google News RSS feed.
    Free and doesn't require an API key.
    """
    global _last_data_source
    
    try:
        region = get_city_region(city)
        search_query = f"{city} {'India' if region == 'India' else ''} news"
        encoded_query = quote_plus(search_query)
        
        url = f"{GOOGLE_NEWS_RSS_URL}?q={encoded_query}&hl=en&gl=US&ceid=US:en"
        
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        }
        
        response = requests.get(url, headers=headers, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
        
        # Parse XML RSS feed
        root = ET.fromstring(response.content)
        
        articles = []
        items = root.findall(".//item")[:NEWS_FETCH_LIMIT]
        
        for item in items:
            title_elem = item.find("title")
            desc_elem = item.find("description")
            source_elem = item.find("source")
            pubdate_elem = item.find("pubDate")
            
            title = title_elem.text if title_elem is not None else "Untitled"
            
            # Clean HTML from description
            description = ""
            if desc_elem is not None and desc_elem.text:
                description = re.sub(r'<[^>]+>', '', desc_elem.text)
            
            source = source_elem.text if source_elem is not None else "Google News"
            
            # Parse pub date (format: "Tue, 03 Dec 2024 10:30:00 GMT")
            published_at = ""
            if pubdate_elem is not None and pubdate_elem.text:
                try:
                    dt = datetime.strptime(pubdate_elem.text, "%a, %d %b %Y %H:%M:%S %Z")
                    published_at = dt.strftime("%Y-%m-%dT%H:%M:%S")
                except ValueError:
                    published_at = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
            
            articles.append({
                "title": title,
                "description": description[:500] if description else "",
                "city": city,
                "source": source,
                "published_at": published_at
            })
        
        if articles:
            _last_data_source = "📡 Google News RSS (Live)"
        
        return articles
        
    except requests.exceptions.RequestException as e:
        print(f"Warning: Google News RSS request failed: {e}")
        return []
    except ET.ParseError as e:
        print(f"Warning: Failed to parse Google News RSS: {e}")
        return []


def _fetch_from_gnews(city: str) -> List[dict]:
    """
    Fetch news from GNews API (Alternative source).
    Requires API key in GNEWS_API_KEY environment variable.
    Free tier: 100 requests/day
    """
    global _last_data_source
    
    if not GNEWS_API_KEY:
        return []
    
    try:
        region = get_city_region(city)
        search_query = f"{city} {'India' if region == 'India' else ''}"
        
        params = {
            "q": search_query,
            "token": GNEWS_API_KEY,
            "lang": "en",
            "max": min(NEWS_FETCH_LIMIT, 10)  # GNews free tier limit
        }
        
        response = requests.get(
            GNEWS_API_URL,
            params=params,
            timeout=REQUEST_TIMEOUT
        )
        response.raise_for_status()
        
        data = response.json()
        articles = data.get("articles", [])
        
        transformed = []
        for article in articles:
            transformed.append({
                "title": article.get("title", ""),
                "description": article.get("description", ""),
                "city": city,
                "source": article.get("source", {}).get("name", "Unknown"),
                "published_at": article.get("publishedAt", "")
            })
        
        if transformed:
            _last_data_source = "📡 GNews API (Live)"
        
        return transformed
        
    except requests.exceptions.RequestException as e:
        print(f"Warning: GNews API request failed: {e}")
        return []
    except json.JSONDecodeError:
        print("Warning: Failed to parse GNews response")
        return []


def fetch_news_for_city(city: str) -> List[NewsItem]:
    """
    Fetch news articles for a specific city using fallback chain.
    
    Fallback order:
    1. NewsAPI (if API key set)
    2. Google News RSS (free)
    3. GNews API (if API key set)
    4. Sample data (local)
    5. Generated sample (if no data exists)
    
    Args:
        city: Name of the city (should be in SUPPORTED_CITIES)
        
    Returns:
        List of NewsItem objects for the city
    """
    global _last_data_source
    
    if city not in SUPPORTED_CITIES:
        print(f"Warning: '{city}' is not in supported cities")
    
    raw_news: List[dict] = []
    
    # Check API key availability
    api_status = check_api_keys()
    has_news_api = api_status["any_news_key"]
    
    # Determine if we should attempt live mode
    should_try_live = USE_LIVE_NEWS and has_news_api
    
    if not has_news_api and USE_LIVE_NEWS:
        print(f"Warning: No news API keys configured. Falling back to sample data.")
    
    if should_try_live:
        # Try NewsAPI first
        print(f"Fetching live news for {city}...")
        raw_news = _fetch_from_newsapi(city)
        
        # Fallback to Google News RSS
        if not raw_news:
            print("Trying Google News RSS fallback...")
            raw_news = _fetch_from_google_rss(city)
        
        # Fallback to GNews
        if not raw_news:
            print("Trying GNews API fallback...")
            raw_news = _fetch_from_gnews(city)
        
        # Final fallback to sample data
        if not raw_news:
            print("Falling back to sample data...")
            all_sample = _load_sample_news()
            raw_news = _filter_news_by_city(all_sample, city)
            if raw_news:
                _last_data_source = "📁 Sample Data (Fallback)"
    else:
        # Use sample data (offline mode or no API keys)
        all_sample = _load_sample_news()
        raw_news = _filter_news_by_city(all_sample, city)
        _last_data_source = "📁 Sample Data (Offline)"
    
    # Generate sample if no data found for this city
    if not raw_news:
        print(f"Generating sample news for {city}...")
        raw_news = _generate_sample_for_city(city)
        _last_data_source = "🔄 Generated Sample"
    
    # Parse raw dictionaries into NewsItem objects
    news_items: List[NewsItem] = []
    for raw in raw_news:
        item = _parse_news_item(raw)
        if item:
            news_items.append(item)
    
    return news_items


def fetch_news_for_all_cities() -> Dict[str, List[NewsItem]]:
    """Fetch news for all supported cities."""
    result = {}
    for city in SUPPORTED_CITIES:
        result[city] = fetch_news_for_city(city)
    return result


def get_news_count_by_city() -> Dict[str, int]:
    """Get count of available news articles per city."""
    counts = {}
    
    if not USE_LIVE_NEWS:
        all_sample = _load_sample_news()
        for city in SUPPORTED_CITIES:
            filtered = _filter_news_by_city(all_sample, city)
            counts[city] = len(filtered) if filtered else 8  # Default generated count
    else:
        for city in SUPPORTED_CITIES:
            counts[city] = NEWS_FETCH_LIMIT
    
    return counts


def is_live_mode_available() -> bool:
    """Check if live API mode is available."""
    api_status = check_api_keys()
    return USE_LIVE_NEWS and api_status["any_news_key"]


def get_data_source_info() -> str:
    """Get information about the current data source."""
    global _last_data_source
    return _last_data_source if _last_data_source else "📁 Sample Data (Offline)"


def get_news_api_status() -> tuple:
    """
    Get current news API status for UI display.
    
    Returns:
        Tuple of (is_live: bool, source_text: str, color: str)
    """
    api_status = check_api_keys()
    is_live = api_status["any_news_key"] and USE_LIVE_NEWS
    
    if is_live:
        return True, "Live API", "#10b981"
    else:
        return False, "Sample Data", "#f59e0b"
