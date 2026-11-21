"""Structured logging to console and ``backend/logs/`` (daily file)."""

from __future__ import annotations

import logging
import sys
from datetime import datetime
from pathlib import Path

LOG_DIR = Path(__file__).resolve().parent.parent / "logs"
_FORMAT = "%(asctime)s | %(levelname)-7s | %(name)s | %(message)s"
_configured = False


def configure_logging(level: int = logging.INFO) -> None:
    global _configured
    if _configured:
        return
    root = logging.getLogger("travelsafe")
    root.setLevel(level)
    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(logging.Formatter(_FORMAT, "%Y-%m-%d %H:%M:%S"))
    root.addHandler(console)
    try:
        LOG_DIR.mkdir(exist_ok=True)
        fh = logging.FileHandler(LOG_DIR / f"travelsafe_{datetime.now():%Y%m%d}.log", encoding="utf-8")
        fh.setFormatter(logging.Formatter(_FORMAT, "%Y-%m-%d %H:%M:%S"))
        root.addHandler(fh)
    except OSError as exc:  # read-only filesystem etc.
        root.warning("File logging disabled: %s", exc)
    root.propagate = False
    _configured = True


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(f"travelsafe.{name}")
