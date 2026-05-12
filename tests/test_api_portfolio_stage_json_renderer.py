from __future__ import annotations

from max.api import portfolio_stage_distribution_to_json


def test_portfolio_stage_renderer_includes_counts_percentages_and_metadata() -> None:
    payload = portfolio_stage_distribution_to_json(
        {
            "schema_version": "max.portfolio_stage_distribution.v1",
            "kind": "max.portfolio_stage_distribution",
            "filters": {"profile": ["default"], "domain": None},
            "summary": {"total_ideas": 4, "evaluated_count": 3},
            "by_status": [
                {"status": "new", "count": 1, "percentage": 25.0},
                {"status": "validated", "count": 3, "percentage": 75.0},
            ],
            "by_recommendation": [
                {"recommendation": "build", "count": 3, "percentage": 75.0}
            ],
            "groups": [{"status": "validated", "count": 3, "percentage": 75.0}],
            "bottlenecks": [{"dimension": "status", "value": "new", "count": 1}],
            "recommendations": ["Review new ideas"],
        }
    )

    assert payload["kind"] == "max.api.portfolio_stage_distribution"
    assert payload["summary"]["total_ideas"] == 4
    assert payload["stage_counts"]["by_status"][0]["status"] == "new"
    assert payload["percentages"]["by_status"]["new"] == 25.0
    assert payload["groups"][0]["count"] == 3
    assert payload["metadata"]["filters"]["profile"] == ["default"]
