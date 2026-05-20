from __future__ import annotations

from max.spec.launch_support_coverage_plan import KIND, SCHEMA_VERSION, generate_launch_support_coverage_plan


def test_launch_support_coverage_holds_for_uncovered_critical_window() -> None:
    plan = generate_launch_support_coverage_plan(
        {
            "evidence": {"signal_ids": ["launch-sig"]},
            "metadata": {
                "launch_support_coverage": {
                    "support_windows": [{"name": "cutover", "severity": "critical", "coverage": "uncovered"}],
                    "roles": ["incident commander"],
                }
            },
        }
    )

    assert plan["schema_version"] == SCHEMA_VERSION
    assert plan["kind"] == KIND
    assert plan["recommendation"] == "hold"
    assert plan["coverage_gaps"]
    assert plan["support_windows"][0]["evidence_reference_ids"] == ["EV1"]


def test_launch_support_coverage_accepts_dict_and_string_roles() -> None:
    plan = generate_launch_support_coverage_plan({"metadata": {"launch_support_coverage": {"roles": ["support lead", {"name": "SRE", "owner": "Ops"}], "escalation_paths": ["pager"]}}})

    assert [item["name"] for item in plan["staffed_roles"]] == ["SRE", "support lead"]
    assert plan["recommendation"] == "ready"
