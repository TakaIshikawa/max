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
