"""Tests for disaster recovery plan inclusion in spec bundles."""

from __future__ import annotations

from max.spec.bundle import generate_spec_bundle, render_spec_bundle_markdown


def test_spec_bundle_includes_disaster_recovery_plan_when_all_artifacts_requested(
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

    bundle = generate_spec_bundle(sample_unit, sample_evaluation, store, artifacts=["all"])

    assert "disaster_recovery_plan" in bundle["artifacts"]
    plan = bundle["artifacts"]["disaster_recovery_plan"]
    assert plan["schema_version"] == "max-disaster-recovery-plan/v1"
    assert plan["kind"] == "max.disaster_recovery_plan"
    assert plan["source"]["idea_id"] == "bu-test001"
    assert plan["summary"]["recovery_tier"] == "priority_restore"
    assert plan["critical_capabilities"]
    assert plan["restore_sequence"]


def test_spec_bundle_explicit_disaster_recovery_selection_returns_only_requested_artifact(
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

    bundle = generate_spec_bundle(
        sample_unit,
        sample_evaluation,
        store,
        artifacts=["disaster_recovery_plan"],
    )

    assert bundle["schema_version"] == "max-spec-bundle/v1"
    assert bundle["kind"] == "max.spec_bundle"
    assert bundle["idea_id"] == "bu-test001"
    assert bundle["generated_at"]
    assert set(bundle["artifacts"]) == {"disaster_recovery_plan"}
    assert bundle["artifacts"]["disaster_recovery_plan"]["summary"]["title"] == "MCP Test Framework"


def test_spec_bundle_markdown_renders_disaster_recovery_section(
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

    assert "## MCP Test Framework Disaster Recovery Plan" in markdown
    assert "## Critical Capabilities" in markdown
    assert "- Recovery tier: priority_restore" in markdown
    assert "RST3: Restore application" in markdown


def test_spec_bundle_existing_artifact_keys_are_preserved_with_disaster_recovery(
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

    expected_existing_keys = {
        "spec_preview",
        "readiness",
        "implementation_plan",
        "launch_checklist",
        "rollback_plan",
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
    assert expected_existing_keys < set(bundle["artifacts"])
    assert "disaster_recovery_plan" in bundle["artifacts"]
