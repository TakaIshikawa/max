from __future__ import annotations

from max.spec.inference_abuse_monitoring_plan import generate_inference_abuse_monitoring_plan


def test_inference_abuse_monitoring_plan_flags_missing_owner_and_threshold() -> None:
    plan = generate_inference_abuse_monitoring_plan(
        {
            "abuse_signals": [
                {"signal": "credential stuffing", "threshold": "50 failures/min", "owner": "security"},
                {"signal": "jailbreak spike", "severity": "high"},
            ],
            "suppression_rules": [{"name": "load test window", "owner": "sre", "expiry": "2026-06-01"}],
        }
    )

    assert set(plan) >= {"abuse_signals", "detection_thresholds", "alert_routing", "investigation_steps", "escalation_owners", "suppression_rules", "evidence_requirements"}
    assert plan["abuse_signals"][0]["name"] == "jailbreak spike"
    assert len(plan["blockers"]) == 2
    assert plan["suppression_rules"][0]["name"] == "load test window"


def test_inference_abuse_monitoring_plan_is_deterministic_and_preserves_metadata() -> None:
    source = {"abuse_signals": [{"signal": "token spray", "threshold": "100/min", "owner": "abuse", "evidence_id": "sig-1", "metadata": {"team": "red"}}]}

    assert generate_inference_abuse_monitoring_plan(source) == generate_inference_abuse_monitoring_plan(source)
    row = generate_inference_abuse_monitoring_plan(source)["abuse_signals"][0]
    assert row["evidence_id"] == "sig-1"
    assert row["metadata"] == {"team": "red"}
