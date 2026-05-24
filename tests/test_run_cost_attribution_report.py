from __future__ import annotations

from max.exports.run_cost_attribution_report import generate_run_cost_attribution_report


def test_run_cost_attribution_report_groups_costs_and_percentages() -> None:
    report = generate_run_cost_attribution_report(
        {
            "budget": 10,
            "records": [
                {"stage": "fetch", "profile": "smb", "idea_id": "a", "cost_type": "api", "cost": 2},
                {"stage": "score", "profile": "smb", "idea_id": "b", "cost_type": "llm", "cost": 6},
                {"stage": "score", "profile": "ent", "idea_id": "b", "cost_type": "storage", "cost": 2},
            ],
        }
    )

    assert report["summary"]["total_cost"] == 10
    assert report["stage_rows"][0] == {"name": "score", "cost": 8.0, "percentage": 0.8, "record_count": 2}
    assert report["profile_rows"][0]["name"] == "smb"
    assert report["top_cost_drivers"][0]["cost_type"] == "llm"


def test_run_cost_attribution_report_aliases_missing_costs_and_warnings() -> None:
    report = generate_run_cost_attribution_report({"cost_budget": 1, "costs": [{"pipeline_stage": "draft", "persona": "ent", "idea": "x", "type": "llm", "amount": "bad"}]})

    assert report["summary"]["unknown_cost_count"] == 1
    assert report["stage_rows"][0]["name"] == "draft"
    assert report["warnings"] == ["Missing or zero cost for record 1"]
    assert report["recommendations"][0]["type"] == "stage_optimization"


def test_run_cost_attribution_report_deterministic_sorting() -> None:
    report = generate_run_cost_attribution_report([{"stage": "b", "cost": 1}, {"stage": "a", "cost": 1}])

    assert [row["name"] for row in report["stage_rows"]] == ["a", "b"]
    assert report["budget_variance"]["variance"] == 0.0
