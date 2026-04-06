"""Configuration loaded from environment variables."""

from __future__ import annotations

import logging
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)


def get_project_root() -> Path:
    return Path(__file__).resolve().parent.parent.parent


def _parse_int(env_var: str, default: int) -> int:
    """Parse an integer environment variable, returning *default* on failure."""
    raw = os.getenv(env_var)
    if raw is None:
        return default
    try:
        return int(raw)
    except (ValueError, TypeError):
        logger.warning(
            "%s=%r is not a valid integer, using default %d", env_var, raw, default
        )
        return default


def _parse_float(env_var: str, default: float) -> float:
    """Parse a float environment variable, returning *default* on failure."""
    raw = os.getenv(env_var)
    if raw is None:
        return default
    try:
        return float(raw)
    except (ValueError, TypeError):
        logger.warning(
            "%s=%r is not a valid float, using default %s", env_var, raw, default
        )
        return default


DB_PATH: str = os.getenv("MAX_DB_PATH", str(get_project_root() / "max.db"))
MODEL: str = os.getenv("MAX_MODEL", "claude-opus-4-6")
ANTHROPIC_API_KEY: str = os.getenv("ANTHROPIC_API_KEY", "")

# Server
MAX_HOST: str = os.getenv("MAX_HOST", "0.0.0.0")
MAX_PORT: int = _parse_int("MAX_PORT", 8000)

# Scheduler
MAX_SCHEDULE_INTERVAL: int = _parse_int("MAX_SCHEDULE_INTERVAL", 21600)  # seconds, default 6h
MAX_SCHEDULE_ENABLED: bool = os.getenv("MAX_SCHEDULE_ENABLED", "true").lower() == "true"
MAX_SCHEDULE_SIGNAL_LIMIT: int = _parse_int("MAX_SCHEDULE_SIGNAL_LIMIT", 30)
MAX_SCHEDULE_MIN_SCORE: float = _parse_float("MAX_SCHEDULE_MIN_SCORE", 50.0)
MAX_SCHEDULE_PROFILE: str = os.getenv("MAX_SCHEDULE_PROFILE", "default")
MAX_SCHEDULE_MODE: str = os.getenv("MAX_SCHEDULE_MODE", "direct")

# Pipeline profile
MAX_PROFILE: str = os.getenv("MAX_PROFILE", "")  # pipeline profile name (e.g. "devtools", "healthcare")

# Adapters
MAX_ADAPTERS: str = os.getenv("MAX_ADAPTERS", "all")  # comma-separated or "all"
MAX_ADAPTERS_EXCLUDE: str = os.getenv("MAX_ADAPTERS_EXCLUDE", "")  # comma-separated

# Retention
MAX_RETENTION_DAYS: int = _parse_int("MAX_RETENTION_DAYS", 90)  # days before archival


def validate_config() -> list[str]:
    """Check current config values and return a list of warning strings."""
    warnings: list[str] = []

    if not ANTHROPIC_API_KEY:
        warnings.append("ANTHROPIC_API_KEY is not set; API calls will fail")

    if not (1 <= MAX_PORT <= 65535):
        warnings.append(
            f"MAX_PORT={MAX_PORT} is outside valid range 1-65535"
        )

    if MAX_SCHEDULE_INTERVAL < 60:
        warnings.append(
            f"MAX_SCHEDULE_INTERVAL={MAX_SCHEDULE_INTERVAL} is below minimum of 60 seconds"
        )

    return warnings
