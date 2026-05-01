from __future__ import annotations

from max.spec import generate_deployment_topology as exported_generate
from max.spec import render_deployment_topology_markdown as exported_render
from max.spec.deployment_topology import (
    DEPLOYMENT_TOPOLOGY_SCHEMA_VERSION,
    generate_deployment_topology,
    render_deployment_topology_markdown,
)


def _rich_tact_spec() -> dict:
    return {
        "schema_version": "tact-spec-preview/v1",
        "kind": "tact.project_spec",
        "source": {
            "system": "max",
            "type": "idea",
            "idea_id": "bu-topology",
            "status": "approved",
            "domain": "customer-success",
            "category": "workflow-automation",
        },
        "project": {
            "title": "Renewal Signal Router",
            "summary": "Route customer renewal risk from Salesforce to Slack with audit review.",
            "value_proposition": "Prevent missed renewal escalations.",
            "target_users": "customer success teams",
            "specific_user": "customer success operator",
            "buyer": "customer success director",
            "workflow_context": "Salesforce account review to Slack renewal alert",
        },
        "solution": {
            "approach": "Sync account risk fields and publish Slack workflow alerts.",
            "technical_approach": (
                "FastAPI webhook API with React dashboard, OAuth, Postgres audit store, "
                "Redis queue workers, Slack callbacks, Salesforce sync, and Datadog dashboards."
            ),
            "suggested_stack": {
                "auth": "OAuth",
                "backend": "FastAPI",
                "cache": "Redis",
                "crm": "Salesforce",
                "database": "Postgres",
                "frontend": "React",
                "messaging": "Slack",
                "observability": "Datadog",
                "queue": "Redis queue",
            },
        },
        "execution": {
            "mvp_scope": [
                "Salesforce account sync",
                "Slack renewal notification",
                "React operator dashboard",
                "Background retry worker",
            ],
            "validation_plan": "Run OAuth sandbox sync, webhook checks, and acceptance smoke tests.",
            "risks": [
                "Salesforce API outages may delay Slack alerts.",
                "Customer account records require retention controls.",
            ],
        },
        "evaluation": {
            "overall_score": 87.0,
            "recommendation": "yes",
            "weaknesses": [
                "Integration reliability must be validated before production data access."
            ],
        },
        "acceptance_criteria": {
            "functional_criteria": [
                {"id": "AC-F1", "statement": "Operator can trigger a Slack renewal alert."},
                {"id": "AC-F2", "statement": "Salesforce status changes are synced."},
            ],
            "non_functional_criteria": [
                {"id": "AC-NF1", "statement": "Secrets are never written to logs."},
            ],
        },
    }


def test_generate_deployment_topology_is_stable_and_complete_for_rich_specs() -> None:
    first = generate_deployment_topology(_rich_tact_spec())
    second = generate_deployment_topology(_rich_tact_spec())

    assert first == second
    assert first["schema_version"] == DEPLOYMENT_TOPOLOGY_SCHEMA_VERSION
    assert first["kind"] == "max.deployment_topology"
    assert first["source"]["idea_id"] == "bu-topology"
    assert first["summary"]["title"] == "Renewal Signal Router"
    assert first["summary"]["stack"] == (
        "auth=OAuth, backend=FastAPI, cache=Redis, crm=Salesforce, database=Postgres, "
        "frontend=React, messaging=Slack, observability=Datadog, queue=Redis queue"
    )
    assert set(first) == {
        "schema_version",
        "kind",
        "source",
        "summary",
        "topology",
        "environments",
        "operational_notes",
        "assumptions",
    }
    assert set(first["topology"]) == {
        "runtime_components",
        "backing_services",
        "external_services",
        "configuration",
        "network_boundaries",
        "deployment_sequence",
    }
    assert {item["category"] for item in first["topology"]["runtime_components"]} >= {
        "application-runtime",
        "api",
        "frontend",
        "worker",
    }
    assert {item["name"] for item in first["topology"]["backing_services"]} >= {
        "Postgres",
        "Redis",
        "Redis queue",
    }
    assert {item["name"] for item in first["topology"]["external_services"]} >= {
        "Datadog",
        "Salesforce",
        "Slack",
    }
    assert {item["name"] for item in first["topology"]["configuration"]} >= {
        "SERVICE_ENV",
        "APP_BASE_URL",
        "DATABASE_URL",
        "REDIS_URL",
        "SLACK_API_TOKEN",
        "SALESFORCE_API_TOKEN",
        "DATADOG_API_TOKEN",
        "AUTH_CLIENT_SECRET",
    }
    assert first["summary"]["secret_count"] >= 5
    assert any(item["name"] == "vendor-egress" for item in first["topology"]["network_boundaries"])
    assert any(
        item["name"] == "Configure external integrations"
        for item in first["topology"]["deployment_sequence"]
    )
    assert [item["name"] for item in first["environments"]] == ["local", "staging", "production"]


