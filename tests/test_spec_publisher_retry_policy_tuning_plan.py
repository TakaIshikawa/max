from __future__ import annotations

from max.spec import generate_publisher_retry_policy_tuning_plan


def test_publisher_retry_policy_tuning_plan_summarizes_patterns_by_target_and_reason() -> None:
    plan = generate_publisher_retry_policy_tuning_plan(
        {
            "metadata": {
                "publisher_retry_policy_tuning": {
                    "retry_history": [
                        {"target_type": "webhook", "failure_reason": "network_timeout", "attempts": 2},
                        {"target_type": "webhook", "failure_reason": "network_timeout", "attempts": 4},
                        {"target_type": "email", "failure_reason": "auth_denied", "attempts": 3},
                    ]
                }
            }
        }
    )

    assert [(row["target_type"], row["failure_reason"], row["event_count"]) for row in plan["retry_patterns"]] == [
        ("email", "auth_denied", 1),
        ("webhook", "network_timeout", 2),
    ]
    assert plan["retry_patterns"][1]["average_attempts"] == 3.0


def test_publisher_retry_policy_tuning_plan_recommends_different_auth_and_network_policies() -> None:
    plan = generate_publisher_retry_policy_tuning_plan(
        {"events": [{"target": "feed", "reason": "credential_expired"}, {"target": "feed", "reason": "transient_network"}]}
    )

    auth, network = plan["policy_recommendations"]
    assert auth["max_attempts"] == 2
    assert "credential repair" in auth["action"]
    assert network["max_attempts"] == 6
    assert network["retry_interval"] == "exponential backoff with jitter"


def test_publisher_retry_policy_tuning_plan_includes_validation_metrics() -> None:
    plan = generate_publisher_retry_policy_tuning_plan({})

    assert plan["summary"]["retry_pattern_count"] == 0
    assert plan["validation_metrics"][0]["name"] == "publish_success_after_retry"
