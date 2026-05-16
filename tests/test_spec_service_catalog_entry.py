from __future__ import annotations

from types import SimpleNamespace

from max.spec.service_catalog_entry import KIND, SCHEMA_VERSION, generate_service_catalog_entry


def test_generate_service_catalog_entry_from_complete_spec() -> None:
    entry = generate_service_catalog_entry(
        {
            "source": {"idea_id": "svc-1", "system": "max", "type": "tact_spec", "domain": "ops"},
            "project": {
                "title": "Billing Portal",
                "summary": "Customer billing self-service.",
                "buyer": "finance lead",
                "specific_user": "account admin",
                "workflow_context": "invoice and payment updates",
            },
            "solution": {
                "technical_approach": "FastAPI service with Postgres and Stripe webhooks.",
                "suggested_stack": {"language": "python", "database": "postgres", "payments": "stripe"},
                "dependencies": ["Stripe", "Postgres", "Stripe"],
                "data_stores": ["billing-db"],
            },
            "metadata": {
                "service_owner": "billing team",
                "technical_owner": "platform team",
                "data_classification": "Restricted PII",
                "operational_contacts": ["#billing-ops", "#platform"],
                "slo_references": ["slo:billing-portal"],
                "evidence_links": ["runbook://billing"],
            },
            "evidence": {"signal_ids": ["sig-2"], "insight_ids": ["ins-1"]},
        }
    )

    assert entry["schema_version"] == SCHEMA_VERSION
    assert entry["kind"] == KIND
    assert entry["ownership"]["service_owner"] == "billing team"
    assert entry["purpose"]["name"] == "Billing Portal"
    assert entry["runtime"]["stack"] == "database=postgres, language=python, payments=stripe"
    assert entry["dependencies"] == ["Postgres", "Stripe"]
    assert entry["data"]["classification"] == "Restricted PII"
    assert entry["operations"]["contacts"] == ["#billing-ops", "#platform"]
    assert entry["operations"]["slo_references"] == ["slo:billing-portal"]
    assert entry["evidence"] == ["insight:ins-1", "runbook://billing", "signal:sig-2"]


def test_generate_service_catalog_entry_handles_sparse_buildable_unit() -> None:
    unit = SimpleNamespace(id="unit-1", title="Sparse Service", metadata={})

    entry = generate_service_catalog_entry(unit)

    assert entry["source"]["idea_id"] == "unit-1"
    assert entry["ownership"]["service_owner"] == "Unknown"
    assert entry["purpose"]["name"] == "Sparse Service"
    assert entry["runtime"]["stack"] == "Unknown"
    assert entry["dependencies"] == []
    assert entry["data"]["classification"] == "Unknown"
    assert entry["operations"]["contacts"] == []
    assert entry["operations"]["slo_references"] == []
    assert entry["evidence"] == []


def test_generate_service_catalog_entry_is_deterministic_and_sorts_collections() -> None:
    payload = {
        "id": "svc",
        "title": "Stable",
        "metadata": {
            "dependencies": ["zeta", "Alpha", "alpha", "Beta"],
            "operational_contacts": ["pagerduty", "email", "pagerduty"],
            "slo_references": ["slo-z", "slo-a"],
        },
    }

    first = generate_service_catalog_entry(payload)
    second = generate_service_catalog_entry(payload)

    assert first == second
    assert first["dependencies"] == ["Alpha", "alpha", "Beta", "zeta"]
    assert first["operations"]["contacts"] == ["email", "pagerduty"]
    assert first["operations"]["slo_references"] == ["slo-a", "slo-z"]
