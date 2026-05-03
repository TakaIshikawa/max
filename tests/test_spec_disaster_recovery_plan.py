from __future__ import annotations

import csv
from io import StringIO

from max.spec import generate_disaster_recovery_plan as exported_generate
from max.spec import render_disaster_recovery_plan_csv as exported_render_csv
from max.spec import render_disaster_recovery_plan_markdown as exported_render
from max.spec.disaster_recovery_plan import (
    DISASTER_RECOVERY_PLAN_CSV_COLUMNS,
    DISASTER_RECOVERY_PLAN_SCHEMA_VERSION,
    generate_disaster_recovery_plan,
    render_disaster_recovery_plan_csv,
    render_disaster_recovery_plan_markdown,
)


def _rich_tact_spec() -> dict:
    return {
        "schema_version": "tact-spec-preview/v1",
        "kind": "tact.project_spec",
        "source": {
            "system": "max",
            "type": "idea",
            "idea_id": "bu-dr-rich",
            "status": "approved",
            "domain": "customer-success",
            "category": "application",
        },
        "project": {
            "title": "Renewal Risk Console",
            "summary": "Coordinate renewal escalations across Salesforce and Slack.",
            "target_users": "customer success teams",
            "specific_user": "customer success operator",
            "buyer": "customer success director",
            "workflow_context": "Salesforce account review to Slack renewal alert",
        },
        "solution": {
            "technical_approach": (
                "FastAPI service with OAuth, Slack notifications, Salesforce sync, "
                "Postgres storage, Redis queues, and Datadog dashboards."
            ),
            "suggested_stack": {
                "backend": "FastAPI",
                "database": "Postgres",
                "messaging": "Slack",
                "queue": "Redis",
                "observability": "Datadog",
            },
        },
        "execution": {
            "validation_plan": "Run Salesforce sandbox sync and Slack alert fixture.",
            "risks": [
                "Salesforce outage may delay customer renewal workflows.",
                "Customer data restore must preserve audit records.",
            ],
        },
        "evaluation": {"overall_score": 84, "weaknesses": ["Integration reliability must be proven."]},
        "acceptance_criteria": {
            "functional_criteria": [
                {"id": "AC-F1", "statement": "Operator can send a Slack renewal alert."}
            ],
            "non_functional_criteria": [
                {"id": "AC-NF1", "statement": "Restored audit history is complete."}
            ],
        },
        "evidence": {
            "insight_ids": ["ins-renewal-risk"],
            "signal_ids": ["sig-cs-workflow"],
            "source_idea_ids": ["src-renewal"],
        },
    }


def test_generate_disaster_recovery_plan_is_stable_and_complete_for_tact_spec() -> None:
    first = generate_disaster_recovery_plan(_rich_tact_spec())
    second = generate_disaster_recovery_plan(_rich_tact_spec())

    assert first == second
    assert first["schema_version"] == DISASTER_RECOVERY_PLAN_SCHEMA_VERSION
    assert first["kind"] == "max.disaster_recovery_plan"
    assert first["source"]["idea_id"] == "bu-dr-rich"
    assert first["source"]["evidence_reference_count"] == 3
    assert first["summary"]["title"] == "Renewal Risk Console"
    assert first["summary"]["recovery_tier"] == "priority_restore"
    assert first["summary"]["recovery_time_objective"] == "4 hours"
    assert first["summary"]["recovery_point_objective"] == "15 minutes"
    assert set(first) == {
        "schema_version",
        "kind",
        "source",
        "summary",
        "recovery_objectives",
        "critical_capabilities",
        "critical_dependencies",
        "backup_restore_assumptions",
        "backup_strategy",
        "failover_steps",
        "restore_sequence",
        "data_integrity_checks",
        "validation_checks",
        "communications",
        "owner_roles",
        "validation_drills",
        "evidence_references",
        "gaps",
    }
    assert [item["name"] for item in first["critical_dependencies"]] == [
        "FastAPI",
        "Postgres",
        "Slack",
        "Datadog",
        "Redis",
        "Salesforce",
    ]
    assert any(item["id"] == "ASM4" for item in first["backup_restore_assumptions"])
    assert any(step["id"] == "FOV3" for step in first["failover_steps"])
    assert any(step["id"] == "RST3" for step in first["restore_sequence"])
    assert any(check["id"] == "DAT2" for check in first["data_integrity_checks"])
    assert {role["role"] for role in first["owner_roles"]} >= {
        "incident_commander",
        "technical_owner",
        "data_owner",
        "product_owner",
        "qa_owner",
    }
    assert {drill["id"] for drill in first["validation_drills"]} == {"DRL1", "DRL2", "DRL3"}
    assert first["gaps"] == []


