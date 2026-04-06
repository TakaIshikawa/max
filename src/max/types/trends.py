"""TrendPoint — per-window metrics for approval rate trend detection."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal


@dataclass
class TrendPoint:
    """Metrics for a single trend window of pipeline runs."""

    window_start: datetime
    window_end: datetime
    approval_rate: float
    avg_score: float
    signal_count: int
    trend_direction: Literal["improving", "declining", "stable"]
