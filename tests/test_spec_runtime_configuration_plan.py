from __future__ import annotations

import csv
from io import StringIO

from max.spec import generate_runtime_configuration_plan as exported_generate
from max.spec import render_runtime_configuration_plan_csv as exported_render_csv
from max.spec import render_runtime_configuration_plan_markdown as exported_render_markdown
from max.spec.runtime_configuration_plan import (
    KIND,
    RUNTIME_CONFIGURATION_PLAN_CSV_COLUMNS,
    SCHEMA_VERSION,
    generate_runtime_configuration_plan,
    render_runtime_configuration_plan_csv,
    render_runtime_configuration_plan_markdown,
)


def _rich_tact_spec() -> dict:
    return {
        "schema_version": "tact-spec-preview/v1",
        "kind": "tact.project_spec",
        "source": {
            "system": "max",
            "type": "idea",
            "idea_id": "bu-runtime-config",
            "status": "approved",
            "domain": "customer-success",
            "category": "workflow-automation",
        },
        "project": {
            "title": "Renewal Signal Router",
            "summary": "Route customer renewal risk from Salesforce to Slack.",
            "target_users": "customer success teams",
            "specific_user": "customer success operator",
            "buyer": "customer success director",
            "workflow_context": "Salesforce account review to Slack renewal alert",
        },
        "solution": {
            "approach": "Sync account risk fields and publish Slack workflow alerts.",
            "technical_approach": (
                "FastAPI webhook API with OAuth, Postgres audit storage, Redis queue workers, "
                "Slack callbacks, Salesforce sync, and Datadog dashboards."
            ),
            "suggested_stack": {
                "auth": "OAuth",
                "backend": "FastAPI",
                "cache": "Redis",
                "crm": "Salesforce",
                "database": "Postgres",
                "messaging": "Slack",
                "observability": "Datadog",
                "queue": "Redis queue",
            },
            "composability_notes": "Expose webhook events and publish Slack notifications.",
        },
        "execution": {
            "mvp_scope": [
                "Salesforce account sync",
                "Slack renewal notification",
                "Background retry worker",
            ],
            "validation_plan": "Run OAuth sandbox sync, webhook checks, and smoke tests.",
            "risks": [
                "Salesforce API outages may delay Slack alerts.",
                "Credential leakage must be prevented in logs.",
            ],
        },
        "evidence": {
            "rationale": "Renewal operators miss handoffs when account state changes.",
            "insight_ids": ["ins-1"],
            "signal_ids": ["sig-1"],
            "source_idea_ids": ["idea-source-1"],
        },
    }


def test_generate_runtime_configuration_plan_is_stable_and_complete_for_stack_inputs() -> None:
    first = generate_runtime_configuration_plan(_rich_tact_spec())
    second = generate_runtime_configuration_plan(_rich_tact_spec())

    assert first == second
    assert first["schema_version"] == SCHEMA_VERSION
    assert first["kind"] == KIND
    assert first["source"]["idea_id"] == "bu-runtime-config"
    assert first["summary"]["title"] == "Renewal Signal Router"
    assert first["summary"]["stack"] == (
        "auth=OAuth, backend=FastAPI, cache=Redis, crm=Salesforce, database=Postgres, "
        "messaging=Slack, observability=Datadog, queue=Redis queue"
    )
    assert set(first) == {
        "schema_version",
        "kind",
        "source",
        "summary",
        "configuration_items",
        "feature_toggles",
        "secrets",
        "operational_limits",
        "validation_checks",
        "rollback_defaults",
        "owner_handoffs",
        "evidence_references",
    }

    config_names = {item["name"] for item in first["configuration_items"]}
    assert {
        "SERVICE_ENV",
        "APP_BASE_URL",
        "LOG_LEVEL",
        "RENEWAL_SIGNAL_ROUTER_CONFIG_VERSION",
        "DATABASE_URL",
        "REDIS_URL",
        "QUEUE_URL",
        "AUTH_ISSUER_URL",
        "OBSERVABILITY_ENV",
        "SLACK_BASE_URL",
        "SALESFORCE_BASE_URL",
        "DATADOG_BASE_URL",
    } <= config_names

    toggle_names = {item["name"] for item in first["feature_toggles"]}
    assert {
        "RENEWAL_SIGNAL_ROUTER_FEATURE_ENABLED",
        "RENEWAL_SIGNAL_ROUTER_INTEGRATIONS_ENABLED",
        "RENEWAL_SIGNAL_ROUTER_WRITE_ACTIONS_ENABLED",
    } <= toggle_names

    assert {item["name"] for item in first["secrets"]} >= {
        "DATA_STORE_CONNECTION",
        "AUTH_CLIENT_SECRET",
        "SLACK_API_TOKEN",
        "SALESFORCE_API_TOKEN",
        "DATADOG_API_TOKEN",
    }
    assert {item["name"] for item in first["operational_limits"]} >= {
        "REQUEST_TIMEOUT_SECONDS",
        "MAX_RETRY_ATTEMPTS",
        "MAX_PAYLOAD_BYTES",
        "WORKER_CONCURRENCY",
        "RATE_LIMIT_PER_MINUTE",
    }
    assert first["evidence_references"] == [
        "ins-1",
        "sig-1",
        "idea-source-1",
        "Renewal operators miss handoffs when account state changes.",
    ]


