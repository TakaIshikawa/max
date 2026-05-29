from __future__ import annotations

from max.spec import generate_cache_invalidation_rollout_plan


def test_cache_invalidation_rollout_plan_preserves_layer_ordering() -> None:
    plan = generate_cache_invalidation_rollout_plan({"metadata": {"cache_invalidation_rollout": {"cache_layers": ["redis", "edge"], "namespaces": ["profile"], "strategy": "tag purge"}}})

    assert plan["summary"]["invalidation_strategy"] == "tag purge"
    assert [row["name"] for row in plan["cache_inventory"]] == ["edge", "redis"]
    assert plan["invalidation_steps"][0]["name"] == "profile"


def test_cache_invalidation_rollout_plan_sparse_defaults() -> None:
    plan = generate_cache_invalidation_rollout_plan({})

    assert plan["warmup"]
    assert plan["observability"]
    assert plan["post_rollout_validation"]
