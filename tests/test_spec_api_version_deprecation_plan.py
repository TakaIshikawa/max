from __future__ import annotations

import json

from max.spec.api_version_deprecation_plan import (
    API_VERSION_DEPRECATION_PLAN_SCHEMA_VERSION,
    KIND,
    generate_api_version_deprecation_plan,
)


def _spec() -> dict:
    return {
        "schema_version": "tact-spec-preview/v1",
        "kind": "tact.project_spec",
        "source": {"idea_id": "api-version-1", "domain": "platform"},
        "project": {
            "title": "Partner API",
            "workflow_context": "partner order ingestion",
            "specific_user": "partner developer",
            "buyer": "platform lead",
        },
        "execution": {
            "mvp_scope": ["public order API", "partner webhook"],
            "risks": ["Breaking public API contract change affects customer integrations."],
        },
        "metadata": {
            "api_deprecation": {
                "deprecated_version": "v1",
                "replacement_version": "v3",
                "consumers": ["Mobile App", "Partner Gateway"],
                "notice_days": 120,
                "breaking": True,
                "public_api": True,
            },
            "api_versions": {"surfaces": ["orders", "customers"]},
        },
        "evidence": {"insight_ids": ["ins-api"], "signal_ids": ["sig-usage"]},
    }


def test_api_version_deprecation_plan_complete_shape_and_strict_milestones() -> None:
    plan = generate_api_version_deprecation_plan(_spec())

    assert plan["schema_version"] == API_VERSION_DEPRECATION_PLAN_SCHEMA_VERSION
    assert plan["kind"] == KIND
    assert plan["summary"]["title"] == "Partner API"
    assert plan["summary"]["deprecation_strictness"] == "strict"
    assert plan["summary"]["migration_window_days"] == 120
    assert set(plan) == {
        "schema_version",
        "kind",
        "source",
        "summary",
        "deprecation_policy",
        "affected_consumers",
        "migration_timeline",
        "compatibility_checks",
        "communication_schedule",
        "rollback_or_extension_criteria",
        "evidence_references",
    }
    assert plan["deprecation_policy"]["deprecated_version"] == "v1"
    assert [item["consumer"] for item in plan["affected_consumers"]] == [
        "Mobile App",
        "Partner Gateway",
    ]
    assert [item["id"] for item in plan["migration_timeline"]] == ["MT1", "MT2", "MT3", "MT4"]
    assert [item["id"] for item in plan["compatibility_checks"]] == ["CC1", "CC2", "CC3", "CC4", "CC5"]
    assert [item["timing"] for item in plan["communication_schedule"]] == [
        "deprecation announcement",
        "30 days before removal",
        "14 days before removal",
        "7 days before removal",
    ]
    assert plan["rollback_or_extension_criteria"][1]["action"] == "restore v1 compatibility while remediation is completed"
    assert json.loads(json.dumps(plan))["kind"] == KIND


def test_api_version_deprecation_plan_breaking_public_hints_make_windows_stricter() -> None:
    standard = generate_api_version_deprecation_plan({"project": {"title": "Internal API"}})
    strict = generate_api_version_deprecation_plan(
        {
            "project": {"title": "Internal API"},
            "metadata": {
                "api_deprecation": {
                    "deprecated_version": "2024-01",
                    "replacement_version": "2026-01",
                    "notice_days": 30,
                    "public_api": True,
                    "breaking": True,
                }
            },
        }
    )

    assert standard["summary"]["deprecation_strictness"] == "standard"
    assert standard["summary"]["migration_window_days"] == 60
    assert len(standard["compatibility_checks"]) == 3
    assert strict["summary"]["deprecation_strictness"] == "strict"
    assert strict["summary"]["migration_window_days"] == 90
    assert len(strict["compatibility_checks"]) == 5


def test_api_version_deprecation_plan_sparse_input_defaults_are_deterministic() -> None:
    first = generate_api_version_deprecation_plan({})
    second = generate_api_version_deprecation_plan({})

    assert first == second
    assert first["deprecation_policy"]["deprecated_version"] == "v1"
    assert first["deprecation_policy"]["replacement_version"] == "v2"
    assert first["affected_consumers"][0]["consumer"] == "default API consumer"
    assert first["compatibility_checks"][0]["name"] == "Contract parity"
