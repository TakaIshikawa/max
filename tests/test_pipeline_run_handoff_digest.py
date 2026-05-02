"""Tests for pipeline run handoff digest generation."""

from __future__ import annotations

import csv
import json
from io import StringIO

import pytest

from max.analysis.pipeline_run_handoff_digest import (
    SCHEMA_VERSION,
    PipelineRunHandoffDigestNotFound,
    build_pipeline_run_handoff_digest,
    pipeline_run_handoff_digest_filename,
    render_pipeline_run_handoff_digest,
    write_pipeline_run_handoff_digest,
)
from max.store.db import Store
from max.types.buildable_unit import BuildableCategory, BuildableUnit, IdeationMode
from max.types.evaluation import DimensionScore, UtilityEvaluation
from max.types.signal import Signal, SignalSourceType


def _make_signal(signal_id: str, adapter: str) -> Signal:
    return Signal(
        id=signal_id,
        source_type=SignalSourceType.FORUM,
        source_adapter=adapter,
        title=f"Signal {signal_id}",
        content="Evidence about an unmet workflow need.",
        url=f"https://example.com/{signal_id}",
        credibility=0.8,
    )


def _make_unit(
    unit_id: str,
    title: str,
    *,
    status: str = "evaluated",
    evidence_signals: list[str] | None = None,
) -> BuildableUnit:
    return BuildableUnit(
        id=unit_id,
        title=title,
        one_liner=f"{title} one-liner",
        category=BuildableCategory.CLI_TOOL,
        ideation_mode=IdeationMode.DIRECT,
        problem="Developers lose time triaging tool failures.",
        solution="Create a focused automation for handoff and triage.",
        target_users="humans",
        value_proposition="Shortens the review loop.",
        evidence_signals=evidence_signals or [],
        domain="developer tools",
        status=status,
    )


def _score(value: float = 8.0) -> DimensionScore:
    return DimensionScore(value=value, confidence=0.8, reasoning="seeded")


def _make_evaluation(
    unit_id: str,
    *,
    overall_score: float,
    recommendation: str,
) -> UtilityEvaluation:
    return UtilityEvaluation(
        buildable_unit_id=unit_id,
        pain_severity=_score(8.0),
        addressable_scale=_score(7.0),
        build_effort=_score(6.0),
        composability=_score(8.0),
        competitive_density=_score(7.0),
        timing_fit=_score(8.0),
        compounding_value=_score(7.0),
        overall_score=overall_score,
        strengths=["clear workflow"],
        weaknesses=["needs buyer proof"],
        recommendation=recommendation,
        weights_used={"pain_severity": 0.2},
    )


def _seed_handoff_run(store: Store, run_id: str = "run-handoff-001") -> None:
    store.insert_pipeline_run(
        run_id,
        {"profile": "devtools", "domain": "developer tools", "model": "gpt-4o-mini"},
    )
    store.insert_signal(_make_signal("sig-hn", "hackernews"))
    store.insert_signal(_make_signal("sig-gh", "github_issues"))
    store.insert_signal(_make_signal("sig-reddit", "reddit"))

    store.insert_buildable_unit(
        _make_unit("bu-handoff-top", "Agent Run Handoff", evidence_signals=["sig-hn", "sig-gh"])
    )
    store.insert_buildable_unit(
        _make_unit("bu-handoff-second", "Source Coverage Watch", evidence_signals=["sig-reddit"])
    )
    store.insert_buildable_unit(
        _make_unit("bu-handoff-low", "Rejected Noise Filter", evidence_signals=["sig-gh"])
    )

    store.insert_evaluation(
        _make_evaluation("bu-handoff-top", overall_score=91.0, recommendation="strong_yes")
    )
    store.insert_evaluation(
        _make_evaluation("bu-handoff-second", overall_score=76.0, recommendation="yes")
    )
    store.insert_evaluation(
        _make_evaluation("bu-handoff-low", overall_score=42.0, recommendation="no")
    )

    store.insert_feedback(
        "bu-handoff-top",
        "approved",
        reason="best handoff fit",
        approval_score=9,
        pipeline_run_id=run_id,
    )
    store.insert_feedback(
        "bu-handoff-low",
        "rejected",
        reason="too narrow",
        pipeline_run_id=run_id,
    )
    store.insert_publication_attempt(
        idea_id="bu-handoff-top",
        target_type="linear",
        target_url="https://linear.example/issue/MAX-1",
        status="published",
        response_status=201,
    )

    store.update_pipeline_run(
        run_id,
        signals_fetched=16,
        signals_new=12,
        insights_generated=5,
        ideas_generated=3,
        ideas_evaluated=3,
        clusters_found=2,
        gaps_detected=1,
        avg_idea_score=69.7,
        token_usage={
            "input": 1400,
            "output": 350,
            "estimated_cost_usd": 0.0175,
            "by_stage": {"ideation": {"input": 900, "output": 260}},
        },
        adapter_metrics={"github_issues": {"status": "ok", "signal_count": 8}},
        status="completed",
    )
    store.insert_pipeline_run_domain(
        run_id,
        "developer tools",
        {
            "signals_fetched": 16,
            "insights_generated": 5,
            "ideas_generated": 3,
            "ideas_evaluated": 3,
            "avg_score": 69.7,
        },
    )


