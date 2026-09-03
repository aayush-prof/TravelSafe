"""
TravelSafe Error Handler
=========================

Centralized error handling with:
- Graceful degradation
- User-friendly error messages
- Logging integration
- Recovery strategies
"""

import streamlit as st
from typing import Any, Callable, Optional, TypeVar
from functools import wraps
from dataclasses import dataclass
from datetime import datetime

from .logger import log_error, log_warning


@dataclass
class ErrorContext:
    """Context information for error handling."""
    operation: str
    module: str
    user_message: str
    technical_message: Optional[str] = None
    recoverable: bool = True
    timestamp: str = None
    
    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now().isoformat()


def _show_error_toast(message: str, icon: str = "⚠️"):
    """Show error as toast notification."""
    try:
        st.toast(f"{icon} {message}", icon=icon)
    except Exception:
        pass  # Fallback silently if toast fails


def _show_error_message(context: ErrorContext, show_details: bool = False):
    """Display error message to user."""
    if context.recoverable:
        st.warning(f"⚠️ {context.user_message}")
        if show_details and context.technical_message:
            with st.expander("Technical Details"):
                st.code(context.technical_message)
    else:
        st.error(f"🚨 {context.user_message}")
        if show_details and context.technical_message:
            with st.expander("Technical Details"):
                st.code(context.technical_message)


def handle_api_error(
    error: Exception,
    api_name: str,
    city: str,
    fallback_data: Any = None,
    show_toast: bool = True,
) -> Any:
    """
    Handle API errors with graceful degradation.
    
    Args:
        error: The exception that occurred
        api_name: Name of the API (e.g., "OpenWeatherMap")
        city: City being queried
        fallback_data: Data to return if error occurs
        show_toast: Whether to show toast notification
        
    Returns:
        Fallback data if provided, else raises the error
    """
    error_msg = str(error)
    
    # Classify error type
    if "timeout" in error_msg.lower():
        user_msg = f"{api_name} is taking too long to respond. Using cached data."
        log_warning(f"API timeout for {api_name} ({city})", module="api")
    elif "401" in error_msg or "403" in error_msg:
        user_msg = f"{api_name} authentication failed. Check API key."
        log_error(f"API auth error for {api_name}", module="api", exc=error)
    elif "404" in error_msg:
        user_msg = f"Data not found for {city}."
        log_warning(f"API 404 for {api_name} ({city})", module="api")
    elif "429" in error_msg:
        user_msg = f"{api_name} rate limit reached. Please wait a moment."
        log_warning(f"API rate limit for {api_name}", module="api")
    elif "connection" in error_msg.lower() or "network" in error_msg.lower():
        user_msg = "Network connection issue. Using cached data."
        log_error(f"Network error for {api_name}", module="api", exc=error)
    else:
        user_msg = f"Could not fetch data from {api_name}. Using fallback."
        log_error(f"API error for {api_name} ({city})", module="api", exc=error)
    
    if show_toast:
        _show_error_toast(user_msg)
    
    if fallback_data is not None:
        return fallback_data
    
    raise error


def handle_data_error(
    error: Exception,
    operation: str,
    default_value: Any = None,
    show_message: bool = True,
) -> Any:
    """
    Handle data processing errors.
    
    Args:
        error: The exception that occurred
        operation: Description of what was being done
        default_value: Value to return on error
        show_message: Whether to show error message
        
    Returns:
        Default value if provided, else raises error
    """
    log_error(f"Data error during {operation}", module="data", exc=error)
    
    if show_message:
        st.warning(f"⚠️ Error processing data: {operation}")
    
    if default_value is not None:
        return default_value
    
    raise error


T = TypeVar('T')


def safe_execute(
    func: Callable[..., T],
    *args,
    default: T = None,
    error_message: str = "An error occurred",
    show_error: bool = True,
    log_errors: bool = True,
    **kwargs
) -> T:
    """
    Safely execute a function with error handling.
    
    Args:
        func: Function to execute
        *args: Positional arguments for func
        default: Default value to return on error
        error_message: User-facing error message
        show_error: Whether to display error to user
        log_errors: Whether to log errors
        **kwargs: Keyword arguments for func
        
    Returns:
        Function result or default value on error
        
    Example:
        result = safe_execute(
            risky_function,
            arg1, arg2,
            default=[],
            error_message="Could not load data"
        )
    """
    try:
        return func(*args, **kwargs)
    except Exception as e:
        if log_errors:
            log_error(f"Error in {func.__name__}: {error_message}", module="safe", exc=e)
        
        if show_error:
            _show_error_toast(error_message)
        
        return default


def with_error_handling(
    default_return: Any = None,
    error_message: str = "Operation failed",
    show_toast: bool = True,
    reraise: bool = False,
):
    """
    Decorator for automatic error handling.
    
    Usage:
        @with_error_handling(default_return=[], error_message="Could not load items")
        def load_items():
            ...
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                log_error(f"Error in {func.__name__}", module="decorator", exc=e)
                
                if show_toast:
                    _show_error_toast(error_message)
                
                if reraise:
                    raise
                
                return default_return
        return wrapper
    return decorator


def validate_city(city: str, supported_cities: list) -> bool:
    """
    Validate that a city is supported.
    
    Args:
        city: City name to validate
        supported_cities: List of valid cities
        
    Returns:
        True if valid, shows error and returns False otherwise
    """
    if city in supported_cities:
        return True
    
    log_warning(f"Invalid city selected: {city}", module="validation")
    st.error(f"City '{city}' is not supported. Please select a valid city.")
    return False


def validate_api_response(response: dict, required_fields: list) -> bool:
    """
    Validate that an API response contains required fields.
    
    Args:
        response: API response dictionary
        required_fields: List of required field names
        
    Returns:
        True if all fields present, False otherwise
    """
    missing = [f for f in required_fields if f not in response]
    
    if missing:
        log_warning(f"API response missing fields: {missing}", module="validation")
        return False
    
    return True
