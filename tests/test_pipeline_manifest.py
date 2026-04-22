from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

from max.pipeline.manifest import MANIFEST_SCHEMA_VERSION, build_run_manifest, write_run_manifest
from max.pipeline.runner import PipelineResult, run_pipeline

from tests.test_runner import _PatchCtx, _R, _make_signal


def test_build_run_manifest_includes_automation_fields() -> None:
    result = PipelineResult(
        run_id="run-test",
        profile_name="devtools",
        status="completed",
        signals_fetched=3,
        insights_generated=2,
        ideas_generated=1,
        ideas_evaluated=1,
        source_counts={"github": 2, "hackernews": 1},
        generated_idea_ids=["bu-1"],
        evaluation_recommendations=[
            {"idea_id": "bu-1", "recommendation": "yes", "score": 82.0}
        ],
        token_usage={"total_input": 100, "total_output": 50},
        estimated_cost_usd=0.0123,
        publication_outputs=[],
    )

    manifest = build_run_manifest(
        result,
        started_at="2026-04-22T00:00:00+00:00",
        completed_at="2026-04-22T00:00:05+00:00",
        inputs={"profile_name": "devtools", "signal_limit": 10},
    )

    assert manifest["schema_version"] == MANIFEST_SCHEMA_VERSION
    assert manifest["profile_name"] == "devtools"
    assert manifest["duration_seconds"] == 5.0
    assert manifest["source_counts"] == {"github": 2, "hackernews": 1}
    assert manifest["counts"]["insights_generated"] == 2
    assert manifest["generated_idea_ids"] == ["bu-1"]
    assert manifest["evaluation_recommendations"][0]["recommendation"] == "yes"
    assert manifest["budget"]["token_usage"]["total_input"] == 100
    assert manifest["publication_outputs"] == []


def test_write_run_manifest_uses_directory_default_filename(tmp_path: Path) -> None:
    output = write_run_manifest(tmp_path / "manifests", {"run_id": "run-test"})

    assert output == tmp_path / "manifests" / "run-manifest.json"
    assert json.loads(output.read_text(encoding="utf-8")) == {"run_id": "run-test"}


def test_run_pipeline_writes_manifest_when_requested(tmp_path: Path) -> None:
    token_tracker = MagicMock()
    token_tracker.reset = MagicMock()
    token_tracker.summary = MagicMock(return_value={"total_input": 10, "total_output": 5})
    token_tracker.estimated_cost_usd = MagicMock(return_value=0.001)
    token_tracker.cost_by_stage = MagicMock(return_value={"evaluate": 0.001})
    signals = [_make_signal("s1", adapter="hackernews")]

    overrides = {
        f"{_R}.token_tracker": token_tracker,
        f"{_R}._fetch_all_signals": MagicMock(
            return_value=(signals, {"hackernews": 1}, {"hackernews": {"signal_count": 1}})
        ),
    }

    manifest_path = tmp_path / "run.json"
    with _PatchCtx(overrides):
        result = run_pipeline(
            signal_limit=1,
            stages=["fetch"],
            manifest_path=manifest_path,
        )

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["run_id"] == result.run_id
    assert manifest["source_counts"] == {"hackernews": 1}
    assert manifest["counts"]["signals_fetched"] == 1
    assert manifest["budget"]["estimated_cost_usd"] == 0.001
