"""Tests for TactSpec smoke test plan generation."""

from __future__ import annotations

import json

from max.spec import generate_smoke_test_plan as exported_generate
from max.spec import render_smoke_test_plan_markdown as exported_render
from max.spec.generator import generate_spec_preview
from max.spec.smoke_test_plan import (
    SMOKE_TEST_PLAN_SCHEMA_VERSION,
    generate_smoke_test_plan,
    render_smoke_test_plan_markdown,
)


def _minimal_tact_spec() -> dict:
    return {
        "schema_version": "tact-spec-preview/v1",
        "kind": "tact.project_spec",
        "source": {"idea_id": "bu-smoke", "status": "approved"},
        "project": {
            "title": "Agent Release Gate",
            "specific_user": "platform engineer",
            "buyer": "engineering manager",
            "workflow_context": "agent-authored pull request deployment gate",
        },
        "solution": {
            "technical_approach": "Python CLI with GitHub check output.",
            "suggested_stack": {"language": "python", "ci": "github-actions"},
            "composability_notes": "Publishes a GitHub check result.",
        },
        "execution": {
            "mvp_scope": ["CLI runner", "GitHub check output"],
            "validation_plan": "Run against a synthetic pull request fixture.",
            "risks": ["GitHub API outages may block release gates"],
        },
        "evidence": {
            "insight_ids": ["ins-smoke"],
            "signal_ids": ["sig-smoke"],
            "rationale": "Teams need immediate release verification.",
        },
        "evaluation": {"overall_score": 82.0, "recommendation": "yes"},
    }


def test_generate_smoke_test_plan_is_deterministic_for_minimal_tact_spec() -> None:
    first = generate_smoke_test_plan(_minimal_tact_spec())
    second = generate_smoke_test_plan(_minimal_tact_spec())

    assert first == second
    assert first["schema_version"] == SMOKE_TEST_PLAN_SCHEMA_VERSION
    assert first["kind"] == "max.smoke_test_plan"
    assert first["source"]["idea_id"] == "bu-smoke"
    assert first["source"]["tact_spec_schema_version"] == "tact-spec-preview/v1"
    assert first["summary"] == {
        "title": "Agent Release Gate",
        "target_user": "platform engineer",
        "buyer": "engineering manager",
        "workflow_context": "agent-authored pull request deployment gate",
        "stack": "ci=github-actions, language=python",
        "validation_plan": "Run against a synthetic pull request fixture.",
        "recommendation": "yes",
        "overall_score": 82.0,
    }
    assert set(first) == {
        "schema_version",
        "kind",
        "source",
        "summary",
        "user_journey_checks",
        "deployment_verification_checks",
        "integration_checks",
        "data_integrity_checks",
        "observability_checks",
        "rollback_verification_checks",
        "owners",
        "evidence_references",
    }
    assert [check["id"] for check in first["user_journey_checks"]] == [
        "UJ1",
        "UJ2",
        "UJ3",
        "UJ4",
    ]
    assert first["deployment_verification_checks"][0]["owner"] == "release_owner"
    assert first["integration_checks"][0]["category"] == "integration"
    assert first["data_integrity_checks"][0]["category"] == "data_integrity"
    assert first["observability_checks"][0]["category"] == "observability"
    assert first["rollback_verification_checks"][0]["category"] == "rollback"
    assert [reference["id"] for reference in first["evidence_references"]] == [
        "insight:ins-smoke",
        "signal:sig-smoke",
        "spec:evidence_rationale",
    ]


def test_generate_smoke_test_plan_degrades_for_sparse_specs() -> None:
    plan = generate_smoke_test_plan(
        {
            "schema_version": "tact-spec-preview/v1",
            "kind": "tact.project_spec",
            "source": {"idea_id": "bu-sparse"},
            "project": {"title": ""},
            "solution": {"suggested_stack": {}},
            "execution": {"mvp_scope": [], "risks": []},
            "evidence": {},
            "evaluation": None,
        }
    )

    assert plan["summary"]["title"] == "bu-sparse"
    assert plan["summary"]["target_user"] == "primary user"
    assert plan["summary"]["buyer"] == "launch sponsor"
    assert plan["summary"]["workflow_context"] == "primary workflow"
    assert plan["summary"]["stack"] == "unspecified"
    assert [reference["id"] for reference in plan["evidence_references"]] == ["spec:fallback"]
    assert all(
        check["evidence_reference_ids"] == ["spec:fallback"]
        for section in (
            "user_journey_checks",
            "deployment_verification_checks",
            "integration_checks",
            "data_integrity_checks",
            "observability_checks",
            "rollback_verification_checks",
        )
        for check in plan[section]
    )


def test_smoke_test_plan_is_json_serializable(sample_unit, sample_evaluation) -> None:
    spec = generate_spec_preview(sample_unit, sample_evaluation)
    plan = generate_smoke_test_plan(spec)

    assert json.loads(json.dumps(plan))["source"]["idea_id"] == "bu-test001"


def test_render_smoke_test_plan_markdown_is_stable_and_includes_owners() -> None:
    plan = generate_smoke_test_plan(_minimal_tact_spec())

    first = render_smoke_test_plan_markdown(plan)
    second = render_smoke_test_plan_markdown(plan)

    assert first == second
    assert first.startswith("# Agent Release Gate Smoke Test Plan")
    assert f"- Schema version: {SMOKE_TEST_PLAN_SCHEMA_VERSION}" in first
    assert "## User Journey Checks" in first
    assert "## Deployment Verification Checks" in first
    assert "## Integration Checks" in first
    assert "## Data Integrity Checks" in first
    assert "## Observability Checks" in first
    assert "## Rollback Verification Checks" in first
    assert "## Owners" in first
    assert "### UJ1: critical_user_journey" in first
    assert "- Owner: product_owner" in first
    assert "### OWN2: engineering_owner" in first
    assert "- Suggested owner: python service owner" in first
    assert "`signal:sig-smoke`" in first


def test_smoke_test_plan_is_importable_from_spec_package() -> None:
    plan = exported_generate(_minimal_tact_spec())
    markdown = exported_render(plan)

    assert plan["schema_version"] == SMOKE_TEST_PLAN_SCHEMA_VERSION
    assert markdown.startswith("# Agent Release Gate Smoke Test Plan")


def test_generate_spec_preview_embeds_smoke_test_plan_artifact(
    sample_unit, sample_evaluation
) -> None:
    spec = generate_spec_preview(sample_unit, sample_evaluation)

    smoke_plan = spec["artifacts"]["smoke_test_plan"]

    assert smoke_plan["schema_version"] == SMOKE_TEST_PLAN_SCHEMA_VERSION
    assert smoke_plan["source"]["idea_id"] == "bu-test001"
    assert smoke_plan["summary"]["workflow_context"] == "pre-release CI validation"
    assert smoke_plan["observability_checks"]
