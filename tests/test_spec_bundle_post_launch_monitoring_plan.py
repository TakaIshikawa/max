"""Tests for post-launch monitoring plan inclusion in spec bundles."""

from __future__ import annotations

from max.spec.bundle import generate_spec_bundle, render_spec_bundle_markdown


def test_spec_bundle_includes_post_launch_monitoring_plan(
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

    plan = bundle["artifacts"]["post_launch_monitoring_plan"]
    assert plan["schema_version"] == "max-post-launch-monitoring-plan/v1"
    assert plan["kind"] == "max.post_launch_monitoring_plan"
    assert plan["idea_id"] == "bu-test001"
    assert plan["source"]["evaluation_available"] is True
    assert plan["source"]["tact_spec_schema_version"] == "tact-spec-preview/v1"
    assert plan["summary"]["launch_posture"] == "production_candidate"
    assert plan["health_metrics"]
    assert plan["alert_thresholds"]


def test_spec_bundle_explicit_post_launch_monitoring_selection_returns_only_requested_artifact(
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
        artifacts=["post_launch_monitoring_plan"],
    )

    assert set(bundle["artifacts"]) == {"post_launch_monitoring_plan"}
    assert bundle["artifacts"]["post_launch_monitoring_plan"]["summary"]["title"] == (
        "MCP Test Framework"
    )


def test_spec_bundle_markdown_renders_post_launch_monitoring_section(
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

    assert "## MCP Test Framework Post-Launch Monitoring Plan" in markdown
    assert "## Health Metrics" in markdown
    assert "### HM1: workflow_success_rate" in markdown
    assert "### AT1: success_rate_drop (critical)" in markdown


def test_spec_bundle_post_launch_monitoring_degrades_without_evaluation(
    store,
    sample_signal,
    sample_insight,
    sample_unit,
) -> None:
    store.insert_signal(sample_signal)
    store.insert_insight(sample_insight)
    store.insert_buildable_unit(sample_unit)

    bundle = generate_spec_bundle(sample_unit, None, store)

    plan = bundle["artifacts"]["post_launch_monitoring_plan"]
    assert plan["source"]["evaluation_available"] is False
    assert plan["summary"]["launch_posture"] == "limited_pilot"
