from __future__ import annotations

from max.spec import generate_profile_signal_rebalance_plan


def test_profile_signal_rebalance_plan_identifies_missing_and_overrepresented_roles() -> None:
    plan = generate_profile_signal_rebalance_plan(
        {
            "metadata": {
                "profile_signal_rebalance": {
                    "profiles": [
                        {"profile": "buyer", "role_counts": {"problem": 4, "solution": 1}},
                        {"profile": "maker", "role_counts": {"problem": 1, "solution": 1, "market": 1}},
                    ]
                }
            }
        }
    )

    buyer = plan["profile_role_balance"][0]
    assert buyer["profile"] == "buyer"
    assert buyer["missing_roles"] == ["market"]
    assert buyer["overrepresented_roles"] == ["problem"]
    assert {item["role"] for item in plan["allocation_adjustments"]} >= {"market", "problem"}


def test_profile_signal_rebalance_plan_surfaces_unknown_roles_without_balance_credit() -> None:
    plan = generate_profile_signal_rebalance_plan({"profiles": [{"profile": "ops", "signals": [{"role": "problem"}, {"role": "evidence"}]}]})

    row = plan["profile_role_balance"][0]
    assert row["unknown_roles"] == ["evidence"]
    assert row["missing_roles"] == ["solution", "market"]
    assert any(item["role"] == "evidence" and "do not count" in item["action"] for item in plan["allocation_adjustments"])


def test_profile_signal_rebalance_plan_includes_monitoring_and_success_criteria() -> None:
    plan = generate_profile_signal_rebalance_plan({"profiles": [{"profile": "balanced", "role_counts": {"problem": 1, "solution": 1, "market": 1}}]})

    assert plan["summary"]["imbalanced_profile_count"] == 0
    assert plan["monitoring_checks"][0]["name"] == "role_coverage"
    assert plan["success_criteria"][0]["name"] == "balanced_profiles"
