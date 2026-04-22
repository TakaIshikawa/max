"""Source allocation simulation for profile-configured adapters."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from max.pipeline.fetch_strategy import compute_fetch_allocation
from max.profiles.schema import PipelineProfile, SourceConfig
from max.sources.base import snapshot_circuit_breakers
from max.store.db import Store


@dataclass(frozen=True)
class SourceSimulationRow:
    """Per-source simulation details."""

    adapter: str
    enabled: bool
    configured_weight: float
    params: dict[str, Any]
    total_signals: int
    insight_hit_rate: float
    idea_hit_rate: float
    total_feedbacked: int
    approved: int
    rejected: int
    approval_rate: float | None
    circuit_state: str
    circuit_failures: int
    circuit_retry_after_seconds: float | None
    allocated_limit: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "adapter": self.adapter,
            "enabled": self.enabled,
            "configured_weight": self.configured_weight,
            "params": self.params,
            "quality": {
                "total_signals": self.total_signals,
                "insight_hit_rate": self.insight_hit_rate,
                "idea_hit_rate": self.idea_hit_rate,
            },
            "approval": {
                "total_feedbacked": self.total_feedbacked,
                "approved": self.approved,
                "rejected": self.rejected,
                "approval_rate": self.approval_rate,
            },
            "circuit_breaker": {
                "state": self.circuit_state,
                "failure_count": self.circuit_failures,
                "retry_after_seconds": self.circuit_retry_after_seconds,
            },
            "allocated_limit": self.allocated_limit,
        }


@dataclass(frozen=True)
class SourceSimulationReport:
    """Structured source simulation for one profile."""

    profile: str
    domain: str
    total_budget: int
    allocation: dict[str, int]
    sources: list[SourceSimulationRow] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "profile": self.profile,
            "domain": self.domain,
            "total_budget": self.total_budget,
            "allocation": self.allocation,
            "sources": [source.to_dict() for source in self.sources],
        }


def simulate_source_allocation(
    profile: PipelineProfile,
    store: Store,
    *,
    budget: int | None = None,
) -> SourceSimulationReport:
    """Simulate source allocation for a profile without fetching signals."""
    total_budget = budget if budget is not None else profile.signal_limit
    if total_budget < 1:
        raise ValueError("budget must be at least 1")

    enabled_adapter_names = [
        source.adapter for source in profile.sources if source.enabled
    ]
    allocation = compute_fetch_allocation(total_budget, enabled_adapter_names, store)
    quality_stats = store.get_adapter_quality_stats()
    approval_stats = store.get_adapter_approval_stats()
    circuit_by_adapter = {
        snapshot.adapter_name: snapshot
        for snapshot in snapshot_circuit_breakers(
            adapter_names=[source.adapter for source in profile.sources]
        )
    }

    rows = [
        _source_row(
            source,
            quality=quality_stats.get(source.adapter, {}),
            approval=approval_stats.get(source.adapter, {}),
            circuit=circuit_by_adapter.get(source.adapter),
            allocated_limit=allocation.get(source.adapter, 0) if source.enabled else 0,
        )
        for source in profile.sources
    ]

    return SourceSimulationReport(
        profile=profile.name,
        domain=profile.domain.name,
        total_budget=total_budget,
        allocation=allocation,
        sources=rows,
    )


def _source_row(
    source: SourceConfig,
    *,
    quality: dict[str, Any],
    approval: dict[str, Any],
    circuit: Any,
    allocated_limit: int,
) -> SourceSimulationRow:
    return SourceSimulationRow(
        adapter=source.adapter,
        enabled=source.enabled,
        configured_weight=source.weight,
        params=source.normalized_params,
        total_signals=int(quality.get("total_signals", 0)),
        insight_hit_rate=float(quality.get("insight_hit_rate", 0.0)),
        idea_hit_rate=float(quality.get("idea_hit_rate", 0.0)),
        total_feedbacked=int(approval.get("total_feedbacked", 0)),
        approved=int(approval.get("approved", 0)),
        rejected=int(approval.get("rejected", 0)),
        approval_rate=approval.get("approval_rate"),
        circuit_state=getattr(circuit, "state", "closed"),
        circuit_failures=int(getattr(circuit, "failure_count", 0)),
        circuit_retry_after_seconds=getattr(circuit, "retry_after", None),
        allocated_limit=allocated_limit,
    )
