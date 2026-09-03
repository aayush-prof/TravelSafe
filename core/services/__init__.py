"""
TravelSafe Services Module
===========================

Centralized reusable services for the TravelSafe application:

- logger.py      : Centralized logging configuration
- pdf_report.py  : Auto PDF report generator for all pages
- cache.py       : Caching utilities and optimization
- error_handler.py : Unified error handling

Usage:
    from core.services import logger, generate_pdf_report, handle_error
"""

from .logger import get_logger, log_info, log_error, log_warning, log_debug
from .pdf_report import (
    generate_safety_report,
    generate_weather_report,
    generate_crime_report,
    generate_city_report,
    create_download_button,
)
from .cache import (
    get_cached_data,
    clear_cache,
    get_cache_stats,
)
from .error_handler import (
    handle_api_error,
    handle_data_error,
    safe_execute,
    ErrorContext,
)

__all__ = [
    # Logger
    "get_logger",
    "log_info",
    "log_error",
    "log_warning",
    "log_debug",
    # PDF Reports
    "generate_safety_report",
    "generate_weather_report", 
    "generate_crime_report",
    "generate_city_report",
    "create_download_button",
    # Cache
    "get_cached_data",
    "clear_cache",
    "get_cache_stats",
    # Error Handler
    "handle_api_error",
    "handle_data_error",
    "safe_execute",
    "ErrorContext",
]
