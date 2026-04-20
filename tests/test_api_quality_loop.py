"""API tests for ideation quality-loop fields."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from max.server.app import create_app
from max.store.db import Store
from max.types.buildable_unit import BuildableUnit


@pytest.fixture
def quality_client(tmp_path):
    from max.server.dependencies import get_store

    db_path = str(tmp_path / "quality_api.db")
    store = Store(db_path=db_path, wal_mode=True)
    unit = BuildableUnit(
        id="bu-quality001",
        title="Quality Idea",
        one_liner="A quality-scored idea",
        category="workflow_automation",
        problem="Manual release validation is slow",
        solution="Automate release validation checks",
        value_proposition="Faster releases",
        specific_user="QA lead",
        buyer="VP engineering",
        workflow_context="release validation",
        current_workaround="manual checklist",
        why_now="more automated releases",
        validation_plan="test with two release teams",
        first_10_customers="internal platform teams",
        domain_risks=["low urgency"],
        evidence_rationale="Seeded insight supports testing pain.",
        novelty_score=6.0,
        usefulness_score=8.0,
        quality_score=7.0,
    )
    store.insert_buildable_unit(unit)
    store.close()

    app = create_app()

    def override_get_store():
        scoped = Store(db_path=db_path, wal_mode=True)
        try:
            yield scoped
        finally:
            scoped.close()

    app.dependency_overrides[get_store] = override_get_store
    return TestClient(app)


def test_idea_detail_includes_quality_fields(quality_client):
    resp = quality_client.get("/api/v1/ideas/bu-quality001")
    assert resp.status_code == 200
    data = resp.json()
    assert data["specific_user"] == "QA lead"
    assert data["buyer"] == "VP engineering"
    assert data["workflow_context"] == "release validation"
    assert data["validation_plan"] == "test with two release teams"
    assert data["novelty_score"] == 6.0
    assert data["usefulness_score"] == 8.0
    assert data["quality_score"] == 7.0


def test_idea_summary_includes_quality_fields(quality_client):
    resp = quality_client.get("/api/v1/ideas")
    assert resp.status_code == 200
    item = resp.json()["items"][0]
    assert item["specific_user"] == "QA lead"
    assert item["buyer"] == "VP engineering"
    assert item["workflow_context"] == "release validation"
    assert item["quality_score"] == 7.0


def test_pipeline_run_accepts_quality_loop_flags(quality_client):
    from max.pipeline.runner import PipelineResult

    mock_result = PipelineResult(
        signals_fetched=1,
        signals_new=1,
        insights_generated=1,
        ideas_generated=1,
        ideas_evaluated=1,
        draft_ideas_generated=4,
        ideas_revised=2,
        ideas_rejected_by_quality_gate=1,
        avg_novelty_score=7.0,
        avg_usefulness_score=8.0,
        avg_insight_confidence=0.8,
        avg_idea_score=75.0,
        token_usage={},
        top_ideas=[],
    )

    with patch("max.pipeline.runner.run_pipeline", return_value=mock_result) as mock_run:
        resp = quality_client.post(
            "/api/v1/pipeline/run",
            json={
                "signal_limit": 10,
                "quality_loop_enabled": True,
                "draft_count": 4,
            },
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["draft_ideas_generated"] == 4
    assert data["ideas_revised"] == 2
    assert data["ideas_rejected_by_quality_gate"] == 1
    assert data["avg_novelty_score"] == 7.0
    assert data["avg_usefulness_score"] == 8.0
    assert mock_run.call_args.kwargs["quality_loop_enabled"] is True
    assert mock_run.call_args.kwargs["draft_count"] == 4