def test_generate_disaster_recovery_plan_handles_sparse_inputs_with_actionable_defaults() -> None:
    plan = generate_disaster_recovery_plan(
        {
            "id": "bu-sparse-dr",
            "source": {"idea_id": "bu-sparse-dr"},
            "project": {"title": ""},
            "solution": {"suggested_stack": {}},
            "execution": {"risks": []},
            "evaluation": None,
        }
    )

    assert plan["summary"]["title"] == "bu-sparse-dr"
    assert plan["summary"]["workflow_context"] == "primary workflow"
    assert plan["summary"]["stack"] == "unspecified"
    assert plan["summary"]["recovery_tier"] == "limited_restore"
    assert plan["summary"]["recovery_time_objective"] == "2 business days"
    assert plan["summary"]["recovery_point_objective"] == "24 hours or last validated snapshot"
    assert plan["critical_dependencies"] == [
        {
            "id": "DEP1",
            "name": "documented deployment",
            "role": "runtime",
            "recovery_note": (
                "Restore the service runtime, configuration, and deployment pipeline "
                "from the last known-good release."
            ),
            "derived_from": ["solution.suggested_stack"],
        }
    ]
    assert "Run a representative primary workflow smoke test." in plan["validation_checks"][0]["action"]
    assert {gap["category"] for gap in plan["gaps"]} == {
        "missing_validation_plan",
        "missing_evaluation",
        "missing_acceptance_criteria",
        "missing_evidence_references",
    }


def test_render_disaster_recovery_plan_markdown_is_stable_readable_and_traceable() -> None:
    plan = generate_disaster_recovery_plan(_rich_tact_spec())

    first = render_disaster_recovery_plan_markdown(plan)
    second = render_disaster_recovery_plan_markdown(plan)

    assert first == second
    assert first.startswith("# Renewal Risk Console Disaster Recovery Plan")
    assert f"- Schema version: {DISASTER_RECOVERY_PLAN_SCHEMA_VERSION}" in first
    assert "- Source idea ID: bu-dr-rich" in first
    assert "- Evidence references: 3" in first
    assert "## Recovery Objectives" in first
    assert "## Critical Dependencies" in first
    assert "## Backup and Restore Assumptions" in first
    assert "## Failover Steps" in first
    assert "## Restore Sequence" in first
    assert "## Data Integrity Checks" in first
    assert "## Communications" in first
    assert "## Owner Roles" in first
    assert "## Validation Drills" in first
    assert "## Evidence References" in first
    assert "### RST3: Restore application" in first
    assert "### DRL2: Restore rehearsal" in first
    assert "`insight:ins-renewal-risk`" in first


def test_render_disaster_recovery_plan_csv_has_headers_and_generated_rows() -> None:
    plan = generate_disaster_recovery_plan(_rich_tact_spec())

    csv_text = render_disaster_recovery_plan_csv(plan)
    rows = list(csv.DictReader(StringIO(csv_text)))

    assert csv_text == render_disaster_recovery_plan_csv(plan)
    assert csv_text.splitlines()[0].split(",") == list(DISASTER_RECOVERY_PLAN_CSV_COLUMNS)
    assert rows[0] == {
        "section": "recovery_objectives",
        "type": "objective",
        "field": "objective",
        "source_idea_id": "bu-dr-rich",
        "title": "Renewal Risk Console",
        "item_id": "OBJ1",
        "name": "Restore primary workflow",
        "category": "",
        "severity": "",
        "owner": "",
        "timing": "RTO: 4 hours; RPO: 15 minutes",
        "cadence": "",
        "channel": "",
        "recovery_time_objective": "4 hours",
        "recovery_point_objective": "15 minutes",
        "critical_system": "",
        "scenario": "",
        "procedure": "",
        "step": "",
        "objective": (
            "Recover the Salesforce account review to Slack renewal alert path within 4 hours."
        ),
        "description": (
            "Recover the Salesforce account review to Slack renewal alert path within 4 hours."
        ),
        "verification": "",
        "derived_from": "project.workflow_context; summary.recovery_time_objective",
    }
    assert [row["item_id"] for row in rows if row["section"] == "critical_dependencies"] == [
        "DEP1",
        "DEP2",
        "DEP3",
        "DEP4",
        "DEP5",
        "DEP6",
    ]
    assert any(
        row["section"] == "critical_dependencies"
        and row["field"] == "critical_system"
        and row["critical_system"] == "Postgres"
        and row["category"] == "stateful_data"
        for row in rows
    )
    assert [row["item_id"] for row in rows if row["section"] == "restore_sequence"] == [
        "RST1",
        "RST2",
        "RST3",
        "RST4",
        "RST5",
    ]
    assert any(
        row["section"] == "communications"
        and row["owner"] == "product_owner"
        and row["channel"] == "customer_status_channel"
        for row in rows
    )
    assert any(
        row["section"] == "validation_drills"
        and row["item_id"] == "DRL2"
        and row["field"] == "step"
        and row["timing"] == "quarterly"
        and row["cadence"] == "quarterly"
        for row in rows
    )


