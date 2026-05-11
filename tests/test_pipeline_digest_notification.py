"""Tests for pipeline digest notification rendering."""

from __future__ import annotations

import json

from max.notifications.pipeline_digest import (
    PipelineDigest,
    build_pipeline_digest,
    render_digest_html,
    render_digest_json,
    render_digest_text,
)


def _summary() -> dict:
    return {
        "run_id": "run-123",
        "timestamp": "2026-05-12T09:00:00+09:00",
        "stats": {
            "signals_fetched": 42,
            "insights_generated": 7,
            "ideas_scored": 3,
            "duration_seconds": 18.5,
        },
        "top_ideas": [
            {"title": "Customer Data Classifier", "score": 91.2, "recommendation": "build"},
            {"title": "Support Routing", "score": 77.0, "recommendation": "trial"},
        ],
        "errors": [],
    }


def test_build_pipeline_digest_extracts_run_stats() -> None:
    digest = build_pipeline_digest(_summary())

    assert isinstance(digest, PipelineDigest)
    assert digest.run_id == "run-123"
    assert digest.signals_fetched == 42
    assert digest.insights_generated == 7
    assert digest.ideas_scored == 3
    assert digest.duration_seconds == 18.5
    assert digest.top_ideas[0]["title"] == "Customer Data Classifier"


def test_text_rendering_includes_key_stats() -> None:
    text = render_digest_text(build_pipeline_digest(_summary()))

    assert "Max Pipeline Digest" in text
    assert "Run ID: run-123" in text
    assert "Signals fetched: 42" in text
    assert "Customer Data Classifier" in text
    assert "Errors:\n- None" in text


def test_html_rendering_produces_email_structure() -> None:
    html = render_digest_html(build_pipeline_digest(_summary()))

    assert html.startswith("<!doctype html>")
    assert "<h1>Max Pipeline Digest</h1>" in html
    assert "<table>" in html
    assert "<th>Recommendation</th>" in html
    assert "<td>Customer Data Classifier</td>" in html


def test_json_rendering_is_parseable() -> None:
    payload = json.loads(render_digest_json(build_pipeline_digest(_summary())))

    assert payload["run_id"] == "run-123"
    assert payload["top_ideas"][0]["score"] == 91.2


def test_empty_and_error_summaries_are_handled_gracefully() -> None:
    digest = build_pipeline_digest({"id": "failed-run", "errors": ["source timeout"]})

    assert digest.run_id == "failed-run"
    assert digest.signals_fetched == 0
    assert digest.top_ideas == []
    assert digest.errors == ["source timeout"]
    assert "No top ideas identified" in render_digest_text(digest)
    assert "<li>source timeout</li>" in render_digest_html(digest)
