"""Tests for idea spec bundle generation."""

from __future__ import annotations

from max.spec.bundle import (
    SPEC_BUNDLE_SCHEMA_VERSION,
    generate_spec_bundle,
    render_spec_bundle_markdown,
)


def test_generate_spec_bundle_includes_all_artifacts(
    store,
    sample_signal,
    sample_insight,
    sample_unit,
    sample_evaluation,
) -> None:
    store.insert_signal(sample_signal)
    store.insert_insight(sample_insight)
    store.insert_buildable_unit(sample_unit)
    store.insert_evaluation(sample_evaluation)

    bundle = generate_spec_bundle(sample_unit, sample_evaluation, store)

    assert bundle["schema_version"] == SPEC_BUNDLE_SCHEMA_VERSION
    assert bundle["kind"] == "max.spec_bundle"
    assert bundle["idea_id"] == "bu-test001"
    assert bundle["generated_at"]
    assert set(bundle["artifacts"]) == {
        "spec_preview",
        "readiness",
        "implementation_plan",
        "launch_checklist",
        "rollback_plan",
        "disaster_recovery_plan",
        "acceptance_criteria",
        "experiment_card",
        "data_classification",
        "data_retention_schedule",
        "privacy_impact_assessment",
        "dependency_inventory",
        "risk_register",
        "threat_model",
        "slo_plan",
        "review_gate",
        "evidence_density",
        "evidence_chain_summary",
    }
    assert bundle["artifacts"]["spec_preview"]["schema_version"] == "tact-spec-preview/v1"
    assert (
        bundle["artifacts"]["implementation_plan"]["schema_version"] == "max-implementation-plan/v1"
    )
    assert bundle["artifacts"]["launch_checklist"]["schema_version"] == "max-launch-checklist/v1"
    assert bundle["artifacts"]["rollback_plan"]["schema_version"] == "max-rollback-plan/v1"
    assert (
        bundle["artifacts"]["disaster_recovery_plan"]["schema_version"]
        == "max-disaster-recovery-plan/v1"
    )
    assert (
        bundle["artifacts"]["acceptance_criteria"]["schema_version"] == "max-acceptance-criteria/v1"
    )
    assert bundle["artifacts"]["experiment_card"]["schema_version"] == "max-experiment-card/v1"
    assert (
        bundle["artifacts"]["data_classification"]["schema_version"] == "max-data-classification/v1"
    )
    assert bundle["artifacts"]["data_classification"]["kind"] == "max.spec.data_classification"
    assert (
        bundle["artifacts"]["data_retention_schedule"]["schema_version"]
        == "max-data-retention-schedule/v1"
    )
    assert (
        bundle["artifacts"]["data_retention_schedule"]["kind"]
        == "max.spec.data_retention_schedule"
    )
    assert (
        bundle["artifacts"]["privacy_impact_assessment"]["schema_version"]
        == "max-privacy-impact-assessment/v1"
    )
    assert (
        bundle["artifacts"]["privacy_impact_assessment"]["kind"]
        == "max.spec.privacy_impact_assessment"
    )
    assert (
        bundle["artifacts"]["dependency_inventory"]["schema_version"]
        == "max-dependency-inventory/v1"
    )
    assert bundle["artifacts"]["risk_register"]["schema_version"] == "max-risk-register/v1"
    assert bundle["artifacts"]["threat_model"]["schema_version"] == "max-threat-model/v1"
    assert bundle["artifacts"]["slo_plan"]["schema_version"] == "max-slo-plan/v1"
    assert bundle["artifacts"]["review_gate"]["schema_version"] == "max-review-gate/v1"
    assert bundle["artifacts"]["evidence_density"]["signal_count"] == 1
    assert bundle["artifacts"]["evidence_chain_summary"]["signal_ids"] == ["sig-test001"]


