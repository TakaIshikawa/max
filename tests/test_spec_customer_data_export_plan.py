from __future__ import annotations

import json

from max.spec.customer_data_export_plan import (
    CUSTOMER_DATA_EXPORT_PLAN_SCHEMA_VERSION,
    KIND,
    generate_customer_data_export_plan,
)


def _spec() -> dict:
    return {
        "schema_version": "tact-spec-preview/v1",
        "kind": "tact.project_spec",
        "source": {"idea_id": "export-1", "domain": "privacy"},
        "project": {
            "title": "Customer Data Export",
            "workflow_context": "account data export",
            "specific_user": "privacy operator",
            "buyer": "data protection officer",
        },
        "execution": {
            "mvp_scope": ["account database", "billing ledger"],
            "risks": ["Export contains regulated personal data and payment history."],
        },
        "metadata": {
            "data_categories": ["email", "payment history"],
            "integrations": ["Stripe", "Zendesk"],
            "regulatory_regions": ["GDPR"],
            "data_export": {
                "scope": "full customer account export",
                "requester": "verified account owner",
                "format": "JSONL archive",
                "delivery_path": "customer portal secure download",
                "retention_period": "72 hours after delivery",
            },
        },
        "evidence": {
            "insight_ids": ["ins-export"],
            "signal_ids": ["sig-dsr"],
            "rationale": "Customers need a portable account export.",
        },
    }


def test_customer_data_export_plan_complete_shape_and_strict_controls() -> None:
    plan = generate_customer_data_export_plan(_spec())

    assert plan["schema_version"] == CUSTOMER_DATA_EXPORT_PLAN_SCHEMA_VERSION
    assert plan["kind"] == KIND
    assert plan["source"]["idea_id"] == "export-1"
    assert plan["summary"]["title"] == "Customer Data Export"
    assert plan["summary"]["export_strictness"] == "strict"
    assert plan["summary"]["delivery_path"] == "customer portal secure download"
    assert plan["summary"]["export_format"] == "JSONL archive"
    assert set(plan) == {
        "schema_version",
        "kind",
        "source",
        "summary",
        "export_scope",
        "data_sources",
        "format_and_delivery",
        "access_controls",
        "validation_checks",
        "retention_and_cleanup",
        "owner_roles",
        "evidence_references",
    }

    assert plan["export_scope"]["included_data_categories"] == ["email", "payment history"]
    assert [item["system"] for item in plan["data_sources"]] == [
        "account database",
        "billing ledger",
        "Stripe",
        "Zendesk",
    ]
    assert plan["format_and_delivery"]["encryption"] == "per-request encrypted archive with separate credential channel"
    assert [item["id"] for item in plan["access_controls"]] == ["AC1", "AC2", "AC3", "AC4", "AC5"]
    assert [item["id"] for item in plan["validation_checks"]] == ["VC1", "VC2", "VC3", "VC4", "VC5"]
    assert plan["retention_and_cleanup"][0]["retention_period"] == "72 hours after delivery"
    assert {item["role"] for item in plan["owner_roles"]} == {
        "privacy_owner",
        "data_owner",
        "technical_owner",
        "security_owner",
        "support_owner",
    }
    assert [item["reference"] for item in plan["evidence_references"]] == [
        "insight:ins-export",
        "signal:sig-dsr",
        "Customers need a portable account export.",
    ]
    assert json.loads(json.dumps(plan))["kind"] == KIND


def test_customer_data_export_plan_sparse_input_defaults() -> None:
    plan = generate_customer_data_export_plan({})

    assert plan["summary"]["title"] == "Untitled TactSpec"
    assert plan["summary"]["export_strictness"] == "standard"
    assert plan["summary"]["data_categories"] == ["profile data", "account activity"]
    assert plan["summary"]["delivery_path"] == "time-limited secure download link"
    assert plan["data_sources"][0]["system"] == "primary application database"
    assert plan["format_and_delivery"]["format"] == "CSV and JSON package"
    assert [item["id"] for item in plan["access_controls"]] == ["AC1", "AC2", "AC3"]
    assert [item["id"] for item in plan["validation_checks"]] == ["VC1", "VC2", "VC3"]
    assert plan["evidence_references"] == []


def test_customer_data_export_plan_is_deterministic() -> None:
    first = generate_customer_data_export_plan(_spec())
    second = generate_customer_data_export_plan(_spec())

    assert first == second
