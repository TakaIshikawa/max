from __future__ import annotations

import json

from max.spec.secret_rotation_runbook import generate_secret_rotation_runbook


def test_secret_rotation_runbook_orders_rotation_validation_and_rollback_steps() -> None:
    runbook = generate_secret_rotation_runbook(
        {
            "metadata": {
                "secret_rotation": {
                    "secrets": [
                        {
                            "name": "payments api key",
                            "secret_id": "vault/payments/api-key",
                            "owner": "payments_owner",
                        }
                    ],
                    "dependent_services": [{"service": "payments-worker", "owner": "service_owner"}],
                    "validation_steps": [{"name": "payments smoke test", "service": "payments-worker"}],
                    "rollback_steps": [{"name": "restore previous vault version"}],
                    "communication_checkpoints": [{"name": "notify on-call", "channel": "#payments"}],
                }
            },
            "evidence": {"signal_ids": ["rotation-ticket-5"]},
        }
    )

    assert runbook["title"] == "Secret Rotation Runbook"
    assert runbook["rotation_window"] == "within 7 days"
    assert [step["phase"] for step in runbook["rotation_steps"]] == ["prepare", "rotate"]
    assert runbook["validation_steps"][0]["name"] == "payments smoke test"
    assert runbook["rollback_steps"][0]["name"] == "restore previous vault version"
    assert runbook["communication_checkpoints"][0]["channel"] == "#payments"
    assert runbook["blockers"] == []
    assert runbook["secret_inventory"][0]["evidence_reference_ids"] == ["EV1"]


def test_secret_rotation_runbook_missing_required_inputs_create_blockers() -> None:
    runbook = generate_secret_rotation_runbook(
        {
            "metadata": {
                "secret_rotation": {
                    "secrets": [{"name": "webhook token"}],
                    "dependent_services": [],
                }
            }
        }
    )

    assert [blocker["missing_field"] for blocker in runbook["blockers"]] == [
        "owner",
        "secret_identifier",
        "dependent_service",
    ]
    assert runbook["summary"]["blocker_count"] == 3


def test_secret_rotation_emergency_shortens_recommended_window() -> None:
    runbook = generate_secret_rotation_runbook(
        {
            "metadata": {
                "secret_rotation": {
                    "emergency": "yes",
                    "secrets": [
                        {
                            "name": "signing key",
                            "secret_id": "kms/signing-key",
                            "owner": "security_owner",
                        }
                    ],
                    "dependent_services": [{"service": "api"}],
                }
            }
        }
    )

    assert runbook["rotation_window"] == "within 4 hours"
    assert runbook["summary"]["rotation_window"] == "within 4 hours"


def test_secret_rotation_defaults_are_deterministic_and_json_safe() -> None:
    runbook = generate_secret_rotation_runbook({})

    assert runbook == generate_secret_rotation_runbook({})
    assert runbook["schema_version"] == "max.spec.secret_rotation_runbook.v1"
    assert runbook["summary"]["secret_count"] == 1
    assert runbook["secret_inventory"][0]["name"] == "secret rotation inventory"
    assert json.loads(json.dumps(runbook)) == runbook
