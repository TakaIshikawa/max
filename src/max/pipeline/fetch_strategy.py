"""Adaptive fetch allocation — allocate signal budget based on historical adapter quality."""

from __future__ import annotations

import math

from max.store.db import Store


def compute_fetch_allocation(
    total_budget: int,
    adapter_names: list[str],
    store: Store,
    *,
    min_per_adapter: int = 3,
    insight_weight: float = 0.4,
    idea_weight: float = 0.6,
    smoothing: float = 0.3,
) -> dict[str, int]:
    """Compute per-adapter signal fetch limits based on historical quality.

    Quality = insight_weight * insight_hit_rate + idea_weight * idea_hit_rate.
    Blends quality-based allocation with uniform distribution via smoothing.
    Falls back to uniform when no historical data exists.
    """
    if not adapter_names:
        return {}

    n = len(adapter_names)

    # Not enough budget for minimums
    if total_budget < min_per_adapter * n:
        per = max(total_budget // n, 1)
        return {name: per for name in adapter_names}

    stats = store.get_adapter_quality_stats()
    approval_stats = store.get_adapter_approval_stats()

    quality: dict[str, float] = {}
    for name in adapter_names:
        adapter_stats = stats.get(name)
        if not adapter_stats or adapter_stats["total_signals"] < 5:
            quality[name] = 1.0
        else:
            insight_rate = adapter_stats["insight_hit_rate"]
            idea_rate = adapter_stats["idea_hit_rate"]
            # Blend with approval rate when sufficient feedback exists
            adapter_approval = approval_stats.get(name)
            if adapter_approval and adapter_approval["total_feedbacked"] >= 3:
                approval_rate = adapter_approval["approval_rate"]
                quality[name] = (
                    0.3 * insight_rate + 0.3 * idea_rate + 0.4 * approval_rate
                )
            else:
                quality[name] = (
                    insight_weight * insight_rate + idea_weight * idea_rate
                )

    max_q = max(quality.values()) if quality else 1.0
    if max_q == 0:
        max_q = 1.0

    exp_scores = {name: math.exp(q / max_q) for name, q in quality.items()}
    total_exp = sum(exp_scores.values())

    remaining = total_budget - (min_per_adapter * n)

    allocation: dict[str, int] = {}
    for name in adapter_names:
        quality_share = (exp_scores[name] / total_exp) * remaining
        uniform_share = remaining / n
        blended = smoothing * uniform_share + (1 - smoothing) * quality_share
        allocation[name] = min_per_adapter + max(0, round(blended))

    # Adjust rounding to match total_budget exactly
    diff = total_budget - sum(allocation.values())
    if diff != 0:
        best = max(adapter_names, key=lambda name: quality.get(name, 0))
        allocation[best] = max(min_per_adapter, allocation[best] + diff)

    return allocation
