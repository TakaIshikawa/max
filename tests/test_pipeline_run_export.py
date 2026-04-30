from __future__ import annotations

import csv
from io import StringIO

import pytest

from max.analysis.pipeline_run_export import (
    PipelineRunExportNotFound,
    export_pipeline_run,
    export_recent_pipeline_runs,
    render_pipeline_runs_csv,
    render_pipeline_runs_markdown,
)
from max.store.db import Store


def _seed_run(store: Store, run_id: str = "run-export-001") -> None:
    store.insert_pipeline_run(
        run_id,
        {"profile": "devtools", "domain": "developer tools", "model": "gpt-4o-mini"},
    )
    store.update_pipeline_run(
        run_id,
        signals_fetched=12,
        signals_new=8,
        insights_generated=3,
        ideas_generated=2,
        ideas_evaluated=2,
        clusters_found=1,
        gaps_detected=1,
        avg_idea_score=78.5,
        token_usage={
            "input": 1000,
            "output": 250,
            "estimated_cost_usd": 0.0123,
            "by_stage": {"ideation": {"input": 700, "output": 200}},
        },
        adapter_metrics={
            "github": {
                "status": "ok",
                "signal_count": 9,
                "duration_ms": 110,
                "error_message": None,
            },
            "hackernews": {
                "status": "error",
                "signal_count": 0,
                "duration_ms": 45,
                "error_message": "rate limited",
            },
        },
        status="completed",
    )
    store.insert_pipeline_run_domain(
        run_id,
        "developer tools",
        {
            "signals_fetched": 12,
            "insights_generated": 3,
            "ideas_generated": 2,
            "ideas_evaluated": 2,
            "avg_score": 78.5,
        },
    )
    store.insert_feedback("bu-export-001", "approved", pipeline_run_id=run_id)


def test_export_pipeline_run_json_record(store: Store) -> None:
    _seed_run(store)

    record = export_pipeline_run(store, run_id="run-export-001")

    assert record["id"] == "run-export-001"
    assert record["profile"] == "devtools"
    assert record["domain"] == "developer tools"
    assert record["stage_counts"]["signals_fetched"] == 12
    assert record["stage_counts"]["approved"] == 1
    assert record["budget"]["total_tokens"] == 1250
    assert record["budget"]["estimated_cost_usd"] == 0.0123
    assert record["adapter_stats"][1]["adapter"] == "hackernews"
    assert record["errors"]["adapters"][0]["error_message"] == "rate limited"
    assert record["follow_up_recommendations"]


def test_export_recent_pipeline_runs_json(store: Store) -> None:
    _seed_run(store, "run-export-001")
    _seed_run(store, "run-export-002")

    export = export_recent_pipeline_runs(store, limit=1)

    assert export["limit"] == 1
    assert export["run_count"] == 1
    assert len(export["runs"]) == 1


def test_render_pipeline_runs_markdown_includes_review_context(store: Store) -> None:
    _seed_run(store)
    record = export_pipeline_run(store, run_id="run-export-001")

    markdown = render_pipeline_runs_markdown([record], title="Pipeline Run Export")

    assert "# Pipeline Run Export" in markdown
    assert "## Run run-export-001" in markdown
    assert "### Stage Counts" in markdown
    assert "| signals_fetched | 12 |" in markdown
    assert "### Adapter Stats" in markdown
    assert "rate limited" in markdown
    assert "### Budget" in markdown
    assert "Total tokens: 1250" in markdown
    assert "### Follow-up Recommendations" in markdown


def test_render_pipeline_runs_csv_includes_review_columns(store: Store) -> None:
    _seed_run(store)
    record = export_pipeline_run(store, run_id="run-export-001")

    csv_body = render_pipeline_runs_csv([record])

    rows = list(csv.DictReader(StringIO(csv_body)))
    assert len(rows) == 1
    row = rows[0]
    assert row["id"] == "run-export-001"
    assert row["status"] == "completed"
    assert row["profile"] == "devtools"
    assert row["domain"] == "developer tools"
    assert row["signals_fetched"] == "12"
    assert row["approved"] == "1"
    assert row["total_tokens"] == "1250"
    assert row["estimated_cost_usd"] == "0.0123"
    assert row["adapter_count"] == "2"
    assert row["adapter_error_count"] == "1"
    assert row["follow_up_recommendation_count"] == "1"


def test_export_pipeline_run_unknown_id_raises(store: Store) -> None:
    with pytest.raises(PipelineRunExportNotFound) as exc:
        export_pipeline_run(store, run_id="run-missing")

    assert exc.value.run_id == "run-missing"