def test_seeded_run_returns_action_oriented_digest(store: Store) -> None:
    _seed_handoff_run(store)

    digest = build_pipeline_run_handoff_digest(store, run_id="run-handoff-001")

    assert digest["schema_version"] == SCHEMA_VERSION
    assert digest["kind"] == "max.pipeline_run_handoff_digest"
    assert digest["run"]["id"] == "run-handoff-001"
    assert digest["run"]["profile"] == "devtools"
    assert digest["summary"]["idea_count"] == 3
    assert digest["summary"]["evaluated_count"] == 3
    assert digest["summary"]["approved_count"] == 1
    assert digest["summary"]["rejected_count"] == 1
    assert digest["summary"]["publication_attempt_count"] == 1
    assert digest["budget"]["total_tokens"] == 1750
    assert digest["budget"]["estimated_cost_usd"] == 0.0175

    assert digest["top_recommended_ideas"][0]["id"] == "bu-handoff-top"
    assert digest["top_recommended_ideas"][0]["feedback_outcome"] == "approved"
    assert digest["top_recommended_ideas"][0]["publication_attempt_count"] == 1

    sources = {row["source_adapter"]: row for row in digest["source_mix"]}
    assert sources["github_issues"]["idea_count"] == 2
    assert sources["hackernews"]["evidence_signal_count"] == 1
    assert digest["next_actions"]


def test_missing_optional_budget_and_publication_data_does_not_fail(store: Store) -> None:
    run_id = "run-handoff-sparse"
    store.insert_pipeline_run(run_id, {"profile": "devtools", "domain": "developer tools"})
    store.insert_buildable_unit(_make_unit("bu-sparse", "Sparse Idea"))
    store.update_pipeline_run(
        run_id,
        signals_fetched=1,
        ideas_generated=1,
        ideas_evaluated=0,
        token_usage={},
        status="completed",
    )

    digest = build_pipeline_run_handoff_digest(store, run_id=run_id)

    assert digest["summary"]["idea_count"] == 1
    assert digest["summary"]["publication_attempt_count"] == 0
    assert digest["budget"]["total_tokens"] == 0
    assert "No token usage was recorded for this run." in digest["warnings"]
    assert digest["top_recommended_ideas"][0]["recommendation"] == "unevaluated"


def test_digest_can_render_markdown_and_json(store: Store, tmp_path) -> None:
    _seed_handoff_run(store)
    digest = build_pipeline_run_handoff_digest(store, run_id="run-handoff-001")

    markdown = render_pipeline_run_handoff_digest(digest, fmt="markdown")

    assert markdown.startswith("# Pipeline Run Handoff Digest: run-handoff-001")
    assert f"Schema: `{SCHEMA_VERSION}`" in markdown
    assert "## Top Recommended Ideas" in markdown
    assert "Agent Run Handoff" in markdown
    assert "| `github_issues` | 2 | 2 |" in markdown
    assert "## Next Actions" in markdown

    parsed = json.loads(render_pipeline_run_handoff_digest(digest, fmt="json"))
    assert parsed["schema_version"] == SCHEMA_VERSION
    assert parsed["summary"]["approved_count"] == 1

    with pytest.raises(ValueError, match="Unsupported pipeline run handoff digest format: yaml"):
        render_pipeline_run_handoff_digest(digest, fmt="yaml")

    path = tmp_path / pipeline_run_handoff_digest_filename("run-handoff-001")
    write_pipeline_run_handoff_digest(path, digest)
    assert path.name == "run-handoff-001-handoff-digest.md"
    assert pipeline_run_handoff_digest_filename("run-handoff-001", fmt="csv").endswith(".csv")
    assert path.read_text(encoding="utf-8").startswith(
        "# Pipeline Run Handoff Digest: run-handoff-001"
    )