def test_generate_deployment_topology_handles_sparse_specs_with_conservative_assumptions() -> None:
    topology = generate_deployment_topology(
        {
            "schema_version": "tact-spec-preview/v1",
            "kind": "tact.project_spec",
            "source": {"idea_id": "bu-sparse-topology"},
            "project": {"title": ""},
            "solution": {"suggested_stack": {}},
            "execution": {"mvp_scope": [], "risks": []},
            "evaluation": None,
        }
    )

    assert topology["summary"]["title"] == "bu-sparse-topology"
    assert topology["summary"]["workflow_context"] == "primary workflow"
    assert topology["summary"]["stack"] == "unspecified"
    assert topology["topology"]["backing_services"] == []
    assert topology["topology"]["external_services"] == []
    assert topology["topology"]["runtime_components"][0]["technology"] == "application runtime"
    assert {item["name"] for item in topology["topology"]["configuration"]} == {
        "SERVICE_ENV",
        "APP_BASE_URL",
        "BU_SPARSE_TOPOLOGY_FEATURE_ENABLED",
        "LOG_LEVEL",
    }
    assert any(
        item["name"] == "authentication-boundary"
        for item in topology["topology"]["network_boundaries"]
    )
    assert "No backing data store is named" in " ".join(topology["assumptions"])
    assert "No external integration is detected" in " ".join(topology["assumptions"])


def test_generate_deployment_topology_uses_deterministic_ordering_for_stack_and_integrations() -> (
    None
):
    spec = _rich_tact_spec()
    spec["solution"]["suggested_stack"] = {
        "messaging": "Slack",
        "database": "Postgres",
        "observability": "Datadog",
        "backend": "FastAPI",
        "crm": "Salesforce",
        "auth": "OAuth",
    }

    topology = generate_deployment_topology(spec)

    assert topology["summary"]["stack"] == (
        "auth=OAuth, backend=FastAPI, crm=Salesforce, database=Postgres, "
        "messaging=Slack, observability=Datadog"
    )
    assert [item["name"] for item in topology["topology"]["external_services"]] == [
        "Datadog",
        "Salesforce",
        "Slack",
    ]
    assert [item["name"] for item in topology["topology"]["configuration"]][:4] == [
        "SERVICE_ENV",
        "APP_BASE_URL",
        "RENEWAL_SIGNAL_ROUTER_FEATURE_ENABLED",
        "LOG_LEVEL",
    ]


def test_render_deployment_topology_markdown_is_readable_and_deterministic() -> None:
    topology = generate_deployment_topology(_rich_tact_spec())

    first = render_deployment_topology_markdown(topology)
    second = render_deployment_topology_markdown(topology)

    assert first == second
    assert first.startswith("# Renewal Signal Router Deployment Topology")
    assert f"- Schema version: {DEPLOYMENT_TOPOLOGY_SCHEMA_VERSION}" in first
    assert "## Topology - Runtime Components" in first
    assert "## Topology - Backing Services" in first
    assert "## Topology - External Services" in first
    assert "## Configuration and Secrets" in first
    assert "## Network Boundaries" in first
    assert "## Deployment Sequence" in first
    assert "## Environments" in first
    assert "## Operational Notes" in first
    assert "### NET" in first
    assert "### DEP" in first
    assert "Salesforce" in first
    assert "Slack" in first
    assert "production" in first


def test_deployment_topology_is_importable_from_spec_package() -> None:
    topology = exported_generate(_rich_tact_spec())
    markdown = exported_render(topology)

    assert topology["schema_version"] == DEPLOYMENT_TOPOLOGY_SCHEMA_VERSION
    assert markdown.startswith("# Renewal Signal Router Deployment Topology")
