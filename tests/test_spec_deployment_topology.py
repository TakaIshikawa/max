from __future__ import annotations

import csv
import io
import json

from max.spec import generate_deployment_topology as exported_generate
from max.spec import render_deployment_topology_csv as exported_render_csv
from max.spec import render_deployment_topology_json as exported_render_json
from max.spec import render_deployment_topology_markdown as exported_render
from max.spec.deployment_topology import (
    DEPLOYMENT_TOPOLOGY_CSV_COLUMNS,
    DEPLOYMENT_TOPOLOGY_SCHEMA_VERSION,
    generate_deployment_topology,
    render_deployment_topology_csv,
    render_deployment_topology_json,
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


def test_render_deployment_topology_json_preserves_nested_topology_structure() -> None:
    topology = generate_deployment_topology(_rich_tact_spec())

    rendered = render_deployment_topology_json(topology)
    parsed = json.loads(rendered)

    assert parsed == topology
    assert rendered.endswith("\n")
    assert parsed["schema_version"] == DEPLOYMENT_TOPOLOGY_SCHEMA_VERSION
    assert isinstance(parsed["topology"], dict)
    assert isinstance(parsed["topology"]["runtime_components"], list)
    assert isinstance(parsed["topology"]["network_boundaries"][0]["controls"], list)
    assert isinstance(parsed["topology"]["deployment_sequence"][0]["dependencies"], list)
    assert parsed["environments"][0] == {
        "id": "ENV1",
        "name": "local",
        "purpose": "Developer validation with fake or sandbox credentials only.",
        "isolation": "No production data; use fixture-backed dependencies.",
    }
    assert parsed["topology"]["external_services"][0]["name"] == "Datadog"


def test_render_deployment_topology_json_is_pretty_and_deterministic() -> None:
    topology = generate_deployment_topology(_rich_tact_spec())

    first = render_deployment_topology_json(topology)
    second = render_deployment_topology_json(topology)
    parsed = json.loads(first)

    assert first == second
    assert first == json.dumps(topology, indent=2, sort_keys=True) + "\n"
    assert list(parsed) == sorted(topology)


def test_render_deployment_topology_csv_has_stable_sections_and_rows() -> None:
    topology = generate_deployment_topology(_rich_tact_spec())

    first = render_deployment_topology_csv(topology)
    second = render_deployment_topology_csv(topology)
    reader = csv.DictReader(io.StringIO(first))
    rows = list(reader)

    assert first == second
    assert first.endswith("\n")
    assert reader.fieldnames == list(DEPLOYMENT_TOPOLOGY_CSV_COLUMNS)
    assert first.splitlines()[0] == ",".join(DEPLOYMENT_TOPOLOGY_CSV_COLUMNS)
    assert [row["section"] for row in rows] == [
        *["runtime_components"] * len(topology["topology"]["runtime_components"]),
        *["backing_services"] * len(topology["topology"]["backing_services"]),
        *["external_services"] * len(topology["topology"]["external_services"]),
        *["configuration"] * len(topology["topology"]["configuration"]),
        *["network_boundaries"] * len(topology["topology"]["network_boundaries"]),
        *["deployment_sequence"] * len(topology["topology"]["deployment_sequence"]),
        *["environments"] * len(topology["environments"]),
        *["operational_notes"] * len(topology["operational_notes"]),
        *["assumptions"] * max(1, len(topology["assumptions"])),
    ]
    assert {row["section"] for row in rows} >= {
        "runtime_components",
        "backing_services",
        "external_services",
        "configuration",
        "network_boundaries",
        "deployment_sequence",
        "environments",
        "operational_notes",
        "assumptions",
    }
    assert all(row["source_idea_id"] == "bu-topology" for row in rows)
    assert all(row["title"] == "Renewal Signal Router" for row in rows)

    runtime_row = next(row for row in rows if row["section"] == "runtime_components")
    assert runtime_row["item_id"] == "CMP1"
    assert runtime_row["type"] == "component"
    assert runtime_row["technology"] == "FastAPI"
    assert runtime_row["network_boundary"] == "private application subnet or managed app runtime"
    assert runtime_row["derived_from"] == "project.workflow_context; solution.suggested_stack"

    deployment_row = next(
        row
        for row in rows
        if row["section"] == "deployment_sequence"
        and row["name"] == "Configure external integrations"
    )
    assert deployment_row["type"] == "step"
    assert deployment_row["owner"] == "integration_owner"
    assert deployment_row["dependencies"] == "EXT1; EXT2; EXT3"
    assert "webhook callbacks" in deployment_row["action"]

    environment_rows = [row for row in rows if row["section"] == "environments"]
    assert [row["environment"] for row in environment_rows] == ["local", "staging", "production"]
    assert "production vendor apps" in environment_rows[-1]["isolation"]


def test_render_deployment_topology_csv_redacts_secrets_and_serializes_booleans() -> None:
    rows = list(
        csv.DictReader(
            io.StringIO(render_deployment_topology_csv(generate_deployment_topology(_rich_tact_spec())))
        )
    )

    service_env_row = next(
        row
        for row in rows
        if row["section"] == "configuration" and row["name"] == "SERVICE_ENV"
    )
    assert service_env_row["secret"] == "false"
    assert service_env_row["example"] == "production"

    slack_secret_row = next(
        row
        for row in rows
        if row["section"] == "configuration" and row["name"] == "SLACK_API_TOKEN"
    )
    assert slack_secret_row["secret"] == "true"
    assert slack_secret_row["example"] == "[redacted]"
    assert slack_secret_row["required"] == "required"


def test_render_deployment_topology_csv_escapes_integration_names_with_punctuation() -> None:
    topology = generate_deployment_topology(_rich_tact_spec())
    topology["topology"]["external_services"][0]["name"] = 'Datadog, Inc. "Observability"'

    csv_text = render_deployment_topology_csv(topology)
    rows = list(csv.DictReader(io.StringIO(csv_text)))
    integration_row = next(
        row
        for row in rows
        if row["section"] == "external_services" and row["item_id"] == "EXT1"
    )

    assert '"Datadog, Inc. ""Observability"""' in csv_text
    assert integration_row["name"] == 'Datadog, Inc. "Observability"'


def test_deployment_topology_is_importable_from_spec_package() -> None:
    topology = exported_generate(_rich_tact_spec())
    markdown = exported_render(topology)
    csv_text = exported_render_csv(topology)
    json_text = exported_render_json(topology)

    assert topology["schema_version"] == DEPLOYMENT_TOPOLOGY_SCHEMA_VERSION
    assert markdown.startswith("# Renewal Signal Router Deployment Topology")
    assert csv_text.startswith(",".join(DEPLOYMENT_TOPOLOGY_CSV_COLUMNS))
    assert json.loads(json_text)["kind"] == "max.deployment_topology"
