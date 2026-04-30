"""CLI tests for persisted idea spec bundle export."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from max.cli import main
from max.store.db import Store
from max.types.buildable_unit import BuildableCategory, BuildableUnit, IdeationMode
from max.types.evaluation import DimensionScore, UtilityEvaluation
from max.types.insight import Insight, InsightCategory
from max.types.signal import Signal, SignalSourceType


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


@pytest.fixture
def spec_bundle_db(tmp_path) -> str:
    db_path = str(tmp_path / "cli_spec_bundle.db")
    with Store(db_path=db_path, wal_mode=True) as store:
        store.insert_signal(
            Signal(
                id="sig-cli-bundle001",
                source_type=SignalSourceType.FORUM,
                source_adapter="test",
                title="CLI bundle signal",
                content="Evidence that local agents need a single implementation packet.",
                url="https://example.com/cli-bundle",
                credibility=0.8,
            )
        )
        store.insert_insight(
            Insight(
                id="ins-cli-bundle001",
                category=InsightCategory.GAP,
                title="CLI bundle insight",
                summary="Local workflows need the same spec bundle the API returns.",
                evidence=["sig-cli-bundle001"],
                confidence=0.8,
                domains=["developer-tools"],
            )
        )
        store.insert_buildable_unit(_bundle_unit("bu-cli-bundle001"))
        store.insert_evaluation(_bundle_evaluation("bu-cli-bundle001"))
    return db_path


@pytest.fixture
def persisted_store(monkeypatch: pytest.MonkeyPatch, spec_bundle_db: str) -> str:
    monkeypatch.setattr("max.store.db.Store", lambda: Store(db_path=spec_bundle_db, wal_mode=True))
    return spec_bundle_db


def test_spec_bundle_prints_markdown_by_default(
    runner: CliRunner,
    persisted_store: str,
) -> None:
    result = runner.invoke(main, ["spec-bundle", "bu-cli-bundle001"])

    assert result.exit_code == 0, result.output
    assert result.output.startswith("# CLI Bundle Idea Implementation Packet")
    assert "## Spec Preview" in result.output
    assert "## Review Gate" in result.output


def test_spec_bundle_prints_json(
    runner: CliRunner,
    persisted_store: str,
) -> None:
    result = runner.invoke(main, ["spec-bundle", "bu-cli-bundle001", "--format", "json"])

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["schema_version"] == "max-spec-bundle/v1"
    assert payload["kind"] == "max.spec_bundle"
    assert payload["idea_id"] == "bu-cli-bundle001"
    assert payload["artifacts"]["spec_preview"]["project"]["title"] == "CLI Bundle Idea"
    assert payload["artifacts"]["evidence_density"]["signal_count"] == 1


def test_spec_bundle_output_writes_selected_representation(
    runner: CliRunner,
    persisted_store: str,
    tmp_path: Path,
) -> None:
    output_path = tmp_path / "out" / "bundle.json"

    result = runner.invoke(
        main,
        [
            "spec-bundle",
            "bu-cli-bundle001",
            "--format",
            "json",
            "--output",
            str(output_path),
        ],
    )

    assert result.exit_code == 0, result.output
    assert result.output == ""
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["idea_id"] == "bu-cli-bundle001"


def test_spec_bundle_missing_idea_exits_nonzero(
    runner: CliRunner,
    persisted_store: str,
) -> None:
    result = runner.invoke(main, ["spec-bundle", "bu-missing"])

    assert result.exit_code != 0
    assert "Idea not found: bu-missing" in result.output


def _bundle_unit(unit_id: str) -> BuildableUnit:
    return BuildableUnit(
        id=unit_id,
        title="CLI Bundle Idea",
        one_liner="One packet for local implementation handoff",
        category=BuildableCategory.APPLICATION,
        ideation_mode=IdeationMode.DIRECT,
        problem="Local autonomous workflows cannot easily fetch a complete idea handoff.",
        solution="Expose the API spec bundle generation path through the CLI.",
        target_users="agents",
        value_proposition="Faster and more stable local implementation handoff.",
        specific_user="implementation agent operator",
        buyer="platform lead",
        workflow_context="pre-build handoff preparation",
        current_workaround="manual endpoint stitching",
        why_now="more ideas are handed to autonomous agents",
        validation_plan="run the CLI and verify downstream packet consumption",
        first_10_customers="internal implementation agents",
        domain_risks=["packet can become too large"],
        evidence_rationale="Evidence shows local consumers need a stable handoff artifact.",
        inspiring_insights=["ins-cli-bundle001"],
        evidence_signals=["sig-cli-bundle001"],
        tech_approach="Click command that composes existing deterministic artifacts",
        suggested_stack={"language": "python", "framework": "click"},
        composability_notes="No new persistence; bundle is generated on request.",
    )


def _bundle_evaluation(unit_id: str) -> UtilityEvaluation:
    score = DimensionScore(value=8.0, confidence=0.75, reasoning="seeded")
    return UtilityEvaluation(
        buildable_unit_id=unit_id,
        pain_severity=score,
        addressable_scale=score,
        build_effort=score,
        composability=score,
        competitive_density=score,
        timing_fit=score,
        compounding_value=score,
        overall_score=82.0,
        strengths=["Stable handoff"],
        weaknesses=["Bundle size needs monitoring"],
        recommendation="yes",
        weights_used={"pain_severity": 0.2},
    )