def test_digest_can_render_csv_with_stable_sections_and_quoting(store: Store) -> None:
    _seed_handoff_run(store)
    digest = build_pipeline_run_handoff_digest(store, run_id="run-handoff-001")
    digest["source_mix"][0]["source_adapter"] = 'github, "issues"'
    digest["top_recommended_ideas"][0]["title"] = 'Agent, "Run"\nHandoff'

    csv_text = render_pipeline_run_handoff_digest(digest, fmt="csv")
    rows = list(csv.DictReader(StringIO(csv_text)))

    assert csv_text.endswith("\n")
    assert list(rows[0].keys()) == [
        "section",
        "ordinal",
        "key",
        "value",
        "run_id",
        "status",
        "profile",
        "domain",
        "started_at",
        "completed_at",
        "source_adapter",
        "idea_id",
        "title",
        "category",
        "score",
        "recommendation",
        "feedback_outcome",
        "approval_score",
        "publication_attempt_count",
        "latest_publication_status",
        "evidence_signal_count",
        "message",
    ]
    assert [row["section"] for row in rows[:8]] == ["metadata"] * 8
    assert rows[0]["key"] == "schema_version"
    assert rows[0]["value"] == SCHEMA_VERSION
    assert rows[2]["key"] == "run_id"
    assert rows[2]["value"] == "run-handoff-001"

    sections = [row["section"] for row in rows]
    assert sections.index("summary") < sections.index("stage_counts")
    assert sections.index("stage_counts") < sections.index("budget")
    assert sections.index("budget") < sections.index("budget_stage")
    assert sections.index("budget_stage") < sections.index("source_mix")
    assert sections.index("source_mix") < sections.index("top_recommended_ideas")
    assert sections.index("top_recommended_ideas") < sections.index("warnings")
    assert sections.index("warnings") < sections.index("next_actions")

    assert any(
        row["section"] == "summary"
        and row["key"] == "approved_or_published_count"
        and row["value"] == "1"
        for row in rows
    )
    assert any(
        row["section"] == "stage_counts"
        and row["key"] == "signals_fetched"
        and row["value"] == "16"
        for row in rows
    )
    assert any(
        row["section"] == "budget" and row["key"] == "total_tokens" and row["value"] == "1750"
        for row in rows
    )
    assert any(
        row["section"] == "source_mix"
        and row["source_adapter"] == 'github, "issues"'
        and row["value"] == "2"
        and row["evidence_signal_count"] == "2"
        for row in rows
    )
    assert any(
        row["section"] == "top_recommended_ideas"
        and row["idea_id"] == "bu-handoff-top"
        and row["title"] == 'Agent, "Run"\nHandoff'
        and row["feedback_outcome"] == "approved"
        and row["publication_attempt_count"] == "1"
        for row in rows
    )
    assert '"github, ""issues"""' in csv_text
    assert '"Agent, ""Run""\nHandoff"' in csv_text


def test_digest_csv_empty_source_mix_and_top_ideas_use_placeholders() -> None:
    digest = {
        "schema_version": SCHEMA_VERSION,
        "kind": "max.pipeline_run_handoff_digest",
        "run": {"id": "run-empty", "status": "completed"},
        "summary": {"idea_count": 0},
        "stage_counts": {},
        "budget": {},
        "source_mix": [],
        "top_recommended_ideas": [],
        "warnings": [],
        "next_actions": [],
    }

    rows = list(csv.DictReader(StringIO(render_pipeline_run_handoff_digest(digest, fmt="csv"))))

    source_row = next(row for row in rows if row["section"] == "source_mix")
    assert source_row["key"] == "none"
    assert source_row["source_adapter"] == "none"
    assert source_row["value"] == "0"
    assert source_row["message"] == "No source mix is available."

    idea_row = next(row for row in rows if row["section"] == "top_recommended_ideas")
    assert idea_row["key"] == "none"
    assert idea_row["score"] == "0.0"
    assert idea_row["recommendation"] == "none"
    assert idea_row["message"] == "No top recommended ideas are available."

    warning_row = next(row for row in rows if row["section"] == "warnings")
    action_row = next(row for row in rows if row["section"] == "next_actions")
    assert warning_row["key"] == "none"
    assert action_row["key"] == "none"


def test_digest_builder_is_read_only(store: Store) -> None:
    _seed_handoff_run(store)
    unit_ids = ["bu-handoff-top", "bu-handoff-second", "bu-handoff-low"]
    before = {
        "run": store.get_pipeline_run("run-handoff-001"),
        "ideas": {
            unit_id: store.get_buildable_unit(unit_id).model_dump(mode="json")
            for unit_id in unit_ids
        },
        "evaluations": {
            unit_id: store.get_evaluation(unit_id).model_dump(mode="json")
            for unit_id in unit_ids
        },
        "feedback": {
            unit_id: store.get_latest_feedback(unit_id)
            for unit_id in ["bu-handoff-top", "bu-handoff-low"]
        },
        "publications": store.list_publication_attempts("bu-handoff-top"),
    }

    build_pipeline_run_handoff_digest(store, run_id="run-handoff-001")

    after = {
        "run": store.get_pipeline_run("run-handoff-001"),
        "ideas": {
            unit_id: store.get_buildable_unit(unit_id).model_dump(mode="json")
            for unit_id in unit_ids
        },
        "evaluations": {
            unit_id: store.get_evaluation(unit_id).model_dump(mode="json")
            for unit_id in unit_ids
        },
        "feedback": {
            unit_id: store.get_latest_feedback(unit_id)
            for unit_id in ["bu-handoff-top", "bu-handoff-low"]
        },
        "publications": store.list_publication_attempts("bu-handoff-top"),
    }
    assert after == before


def test_unknown_run_raises(store: Store) -> None:
    with pytest.raises(PipelineRunHandoffDigestNotFound) as exc:
        build_pipeline_run_handoff_digest(store, run_id="run-missing")

    assert exc.value.run_id == "run-missing"
