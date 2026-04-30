"""API tests for validation experiment follow-up recommendations."""

from __future__ import annotations

import json

from fastapi.testclient import TestClient

from max.server.app import create_app
from max.store.db import Store
from max.types.buildable_unit import BuildableCategory, BuildableUnit, IdeationMode


def _unit(unit_id: str = "bu-api-followups") -> BuildableUnit:
    return BuildableUnit(
        id=unit_id,
        title="API Validation Followups Idea",
        one_liner="Expose validation next steps",
        category=BuildableCategory.APPLICATION,
        ideation_mode=IdeationMode.DIRECT,
        problem="Validation results are not actionable",
        solution="Expose ranked follow-up actions",
        value_proposition="Operators can act on validation outcomes",
    )


def _client(db_path: str) -> TestClient:
    from max.server.dependencies import get_store

    app = create_app()

    def override_get_store():
        store = Store(db_path=db_path, wal_mode=True)
        try:
            yield store
        finally:
            store.close()

    app.dependency_overrides[get_store] = override_get_store
    return TestClient(app)


def test_validation_followups_api_returns_404_for_missing_idea(tmp_path) -> None:
    client = _client(str(tmp_path / "api.db"))

    response = client.get("/api/v1/ideas/missing/validation-followups")

    assert response.status_code == 404
    assert response.json() == {"detail": "Idea not found: missing"}


def test_validation_followups_api_returns_deterministic_json_for_existing_idea(tmp_path) -> None:
    db_path = str(tmp_path / "api.db")
    with Store(db_path=db_path, wal_mode=True) as store:
        store.insert_buildable_unit(_unit())
        store.create_validation_experiment(
            "bu-api-followups",
            hypothesis="Teams will share reports",
            method="prototype",
            success_metric="6 report shares",
            status="completed",
            completed_at="2026-04-20T00:00:00+00:00",
            result_summary=json.dumps({"outcome": "validated"}),
            evidence_urls=["https://example.com/a", "https://example.com/b"],
            confidence_delta=0.4,
        )
        store.create_validation_experiment(
            "bu-api-followups",
            hypothesis="Buyers accept setup fees",
            method="pricing interview",
            success_metric="3 approvals",
            status="completed",
            completed_at="2026-04-21T00:00:00+00:00",
            result_summary="Buyers rejected setup fees",
            evidence_urls=["https://example.com/c"],
            confidence_delta=-0.1,
        )

    client = _client(db_path)

    first = client.get("/api/v1/ideas/bu-api-followups/validation-followups")
    second = client.get("/api/v1/ideas/bu-api-followups/validation-followups")

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json() == second.json()
    payload = first.json()
    assert payload["idea_id"] == "bu-api-followups"
    assert payload["total_count"] == 2
    assert payload["latest_experiment"]["confidence_delta"] == -0.1
    assert payload["status_counts"] == [{"key": "completed", "count": 2}]
    assert payload["evidence_url_count"] == 3
    assert payload["confidence_delta_summary"] == {
        "count": 2,
        "positive_count": 1,
        "negative_count": 1,
        "neutral_count": 0,
        "total": 0.3,
        "average": 0.15,
        "latest": -0.1,
    }
    assert [item["action"] for item in payload["follow_up_actions"]] == ["pivot", "scale"]
