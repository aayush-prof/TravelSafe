"""
TravelSafe Logger Module
=========================

Centralized logging configuration with:
- File and console logging
- Structured log format
- Log rotation
- Different log levels per module
"""

import logging
import sys
from pathlib import Path
from datetime import datetime
from typing import Optional
import functools


LOG_DIR = Path(__file__).parent.parent.parent / "logs"
LOG_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"
LOG_LEVEL = logging.INFO

# Create log directory if needed
try:
    LOG_DIR.mkdir(exist_ok=True)
except Exception:
    LOG_DIR = None  # Fallback to console-only logging


_loggers = {}


def get_logger(name: str = "travelsafe") -> logging.Logger:
    """
    Get or create a logger with the specified name.
    
    Loggers are cached to avoid duplicate handlers.
    
    Args:
        name: Logger name (default: "travelsafe")
        
    Returns:
        Configured logger instance
    """
    if name in _loggers:
        return _loggers[name]
    
    logger = logging.getLogger(name)
    logger.setLevel(LOG_LEVEL)
    
    # Avoid duplicate handlers
    if not logger.handlers:
        # Console handler
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(LOG_LEVEL)
        console_handler.setFormatter(logging.Formatter(LOG_FORMAT, DATE_FORMAT))
        logger.addHandler(console_handler)
        
        # File handler (if log directory exists)
        if LOG_DIR and LOG_DIR.exists():
            try:
                log_file = LOG_DIR / f"travelsafe_{datetime.now().strftime('%Y%m%d')}.log"
                file_handler = logging.FileHandler(log_file, encoding='utf-8')
                file_handler.setLevel(LOG_LEVEL)
                file_handler.setFormatter(logging.Formatter(LOG_FORMAT, DATE_FORMAT))
                logger.addHandler(file_handler)
            except Exception:
                pass  # Skip file logging if it fails
    
    _loggers[name] = logger
    return logger


_default_logger = None


def _get_default_logger() -> logging.Logger:
    """Get or create the default logger."""
    global _default_logger
    if _default_logger is None:
        _default_logger = get_logger("travelsafe")
    return _default_logger


def log_info(message: str, module: str = "app"):
    """Log an info message."""
    _get_default_logger().info(f"[{module}] {message}")


def log_error(message: str, module: str = "app", exc: Optional[Exception] = None):
    """Log an error message with optional exception."""
    logger = _get_default_logger()
    if exc:
        logger.error(f"[{module}] {message}: {type(exc).__name__}: {str(exc)}")
    else:
        logger.error(f"[{module}] {message}")


def log_warning(message: str, module: str = "app"):
    """Log a warning message."""
    _get_default_logger().warning(f"[{module}] {message}")


def log_debug(message: str, module: str = "app"):
    """Log a debug message."""
    _get_default_logger().debug(f"[{module}] {message}")


def log_api_call(api_name: str, city: str, success: bool, duration_ms: Optional[float] = None):
    """Log an API call with timing info."""
    status = "SUCCESS" if success else "FAILED"
    duration_str = f" ({duration_ms:.0f}ms)" if duration_ms else ""
    log_info(f"API {api_name} for {city}: {status}{duration_str}", module="api")


def log_function_call(func):
    """
    Decorator to log function entry and exit.
    
    Usage:
        @log_function_call
        def my_function(arg1, arg2):
            ...
    """
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        func_name = func.__name__
        log_debug(f"Entering {func_name}", module="func")
        try:
            result = func(*args, **kwargs)
            log_debug(f"Exiting {func_name} (success)", module="func")
            return result
        except Exception as e:
            log_error(f"Exception in {func_name}", module="func", exc=e)
            raise
    return wrapper
