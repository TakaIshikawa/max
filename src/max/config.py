"""Configuration loaded from environment variables."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


def get_project_root() -> Path:
    return Path(__file__).resolve().parent.parent.parent


DB_PATH: str = os.getenv("MAX_DB_PATH", str(get_project_root() / "max.db"))
MODEL: str = os.getenv("MAX_MODEL", "claude-opus-4-6")
ANTHROPIC_API_KEY: str = os.getenv("ANTHROPIC_API_KEY", "")

# Server
MAX_HOST: str = os.getenv("MAX_HOST", "0.0.0.0")
MAX_PORT: int = int(os.getenv("MAX_PORT", "8000"))

# Scheduler
MAX_SCHEDULE_INTERVAL: int = int(os.getenv("MAX_SCHEDULE_INTERVAL", "21600"))  # seconds, default 6h
MAX_SCHEDULE_ENABLED: bool = os.getenv("MAX_SCHEDULE_ENABLED", "true").lower() == "true"
MAX_SCHEDULE_SIGNAL_LIMIT: int = int(os.getenv("MAX_SCHEDULE_SIGNAL_LIMIT", "30"))
MAX_SCHEDULE_MIN_SCORE: float = float(os.getenv("MAX_SCHEDULE_MIN_SCORE", "50.0"))
MAX_SCHEDULE_PROFILE: str = os.getenv("MAX_SCHEDULE_PROFILE", "default")
MAX_SCHEDULE_MODE: str = os.getenv("MAX_SCHEDULE_MODE", "direct")

# Pipeline profile
MAX_PROFILE: str = os.getenv("MAX_PROFILE", "")  # pipeline profile name (e.g. "devtools", "healthcare")

# Adapters
MAX_ADAPTERS: str = os.getenv("MAX_ADAPTERS", "all")  # comma-separated or "all"
MAX_ADAPTERS_EXCLUDE: str = os.getenv("MAX_ADAPTERS_EXCLUDE", "")  # comma-separated
