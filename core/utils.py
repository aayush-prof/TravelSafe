"""
TravelSafe Utilities Module
===========================

This module contains helper functions used across the TravelSafe
application. These are general-purpose utilities that don't belong
to a specific domain module.

Functions included:
- Score normalization and clamping
- Text cleaning and preprocessing
- Date parsing and formatting
- Data validation helpers
"""

import re
from datetime import datetime, timedelta
from typing import Optional, List, Any


def normalize_score(
    value: float,
    min_src: float,
    max_src: float,
    min_dest: float,
    max_dest: float
) -> float:
    """
    Normalize a value from one range to another.
    
    This is a linear transformation that maps a value from the source
    range [min_src, max_src] to the destination range [min_dest, max_dest].
    
    Formula:
        normalized = min_dest + (value - min_src) * (max_dest - min_dest) / (max_src - min_src)
    
    Args:
        value: The value to normalize
        min_src: Minimum of the source range
        max_src: Maximum of the source range
        min_dest: Minimum of the destination range
        max_dest: Maximum of the destination range
        
    Returns:
        Normalized value in the destination range
        
    Example:
        >>> # Convert severity [-3, 3] to index [-10, 10]
        >>> normalize_score(-2, -3, 3, -10, 10)
        -6.666...
        >>> normalize_score(0, -3, 3, -10, 10)
        0.0
        >>> normalize_score(3, -3, 3, -10, 10)
        10.0
    """
    # Handle edge case where source range is zero
    if max_src == min_src:
        return (min_dest + max_dest) / 2
    
    # Linear interpolation formula
    normalized = min_dest + (value - min_src) * (max_dest - min_dest) / (max_src - min_src)
    
    return normalized


def clamp_value(value: float, min_val: float, max_val: float) -> float:
    """
    Clamp a value to be within a specified range.
    
    Args:
        value: The value to clamp
        min_val: Minimum allowed value
        max_val: Maximum allowed value
        
    Returns:
        Value clamped to [min_val, max_val]
        
    Example:
        >>> clamp_value(15, -10, 10)
        10
        >>> clamp_value(-5, -10, 10)
        -5
        >>> clamp_value(-15, -10, 10)
        -10
    """
    return max(min_val, min(max_val, value))


def round_to_decimal(value: float, decimals: int = 2) -> float:
    """
    Round a float to a specified number of decimal places.
    
    Args:
        value: The value to round
        decimals: Number of decimal places (default: 2)
        
    Returns:
        Rounded value
        
    Example:
        >>> round_to_decimal(3.14159, 2)
        3.14
    """
    return round(value, decimals)


def clean_text(text: str) -> str:
    """
    Clean and normalize text for processing.
    
    Operations performed:
    1. Strip leading/trailing whitespace
    2. Normalize multiple spaces to single space
    3. Remove control characters
    
    Args:
        text: Raw input text
        
    Returns:
        Cleaned text string
        
    Example:
        >>> clean_text("  Hello   World  ")
        'Hello World'
    """
    if not text:
        return ""
    
    # Strip whitespace
    text = text.strip()
    
    # Remove control characters
    text = re.sub(r'[\x00-\x1f\x7f-\x9f]', '', text)
    
    # Normalize whitespace
    text = ' '.join(text.split())
    
    return text


def truncate_text(text: str, max_length: int = 100, suffix: str = "...") -> str:
    """
    Truncate text to a maximum length, adding suffix if truncated.
    
    Args:
        text: Text to truncate
        max_length: Maximum length (including suffix)
        suffix: String to append if truncated
        
    Returns:
        Truncated text
        
    Example:
        >>> truncate_text("This is a long sentence", 15)
        'This is a lo...'
    """
    if not text or len(text) <= max_length:
        return text
    
    truncate_at = max_length - len(suffix)
    return text[:truncate_at] + suffix


def extract_keywords(text: str, min_length: int = 3) -> List[str]:
    """
    Extract keywords from text (simple tokenization).
    
    Args:
        text: Text to extract keywords from
        min_length: Minimum keyword length
        
    Returns:
        List of lowercase keywords
        
    Example:
        >>> extract_keywords("Heavy Rain in Mumbai City")
        ['heavy', 'rain', 'mumbai', 'city']
    """
    if not text:
        return []
    
    # Convert to lowercase and extract words
    words = re.findall(r'\b[a-zA-Z]+\b', text.lower())
    
    # Filter by minimum length
    keywords = [w for w in words if len(w) >= min_length]
    
    return keywords


