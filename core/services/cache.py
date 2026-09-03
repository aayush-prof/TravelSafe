"""
TravelSafe Cache Utilities
===========================

Centralized caching utilities for performance optimization:
- Cache statistics tracking
- Cache invalidation helpers
- Memory-efficient caching patterns
"""

import streamlit as st
from typing import Any, Callable, Optional
from datetime import datetime
import functools

from .logger import log_info, log_debug


_cache_stats = {
    "hits": 0,
    "misses": 0,
    "last_clear": None,
}


def get_cache_stats() -> dict:
    """
    Get current cache statistics.
    
    Returns:
        Dictionary with cache stats
    """
    return {
        **_cache_stats,
        "hit_rate": _cache_stats["hits"] / max(1, _cache_stats["hits"] + _cache_stats["misses"]),
    }


def _record_cache_hit():
    """Record a cache hit."""
    _cache_stats["hits"] += 1


def _record_cache_miss():
    """Record a cache miss."""
    _cache_stats["misses"] += 1


def clear_cache(cache_type: Optional[str] = None) -> bool:
    """
    Clear cached data.
    
    Args:
        cache_type: Optional specific cache to clear ('weather', 'crime', 'safety', or None for all)
        
    Returns:
        True if cache was cleared successfully
    """
    try:
        if cache_type is None:
            # Clear all Streamlit caches
            st.cache_data.clear()
            log_info("Cleared all caches", module="cache")
        else:
            # Note: Streamlit doesn't support clearing individual caches by name
            # This is a placeholder for future implementation
            st.cache_data.clear()
            log_info(f"Cleared {cache_type} cache", module="cache")
        
        _cache_stats["last_clear"] = datetime.now().isoformat()
        return True
        
    except Exception as e:
        log_info(f"Failed to clear cache: {e}", module="cache")
        return False


def get_cached_data(
    key: str,
    fetch_func: Callable,
    ttl_seconds: int = 300,
    *args,
    **kwargs
) -> Any:
    """
    Get data from cache or fetch if not available.
    
    This is a wrapper around Streamlit's cache that provides
    additional statistics and logging.
    
    Args:
        key: Cache key identifier
        fetch_func: Function to call if data not in cache
        ttl_seconds: Time-to-live in seconds
        *args, **kwargs: Arguments to pass to fetch_func
        
    Returns:
        Cached or freshly fetched data
    """
    # Use session state for simple key-value caching
    cache_key = f"_cache_{key}"
    time_key = f"_cache_time_{key}"
    
    # Check if cached and not expired
    if cache_key in st.session_state:
        cached_time = st.session_state.get(time_key, 0)
        if (datetime.now().timestamp() - cached_time) < ttl_seconds:
            _record_cache_hit()
            log_debug(f"Cache hit for {key}", module="cache")
            return st.session_state[cache_key]
    
    # Fetch fresh data
    _record_cache_miss()
    log_debug(f"Cache miss for {key}, fetching...", module="cache")
    
    try:
        data = fetch_func(*args, **kwargs)
        st.session_state[cache_key] = data
        st.session_state[time_key] = datetime.now().timestamp()
        return data
    except Exception as e:
        log_info(f"Failed to fetch data for {key}: {e}", module="cache")
        # Return cached data if available, even if expired
        if cache_key in st.session_state:
            return st.session_state[cache_key]
        raise


def cached_with_logging(ttl_seconds: int = 300, show_spinner: bool = False):
    """
    Decorator that adds logging to Streamlit's cache_data.
    
    Usage:
        @cached_with_logging(ttl_seconds=300)
        def my_expensive_function(arg):
            ...
    """
    def decorator(func: Callable) -> Callable:
        @st.cache_data(ttl=ttl_seconds, show_spinner=show_spinner)
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            log_debug(f"Executing cached function: {func.__name__}", module="cache")
            return func(*args, **kwargs)
        return wrapper
    return decorator


_singletons = {}


def get_singleton(key: str, factory: Callable) -> Any:
    """
    Get or create a singleton object.
    
    Useful for expensive objects like ML models that should
    only be loaded once.
    
    Args:
        key: Unique identifier for the singleton
        factory: Function to create the object if not exists
        
    Returns:
        Singleton instance
    """
    if key not in _singletons:
        log_info(f"Creating singleton: {key}", module="cache")
        _singletons[key] = factory()
    return _singletons[key]


def clear_singleton(key: str) -> bool:
    """
    Clear a specific singleton.
    
    Args:
        key: Singleton key to clear
        
    Returns:
        True if singleton was cleared
    """
    if key in _singletons:
        del _singletons[key]
        log_info(f"Cleared singleton: {key}", module="cache")
        return True
    return False