def test_generate_spec_bundle_degrades_without_evaluation(
    store,
    sample_signal,
    sample_insight,
    sample_unit,
) -> None:
    store.insert_signal(sample_signal)
    store.insert_insight(sample_insight)
    store.insert_buildable_unit(sample_unit)

    bundle = generate_spec_bundle(sample_unit, None, store)

    assert any("Utility evaluation is missing" in warning for warning in bundle["warnings"])
    assert bundle["artifacts"]["spec_preview"]["evaluation"] is None
    assert bundle["artifacts"]["readiness"]["passed"] is False
    assert "evaluation_recommendation" in bundle["artifacts"]["readiness"]["failed_check_ids"]
    assert bundle["artifacts"]["experiment_card"]["source"]["evaluation_available"] is False
    assert bundle["artifacts"]["data_classification"]["summary"]["category_count"] >= 1
    assert bundle["artifacts"]["data_retention_schedule"]["source"]["evaluation_available"] is False
    assert "missing_evaluation" in {
        gap["category"] for gap in bundle["artifacts"]["data_retention_schedule"]["gaps"]
    }
    assert bundle["artifacts"]["privacy_impact_assessment"]["summary"]["privacy_gate"] in {
        "field_inventory_required",
        "owner_review_required",
        "privacy_review_required",
    }
    assert bundle["artifacts"]["dependency_inventory"]["source"]["evaluation_available"] is False
    assert bundle["artifacts"]["risk_register"]["source"]["evaluation_available"] is False
    assert bundle["artifacts"]["threat_model"]["scope"]["evaluation_available"] is False
    assert bundle["artifacts"]["slo_plan"]["source"]["evaluation_available"] is False
    assert "missing_evaluation" in {
        gap["category"] for gap in bundle["artifacts"]["slo_plan"]["gaps"]
    }
    assert bundle["artifacts"]["rollback_plan"]["source"]["evaluation_available"] is False
    assert "trigger_missing_evaluation" in {
        trigger["id"] for trigger in bundle["artifacts"]["rollback_plan"]["rollback_triggers"]
    }
    assert "utility evaluation is missing" in bundle["artifacts"]["review_gate"]["blocking_reasons"]


def test_render_spec_bundle_markdown_has_separated_sections(
    store,
    sample_signal,
    sample_insight,
    sample_unit,
    sample_evaluation,
) -> None:
    store.insert_signal(sample_signal)
    store.insert_insight(sample_insight)
    store.insert_buildable_unit(sample_unit)
    store.insert_evaluation(sample_evaluation)
    bundle = generate_spec_bundle(sample_unit, sample_evaluation, store)

    markdown = render_spec_bundle_markdown(bundle)

    assert markdown.startswith("# MCP Test Framework Implementation Packet")
    for heading in [
        "## Spec Preview",
        "## Readiness",
        "## Implementation Plan",
        "## Launch Checklist",
        "## Rollback Plan",
        "## MCP Test Framework Disaster Recovery Plan",
        "## Acceptance Criteria",
        "## Experiment Card",
        "## Data Classification",
        "## Privacy Impact Assessment",
        "## Data Retention Schedule",
        "## Dependency Inventory",
        "## Risk Register",
        "## Threat Model",
        "## SLO Plan",
        "## Review Gate",
        "## Evidence Density",
        "## Evidence Links",
        "## Evidence Chain Summary",
    ]:
        assert heading in markdown
    assert "bu-test001" in markdown
    assert "MCP server maintainer" in markdown
    assert "Sensitivity:" in markdown
    assert "Privacy gate:" in markdown
    assert "Retention gate:" in markdown
    assert "trigger_domain_risk_1" in markdown
    assert "Recovery tier: priority_restore" in markdown
    assert "Credential leakage enables service impersonation" in markdown
    assert "Schema version: max-slo-plan/v1" in markdown
    assert "Launch tier: production_candidate" in markdown
    assert "- bu-test001 -> ins-test001 (inspired_by; inspires)" in markdown
