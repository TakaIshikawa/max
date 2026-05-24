from __future__ import annotations

import json

from max.api.idea_portfolio_balance import idea_portfolio_balance_to_json


def test_idea_portfolio_balance_summarizes_buckets_and_warnings() -> None:
    parsed = json.loads(
        idea_portfolio_balance_to_json(
            {
                "dominance_threshold": 0.5,
                "ideas": [
                    {"id": "a", "domain": "FinTech", "stage": "draft", "recommendation": "invest", "risk_band": "low"},
                    {"id": "b", "domain": "FinTech", "stage": "draft", "recommendation": "invest", "risk_band": "medium"},
                    {"id": "c", "domain": "Health", "stage": "validated", "recommendation": "hold", "risk_band": "medium"},
                ],
            }
        )
    )

    assert parsed["schema_version"] == "max.api.idea_portfolio_balance.v1"
    assert parsed["summary"]["idea_count"] == 3
    assert parsed["bucket_summaries"]["domain"][0] == {"bucket": "fintech", "count": 2, "percentage": 0.6667}
    assert {warning["dimension"] for warning in parsed["imbalance_warnings"]} >= {"domain", "stage", "recommendation", "risk_band"}
    assert parsed["recommended_rebalance_actions"][0]["id"].startswith("rebalance-")


def test_idea_portfolio_balance_aliases_and_metadata() -> None:
    parsed = json.loads(
        idea_portfolio_balance_to_json(
            {
                "items": [{"idea_id": "x", "category": "Ops", "status": "Review", "verdict": "ship", "risk": "high"}],
                "metadata": {"run_id": "r1"},
            },
            as_of="2026-05-21T00:00:00Z",
        )
    )

    assert parsed["ideas"][0]["domain"] == "ops"
    assert parsed["ideas"][0]["recommendation"] == "ship"
    assert parsed["ideas"][0]["risk_band"] == "high"
    assert parsed["metadata"]["run_id"] == "r1"
    assert parsed["metadata"]["as_of"] == "2026-05-21T00:00:00Z"


def test_idea_portfolio_balance_empty_input_has_zero_totals() -> None:
    parsed = json.loads(idea_portfolio_balance_to_json({}))

    assert parsed["summary"]["idea_count"] == 0
    assert parsed["summary"]["balanced"] is True
    assert parsed["bucket_summaries"]["domain"] == []
    assert parsed["imbalance_warnings"] == []
    assert parsed["recommended_rebalance_actions"] == []


def test_idea_portfolio_balance_clamps_threshold() -> None:
    parsed = json.loads(idea_portfolio_balance_to_json({"threshold": 2, "ideas": [{"id": "a"}, {"id": "b"}]}))

    assert parsed["summary"]["dominance_threshold"] == 1.0
    assert parsed["imbalance_warnings"] == []
