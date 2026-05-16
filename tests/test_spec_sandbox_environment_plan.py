from __future__ import annotations

from max.spec.sandbox_environment_plan import generate_sandbox_environment_plan


def test_sandbox_environment_plan_covers_required_sections_and_sensitive_data_rules() -> None:
    plan = generate_sandbox_environment_plan(
        {
            "project": {"title": "Checkout Sandbox"},
            "sandbox": {
                "purpose": "staging checkout flows",
                "data_sensitivity": "restricted PII",
                "integration_stubs": ["stripe stub", "email sink"],
                "reset_cadence": "daily",
            },
            "evidence": {"signal_ids": ["sandbox-1"]},
        }
    )

    assert plan["kind"] == "max.sandbox_environment_plan"
    assert plan["summary"]["data_policy"] == "sanitized_or_synthetic_required"
    assert "use synthetic records" in plan["data_seeding_rules"]
    assert plan["integration_stubs"] == ["email sink", "stripe stub"]
    assert plan["reset_cadence"] == "daily"
    assert plan["evidence"] == ["signal:sandbox-1"]


def test_sandbox_environment_plan_defaults_missing_fields() -> None:
    plan = generate_sandbox_environment_plan({})

    assert plan["summary"]["title"] == "Unknown"
    assert plan["environment_purpose"] == "Unknown"
    assert plan["integration_stubs"] == ["Unknown"]
    assert plan["reset_cadence"] == "weekly"


def test_sandbox_environment_plan_is_deterministic() -> None:
    payload = {"sandbox": {"integration_stubs": ["z", "a", "z"]}}

    assert generate_sandbox_environment_plan(payload) == generate_sandbox_environment_plan(payload)
    assert generate_sandbox_environment_plan(payload)["integration_stubs"] == ["a", "z"]
