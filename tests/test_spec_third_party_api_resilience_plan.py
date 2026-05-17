from __future__ import annotations

import json

from max.spec.third_party_api_resilience_plan import (
    KIND,
    THIRD_PARTY_API_RESILIENCE_PLAN_SCHEMA_VERSION,
    generate_third_party_api_resilience_plan,
)


def _spec() -> dict:
    return {
        "schema_version": "tact-spec-preview/v1",
        "kind": "tact.project_spec",
        "source": {"idea_id": "api-resilience-1", "domain": "operations"},
        "project": {
            "title": "Renewal Automation",
            "workflow_context": "renewal quote workflow",
            "specific_user": "customer success manager",
            "buyer": "revenue operations lead",
        },
        "solution": {
            "dependencies": [{"name": "Okta", "type": "auth"}],
            "suggested_stack": {
                "payments": "Stripe",
                "crm": "Salesforce",
                "support": "Zendesk",
                "observability": "Datadog",
            },
        },
        "metadata": {
            "third_party_dependencies": [
                {"name": "HubSpot", "category": "crm"},
                "OpenAI API",
            ]
        },
        "artifacts": {
            "dependency_inventory": {
                "dependencies": [
                    {"name": "Stripe", "type": "payments"},
                    {"name": "Zendesk", "type": "support"},
                ]
            }
        },
        "evidence": {
            "insight_ids": ["ins-1"],
            "signal_ids": ["sig-1"],
            "rationale": "Revenue workflow relies on external providers.",
        },
    }


def test_third_party_api_resilience_plan_extracts_and_prioritizes_dependencies() -> None:
    plan = generate_third_party_api_resilience_plan(_spec())

    assert plan["schema_version"] == THIRD_PARTY_API_RESILIENCE_PLAN_SCHEMA_VERSION
    assert plan["kind"] == KIND
    assert plan["source"]["idea_id"] == "api-resilience-1"
    assert plan["summary"]["title"] == "Renewal Automation"
    assert plan["summary"]["resilience_posture"] == "strict"
    assert set(plan) == {
        "schema_version",
        "kind",
        "source",
        "summary",
        "dependency_inventory",
        "failure_modes",
        "fallback_strategies",
        "retry_and_timeout_policy",
        "monitoring_signals",
        "owner_roles",
        "evidence_references",
    }

    by_name = {item["name"]: item for item in plan["dependency_inventory"]}
    assert by_name["Stripe"]["category"] == "payments"
    assert by_name["Stripe"]["risk_level"] == "high"
    assert by_name["Stripe"]["risk_hint"] == "financial-critical"
    assert by_name["Okta"]["category"] == "auth"
    assert by_name["Salesforce"]["category"] == "crm"
    assert by_name["Zendesk"]["category"] == "support"
    assert "solution.suggested_stack.payments" in by_name["Stripe"]["source_fields"]
    assert "dependency_inventory.dependencies[1]" in by_name["Stripe"]["source_fields"]

    assert [item["id"] for item in plan["failure_modes"]] == ["FM1", "FM2", "FM3"]
    assert all(item["severity"] == "high" for item in plan["failure_modes"])
    assert any("duplicate charges" in item["strategy"] for item in plan["fallback_strategies"])
    assert any("idempotency keys" in item["strategy"] for item in plan["fallback_strategies"])
    assert all("circuit_breaker" in item for item in plan["retry_and_timeout_policy"])
    assert all("rate-limit responses" in item["signals"] for item in plan["monitoring_signals"])
    assert {item["role"] for item in plan["owner_roles"]} == {
        "technical_owner",
        "product_owner",
        "vendor_owner",
        "support_owner",
    }
    assert [item["reference"] for item in plan["evidence_references"]] == [
        "insight:ins-1",
        "signal:sig-1",
        "Revenue workflow relies on external providers.",
    ]
    assert json.loads(json.dumps(plan))["kind"] == KIND


def test_third_party_api_resilience_plan_sparse_input_defaults() -> None:
    plan = generate_third_party_api_resilience_plan({})

    assert plan["summary"]["title"] == "Untitled TactSpec"
    assert plan["summary"]["dependency_count"] == 1
    assert plan["dependency_inventory"][0]["name"] == "Unspecified third-party API"
    assert plan["dependency_inventory"][0]["category"] == "missing_inventory"
    assert plan["dependency_inventory"][0]["risk_level"] == "high"
    assert plan["fallback_strategies"][0]["strategy"].startswith("Block launch readiness")
    assert plan["evidence_references"] == []


def test_third_party_api_resilience_plan_is_deterministic() -> None:
    first = generate_third_party_api_resilience_plan(_spec())
    second = generate_third_party_api_resilience_plan(_spec())

    assert first == second
