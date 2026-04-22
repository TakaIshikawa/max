"""Domain quality memory helpers."""

from __future__ import annotations

from max.store.db import Store
from max.types.buildable_unit import BuildableUnit


def record_domain_quality_feedback(
    store: Store,
    unit: BuildableUnit,
    *,
    outcome: str,
    notes: str = "",
    score: float | None = None,
) -> None:
    """Persist a domain-local feedback pattern for future generation."""
    memory_outcome = "approved" if outcome in {"approved", "published"} else "rejected"
    store.insert_domain_quality_memory(
        domain=unit.domain,
        outcome=memory_outcome,
        pattern=f"{unit.title}: {unit.one_liner or unit.problem}",
        source_idea_id=unit.id,
        tags=unit.rejection_tags,
        score=score if score is not None else unit.quality_score,
        notes=notes,
    )
