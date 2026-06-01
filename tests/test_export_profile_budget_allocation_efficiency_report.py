from __future__ import annotations

import json

from max.exports.profile_budget_allocation_efficiency_report import generate_profile_budget_allocation_efficiency_report


def test_profile_budget_allocation_efficiency_empty_input() -> None:
    report = generate_profile_budget_allocation_efficiency_report([])

    assert report["summary"]["profile_count"] == 0
    assert report["summary"]["efficiency"] == 0.0
    json.dumps(report)


def test_profile_budget_allocation_efficiency_represents_zero_allocation() -> None:
    report = generate_profile_budget_allocation_efficiency_report([{"profile": "zero", "allocated_budget": 0, "useful_output": 5}])

    assert report["profiles"][0]["profile"] == "zero"
    assert report["profiles"][0]["allocated_budget"] == 0.0
    assert report["profiles"][0]["efficiency"] == 0.0


def test_profile_budget_allocation_efficiency_flags_threshold_failures() -> None:
    report = generate_profile_budget_allocation_efficiency_report(
        [
            {"profile": "growth", "allocated_budget": 100, "useful_output": 40},
            {"profile": "retention", "allocated_budget": 50, "useful_output": 45},
        ],
        min_efficiency=0.5,
    )

    assert report["summary"]["underperforming_count"] == 1
    assert [row["profile"] for row in report["underperforming_profiles"]] == ["growth"]


def test_profile_budget_allocation_efficiency_sorts_by_efficiency_then_profile() -> None:
    report = generate_profile_budget_allocation_efficiency_report(
        [
            {"profile": "Beta", "allocated_budget": 100, "useful_output": 25},
            {"profile": "Alpha", "allocated_budget": 200, "useful_output": 50},
            {"profile": "Gamma", "allocated_budget": 100, "useful_output": 80},
            {"profile": "Alpha", "allocated_budget": 100, "useful_output": 25},
        ]
    )

    assert [row["profile"] for row in report["profiles"]] == ["Alpha", "Beta", "Gamma"]
    assert report["profiles"][0]["allocated_budget"] == 300.0
