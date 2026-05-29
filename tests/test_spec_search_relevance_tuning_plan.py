from __future__ import annotations

from max.spec import generate_search_relevance_tuning_plan


def test_search_relevance_tuning_plan_rich_inputs() -> None:
    plan = generate_search_relevance_tuning_plan({"metadata": {"search_relevance_tuning": {"surface": "catalog", "target_queries": ["laptop"], "ranking_signals": ["freshness"], "baseline_metrics": ["ndcg"]}}})

    assert plan["summary"]["search_surface"] == "catalog"
    assert plan["target_queries"][0]["name"] == "laptop"
    assert plan["ranking_signals"][0]["name"] == "freshness"
    assert plan["baseline"][0]["name"] == "ndcg"


def test_search_relevance_tuning_plan_sparse_defaults() -> None:
    plan = generate_search_relevance_tuning_plan({})

    assert plan["experiment_design"]
    assert plan["evaluation_dataset"]
    assert plan["rollback"]