def test_secrets_describe_purpose_and_owner_without_emitting_values() -> None:
    plan = generate_runtime_configuration_plan(_rich_tact_spec())
    markdown = render_runtime_configuration_plan_markdown(plan)
    csv_text = render_runtime_configuration_plan_csv(plan)

    for secret in plan["secrets"]:
        assert set(secret) == {"id", "name", "purpose", "owner", "storage", "rotation", "source_fields"}
        assert secret["purpose"]
        assert secret["owner"]
        assert "value" not in secret
        assert "secret_value" not in secret

    assert "xoxb-" not in markdown
    assert "xoxb-" not in csv_text
    assert "[secret reference]" in markdown
    assert "[secret reference]" in csv_text


def test_sparse_spec_produces_conservative_defaults() -> None:
    plan = generate_runtime_configuration_plan(
        {
            "schema_version": "tact-spec-preview/v1",
            "kind": "tact.project_spec",
            "source": {"idea_id": "bu-sparse-runtime"},
            "project": {"title": ""},
            "solution": {"suggested_stack": {}},
            "execution": {"mvp_scope": [], "risks": []},
        }
    )

    assert plan["summary"]["title"] == "bu-sparse-runtime"
    assert plan["summary"]["workflow_context"] == "primary workflow"
    assert plan["summary"]["stack"] == "unspecified"
    assert {item["name"] for item in plan["configuration_items"]} == {
        "SERVICE_ENV",
        "APP_BASE_URL",
        "LOG_LEVEL",
        "BU_SPARSE_RUNTIME_CONFIG_VERSION",
    }
    assert [item["name"] for item in plan["feature_toggles"]] == [
        "BU_SPARSE_RUNTIME_FEATURE_ENABLED"
    ]
    assert plan["secrets"][0]["name"] == "RUNTIME_SECRET_PLACEHOLDER"
    assert plan["evidence_references"] == []


def test_markdown_and_csv_renderers_are_deterministic_and_parseable() -> None:
    plan = generate_runtime_configuration_plan(_rich_tact_spec())

    markdown = render_runtime_configuration_plan_markdown(plan)
    csv_text = render_runtime_configuration_plan_csv(plan)
    rows = list(csv.DictReader(StringIO(csv_text)))

    assert markdown == render_runtime_configuration_plan_markdown(plan)
    assert csv_text == render_runtime_configuration_plan_csv(plan)
    assert markdown.startswith("# Renewal Signal Router Runtime Configuration Plan")
    assert "## Configuration Items" in markdown
    assert "## Feature Toggles" in markdown
    assert "## Secrets" in markdown
    assert "## Rollback Defaults" in markdown
    assert csv_text.splitlines()[0] == ",".join(RUNTIME_CONFIGURATION_PLAN_CSV_COLUMNS)
    assert rows
    assert {row["section"] for row in rows} >= {
        "configuration_items",
        "feature_toggles",
        "secrets",
        "operational_limits",
        "validation_checks",
        "rollback_defaults",
        "owner_handoffs",
        "evidence_references",
    }
    assert {row["type"] for row in rows} >= {
        "environment_variable",
        "feature_toggle",
        "secret_reference",
        "limit",
        "validation",
        "rollback",
        "handoff",
        "evidence",
    }


def test_csv_renderer_handles_empty_or_invalid_plan_input() -> None:
    csv_text = render_runtime_configuration_plan_csv(None)  # type: ignore[arg-type]

    assert csv_text == ",".join(RUNTIME_CONFIGURATION_PLAN_CSV_COLUMNS) + "\n"
    assert render_runtime_configuration_plan_markdown(None).startswith(  # type: ignore[arg-type]
        "# TactSpec Runtime Configuration Plan"
    )


def test_runtime_configuration_plan_is_importable_from_spec_package() -> None:
    plan = exported_generate(_rich_tact_spec())
    csv_text = exported_render_csv(plan)
    markdown = exported_render_markdown(plan)

    assert plan["schema_version"] == SCHEMA_VERSION
    assert csv_text.startswith(",".join(RUNTIME_CONFIGURATION_PLAN_CSV_COLUMNS))
    assert markdown.startswith("# Renewal Signal Router Runtime Configuration Plan")
