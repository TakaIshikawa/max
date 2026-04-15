"""Pipeline types and result structures."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class StageSummary:
    """Summary of a single pipeline stage (for dry-run reporting)."""

    name: str
    would_process: int  # number of items this stage would handle
    estimated_llm_calls: int
    skipped: bool
    reason: str  # e.g., 'no new signals since last run'


@dataclass
class DryRunReport:
    """Dry-run report showing what the pipeline would do without executing."""

    stages: list[StageSummary]
    estimated_total_llm_calls: int
    estimated_token_budget: int
