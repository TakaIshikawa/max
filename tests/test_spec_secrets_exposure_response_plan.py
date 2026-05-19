from __future__ import annotations

import json

from max.spec.secrets_exposure_response_plan import (
    KIND,
    SECRETS_EXPOSURE_RESPONSE_PLAN_SCHEMA_VERSION,
    generate_secrets_exposure_response_plan,
)


def _spec() -> dict:
    return {
        "schema_version": "tact-spec-preview/v1",
        "kind": "tact.project_spec",
        "source": {"idea_id": "secret-1", "domain": "security"},
        "project": {
            "title": "Checkout API",
            "workflow_context": "checkout payment flow",
            "specific_user": "merchant operator",
            "buyer": "security director",
        },
        "execution": {
            "mvp_scope": ["production checkout api", "payment worker"],
            "risks": ["Customer-impacting API key exposure in production logs."],
        },
        "metadata": {
            "secrets": ["Stripe API key", "database password"],
            "secrets_exposure": {
                "type": "production log leak",
                "production": True,
                "customer_impacting": True,
                "systems": ["payment worker"],
                "detected_at": "2026-05-20T10:00:00Z",
                "ticket": "SEC-123",
            },
        },
        "evidence": {"insight_ids": ["ins-secret"], "signal_ids": ["sig-log"]},
    }


def test_secrets_exposure_response_plan_complete_shape_and_strict_expectations() -> None:
    plan = generate_secrets_exposure_response_plan(_spec())

    assert plan["schema_version"] == SECRETS_EXPOSURE_RESPONSE_PLAN_SCHEMA_VERSION
    assert plan["kind"] == KIND
    assert plan["summary"]["title"] == "Checkout API"
    assert plan["summary"]["response_strictness"] == "strict"
    assert plan["summary"]["production"] is True
    assert set(plan) == {
        "schema_version",
        "kind",
        "source",
        "summary",
        "exposure_triage",
        "containment_steps",
        "rotation_sequence",
        "blast_radius_review",
        "verification_checks",
        "communication_path",
        "owner_roles",
        "evidence_references",
    }
    assert plan["exposure_triage"]["classification"] == "production customer-impacting secret exposure"
    assert [item["name"] for item in plan["containment_steps"]] == [
        "Revoke exposed material",
        "Freeze unsafe propagation",
        "Preserve evidence",
        "Production access guard",
    ]
    assert [item["secret"] for item in plan["rotation_sequence"]] == [
        "database password",
        "Stripe API key",
    ]
    assert plan["blast_radius_review"][0]["customer_impact_review_required"] is True
    assert [item["id"] for item in plan["verification_checks"]] == ["VC1", "VC2", "VC3", "VC4"]
    assert plan["communication_path"][-1]["owner"] == "communications_owner"
    assert json.loads(json.dumps(plan))["kind"] == KIND


def test_secrets_exposure_response_plan_metadata_changes_containment_and_verification() -> None:
    standard = generate_secrets_exposure_response_plan({"project": {"title": "Developer Sandbox"}})
    strict = generate_secrets_exposure_response_plan(
        {
            "project": {"title": "Developer Sandbox"},
            "metadata": {"secrets_exposure": {"production": True, "customer_impacting": True}, "secrets": ["OAuth token"]},
        }
    )

    assert standard["summary"]["response_strictness"] == "standard"
    assert len(standard["containment_steps"]) == 3
    assert len(standard["verification_checks"]) == 3
    assert strict["summary"]["response_strictness"] == "strict"
    assert strict["containment_steps"][0]["timing"] == "immediate"
    assert len(strict["verification_checks"]) == 4


def test_secrets_exposure_response_plan_sparse_input_defaults_are_deterministic() -> None:
    first = generate_secrets_exposure_response_plan({})
    second = generate_secrets_exposure_response_plan({})

    assert first == second
    assert first["rotation_sequence"][0]["secret"] == "application credential under review"
    assert first["blast_radius_review"][0]["system"] == "primary application system"
    assert first["exposure_triage"]["exposure_type"] == "suspected secrets exposure"