def test_render_disaster_recovery_plan_csv_covers_scenarios_procedures_and_escaping() -> None:
    plan = {
        "source": {"idea_id": "idea-csv"},
        "summary": {
            "title": 'Payments, "Ledger"\nRestore',
            "recovery_time_objective": "30 minutes",
            "recovery_point_objective": "5 minutes",
        },
        "recovery_objectives": [
            {"id": "OBJ1", "name": "Restore writes", "description": "Resume ledger writes."}
        ],
        "critical_systems": [
            {"id": "SYS1", "name": "Postgres, primary", "role": "stateful_data"}
        ],
        "failure_scenarios": [
            {
                "id": "SCN1",
                "name": "Database unavailable",
                "severity": "critical",
                "owner": "technical_owner",
                "critical_system": "Postgres",
                "description": 'Primary database returns "read only", then fails over.',
            },
            {
                "id": "SCN2",
                "name": "Queue backlog",
                "severity": "high",
                "owner": "data_owner",
                "critical_system": "Redis",
                "scenario": "Queued writes exceed restore window.",
            },
        ],
        "backup_restore_procedures": [
            {
                "id": "PRC1",
                "name": "Restore snapshot",
                "owner": "data_owner",
                "procedure": "Restore latest snapshot, validate counts.",
            },
            {
                "id": "PRC2",
                "name": "Replay queue",
                "owner": "technical_owner",
                "procedure": 'Replay "accepted" jobs\nin timestamp order.',
            },
        ],
    }

    csv_text = render_disaster_recovery_plan_csv(plan)
    rows = list(csv.DictReader(StringIO(csv_text)))

    assert '"Payments, ""Ledger""\nRestore"' in csv_text
    assert '"Postgres, primary"' in csv_text
    assert '"Replay ""accepted"" jobs\nin timestamp order."' in csv_text
    assert [row["item_id"] for row in rows if row["section"] == "failure_scenarios"] == [
        "SCN1",
        "SCN2",
    ]
    assert any(
        row["section"] == "failure_scenarios"
        and row["field"] == "scenario"
        and row["severity"] == "critical"
        and row["owner"] == "technical_owner"
        for row in rows
    )
    assert [row["item_id"] for row in rows if row["section"] == "backup_restore_procedures"] == [
        "PRC1",
        "PRC2",
    ]
    assert rows[-1]["procedure"] == 'Replay "accepted" jobs\nin timestamp order.'


def test_render_disaster_recovery_plan_csv_handles_minimal_partial_plan() -> None:
    csv_text = render_disaster_recovery_plan_csv({"summary": {"title": "Minimal DR"}})
    rows = list(csv.DictReader(StringIO(csv_text)))

    assert csv_text == ",".join(DISASTER_RECOVERY_PLAN_CSV_COLUMNS) + "\n"
    assert rows == []

    partial_text = render_disaster_recovery_plan_csv(
        {
            "summary": {"title": "Partial DR"},
            "restore_sequence": [{"id": "RST1", "action": "Restore the service."}],
            "validation_drills": [{"id": "DRL1", "cadence": "annually"}],
        }
    )
    partial_rows = list(csv.DictReader(StringIO(partial_text)))

    assert [row["section"] for row in partial_rows] == ["restore_sequence", "validation_drills"]
    assert partial_rows[0]["step"] == "Restore the service."
    assert partial_rows[1]["cadence"] == "annually"


def test_generate_disaster_recovery_plan_orders_dependencies_deterministically() -> None:
    spec = _rich_tact_spec()
    spec["solution"]["suggested_stack"] = {
        "queue": "Redis",
        "backend": "FastAPI",
        "database": "Postgres",
    }

    plan = generate_disaster_recovery_plan(spec)

    assert [item["name"] for item in plan["critical_dependencies"]][:3] == [
        "FastAPI",
        "Postgres",
        "Redis",
    ]


def test_disaster_recovery_plan_is_importable_from_spec_package() -> None:
    plan = exported_generate(_rich_tact_spec())
    markdown = exported_render(plan)
    csv_text = exported_render_csv(plan)

    assert plan["schema_version"] == DISASTER_RECOVERY_PLAN_SCHEMA_VERSION
    assert markdown.startswith("# Renewal Risk Console Disaster Recovery Plan")
    assert csv_text.startswith(",".join(DISASTER_RECOVERY_PLAN_CSV_COLUMNS))