def parse_date(
    date_string: str,
    formats: Optional[List[str]] = None
) -> Optional[datetime]:
    """
    Parse a date string using multiple possible formats.
    
    Args:
        date_string: String representation of date
        formats: List of format strings to try (default: common formats)
        
    Returns:
        datetime object or None if parsing fails
        
    Example:
        >>> parse_date("2025-12-01T10:30:00")
        datetime(2025, 12, 1, 10, 30)
        >>> parse_date("01-12-2025")
        datetime(2025, 12, 1)
    """
    if not date_string:
        return None
    
    # Default formats to try
    if formats is None:
        formats = [
            "%Y-%m-%dT%H:%M:%S",      # ISO format
            "%Y-%m-%dT%H:%M:%SZ",     # ISO with Z
            "%Y-%m-%d %H:%M:%S",      # Standard datetime
            "%Y-%m-%d",               # Date only
            "%d-%m-%Y",               # DD-MM-YYYY
            "%d/%m/%Y",               # DD/MM/YYYY
            "%m/%d/%Y",               # MM/DD/YYYY (US)
            "%B %d, %Y",              # Month DD, YYYY
            "%b %d, %Y",              # Mon DD, YYYY
        ]
    
    for fmt in formats:
        try:
            return datetime.strptime(date_string.strip(), fmt)
        except ValueError:
            continue
    
    return None


def format_date(
    dt: datetime,
    format_str: str = "%d %b %Y, %H:%M"
) -> str:
    """
    Format a datetime object to a human-readable string.
    
    Args:
        dt: datetime object
        format_str: Output format string
        
    Returns:
        Formatted date string
        
    Example:
        >>> format_date(datetime(2025, 12, 1, 10, 30))
        '01 Dec 2025, 10:30'
    """
    return dt.strftime(format_str)


def get_relative_time(dt: datetime) -> str:
    """
    Get a relative time description (e.g., "2 hours ago").
    
    Args:
        dt: datetime object
        
    Returns:
        Relative time string
        
    Example:
        >>> get_relative_time(datetime.now() - timedelta(hours=2))
        '2 hours ago'
    """
    now = datetime.now()
    diff = now - dt
    
    seconds = diff.total_seconds()
    
    if seconds < 60:
        return "just now"
    elif seconds < 3600:
        minutes = int(seconds / 60)
        return f"{minutes} minute{'s' if minutes > 1 else ''} ago"
    elif seconds < 86400:
        hours = int(seconds / 3600)
        return f"{hours} hour{'s' if hours > 1 else ''} ago"
    elif seconds < 604800:
        days = int(seconds / 86400)
        return f"{days} day{'s' if days > 1 else ''} ago"
    elif seconds < 2592000:
        weeks = int(seconds / 604800)
        return f"{weeks} week{'s' if weeks > 1 else ''} ago"
    else:
        return format_date(dt, "%d %b %Y")


def is_recent(dt: datetime, days: int = 7) -> bool:
    """
    Check if a datetime is within the last N days.
    
    Args:
        dt: datetime to check
        days: Number of days to consider "recent"
        
    Returns:
        True if datetime is within the last N days
    """
    cutoff = datetime.now() - timedelta(days=days)
    return dt >= cutoff


def is_valid_city(city: str, supported_cities: List[str]) -> bool:
    """
    Check if a city is in the list of supported cities.
    
    Case-insensitive comparison.
    
    Args:
        city: City name to validate
        supported_cities: List of valid city names
        
    Returns:
        True if city is supported
    """
    city_lower = city.lower()
    return any(c.lower() == city_lower for c in supported_cities)


def safe_get(
    dictionary: dict,
    key: str,
    default: Any = None
) -> Any:
    """
    Safely get a value from a dictionary with a default.
    
    Args:
        dictionary: Dictionary to get value from
        key: Key to look up
        default: Default value if key not found
        
    Returns:
        Value or default
    """
    return dictionary.get(key, default)


def ensure_list(value: Any) -> List:
    """
    Ensure a value is a list. If not, wrap it in a list.
    
    Args:
        value: Value to ensure is a list
        
    Returns:
        List containing the value or the value if already a list
        
    Example:
        >>> ensure_list("item")
        ['item']
        >>> ensure_list(["a", "b"])
        ['a', 'b']
        >>> ensure_list(None)
        []
    """
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def format_percentage(value: float, decimals: int = 1) -> str:
    """
    Format a decimal value as a percentage string.
    
    Args:
        value: Value between 0 and 1
        decimals: Decimal places to show
        
    Returns:
        Formatted percentage string
        
    Example:
        >>> format_percentage(0.856)
        '85.6%'
    """
    return f"{value * 100:.{decimals}f}%"


def format_score_with_sign(score: float) -> str:
    """
    Format a score with explicit sign (+ or -).
    
    Args:
        score: Numerical score
        
    Returns:
        String with explicit sign
        
    Example:
        >>> format_score_with_sign(5.5)
        '+5.50'
        >>> format_score_with_sign(-3.2)
        '-3.20'
    """
    if score >= 0:
        return f"+{score:.2f}"
    return f"{score:.2f}"


def pluralize(count: int, singular: str, plural: Optional[str] = None) -> str:
    """
    Return singular or plural form based on count.
    
    Args:
        count: Number of items
        singular: Singular form of word
        plural: Plural form (default: singular + 's')
        
    Returns:
        Appropriate form of the word
        
    Example:
        >>> pluralize(1, "event")
        'event'
        >>> pluralize(5, "event")
        'events'
        >>> pluralize(2, "city", "cities")
        'cities'
    """
    if plural is None:
        plural = singular + "s"
    
    return singular if count == 1 else plural
