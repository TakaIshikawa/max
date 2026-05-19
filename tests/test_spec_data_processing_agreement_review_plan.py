from __future__ import annotations

import json

from max.spec.data_processing_agreement_review_plan import (
    DATA_PROCESSING_AGREEMENT_REVIEW_PLAN_SCHEMA_VERSION,
    KIND,
    generate_data_processing_agreement_review_plan,
)


def _spec() -> dict:
    return {
        "schema_version": "tact-spec-preview/v1",
        "kind": "tact.project_spec",
        "source": {"idea_id": "dpa-1", "domain": "privacy"},
        "project": {
            "title": "Vendor Onboarding Portal",
            "workflow_context": "vendor onboarding",
            "specific_user": "procurement manager",
            "target_users": ["legal reviewer"],
            "buyer": "privacy director",
        },
        "execution": {
            "mvp_scope": ["vendor intake", "contract approval"],
            "risks": ["GDPR transfer and subprocessor risk for personal data."],
        },
        "metadata": {
            "vendors": ["Cloud CRM", "Analytics Warehouse"],
            "data_categories": ["email", "personal data"],
            "regulatory_regions": ["GDPR", "CPRA"],
            "dpa": {
                "transfer_mechanism": "EU SCCs with transfer impact assessment",
                "review_deadline": "before first production sync",
            },
        },
        "evidence": {"insight_ids": ["ins-dpa"], "signal_ids": ["sig-vendor"]},
    }


def test_data_processing_agreement_review_plan_complete_shape_and_strict_checks() -> None:
    plan = generate_data_processing_agreement_review_plan(_spec())

    assert plan["schema_version"] == DATA_PROCESSING_AGREEMENT_REVIEW_PLAN_SCHEMA_VERSION
    assert plan["kind"] == KIND
    assert plan["summary"]["title"] == "Vendor Onboarding Portal"
    assert plan["summary"]["review_strictness"] == "strict"
    assert plan["summary"]["processor_count"] == 2
    assert set(plan) == {
        "schema_version",
        "kind",
        "source",
        "summary",
        "review_scope",
        "processor_inventory",
        "clause_checks",
        "transfer_assessment",
        "approval_path",
        "remediation_items",
        "evidence_references",
    }
    assert [item["processor"] for item in plan["processor_inventory"]] == [
        "Analytics Warehouse",
        "Cloud CRM",
    ]
    assert [item["id"] for item in plan["clause_checks"]] == ["CC1", "CC2", "CC3", "CC4", "CC5", "CC6"]
    assert plan["transfer_assessment"][0]["transfer_mechanism"] == "EU SCCs with transfer impact assessment"
    assert [item["owner"] for item in plan["approval_path"]] == [
        "legal_owner",
        "security_owner",
        "privacy_owner",
        "privacy director",
    ]
    assert plan["remediation_items"][0]["severity"] == "high"
    assert json.loads(json.dumps(plan))["kind"] == KIND


def test_data_processing_agreement_review_plan_metadata_changes_strictness() -> None:
    standard = generate_data_processing_agreement_review_plan({"project": {"title": "Internal Tool"}})
    strict = generate_data_processing_agreement_review_plan(
        {
            "project": {"title": "Internal Tool"},
            "metadata": {"vendors": ["Payment Processor"], "data_categories": ["payment card"], "regulatory_regions": ["GDPR"]},
        }
    )

    assert standard["summary"]["review_strictness"] == "standard"
    assert len(standard["clause_checks"]) == 4
    assert strict["summary"]["review_strictness"] == "strict"
    assert len(strict["clause_checks"]) == 6
    assert strict["transfer_assessment"][0]["timing"] == "complete before production data transfer"


def test_data_processing_agreement_review_plan_sparse_input_defaults_are_deterministic() -> None:
    first = generate_data_processing_agreement_review_plan({})
    second = generate_data_processing_agreement_review_plan({})

    assert first == second
    assert first["processor_inventory"][0]["processor"] == "primary processor under review"
    assert first["clause_checks"][0]["name"] == "Processing instructions"
    assert first["review_scope"]["data_categories"] == ["customer data"]
