"""API tests for evaluation sensitivity reports."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from max.server.app import create_app
from max.store.db import Store
from max.types.buildable_unit import BuildableCategory, BuildableUnit, IdeationMode
from max.types.evaluation import DimensionScore, UtilityEvaluation


@pytest.fixture
def db_path(tmp_path):
    path = str(tmp_path / "test_api_sensitivity.db")
    store = Store(db_path=path, wal_mode=True)
    store.close()
    return path


@pytest.fixture
def client(db_path):
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


def _score(value: float) -> DimensionScore:
    return DimensionScore(value=value, confidence=0.7, reasoning="test")


def _unit(idea_id: str = "bu-sensitive-api") -> BuildableUnit:
    return BuildableUnit(
        id=idea_id,
        title="Sensitivity API Idea",
        one_liner="Reports score sensitivity",
        category=BuildableCategory.APPLICATION,
        ideation_mode=IdeationMode.DIRECT,
        problem="Reviewers cannot see score sensitivity.",
        solution="Expose deterministic sensitivity analysis.",
        value_proposition="More actionable scoring decisions.",
    )


def _evaluation(idea_id: str = "bu-sensitive-api") -> UtilityEvaluation:
    return UtilityEvaluation(
        buildable_unit_id=idea_id,
        pain_severity=_score(8.0),
        addressable_scale=_score(7.0),
        build_effort=_score(7.5),
        composability=_score(8.5),
        competitive_density=_score(9.0),
        timing_fit=_score(8.0),
        compounding_value=_score(7.0),
        overall_score=78.0,
        strengths=["Good"],
        weaknesses=["Limited"],
        recommendation="yes",
        weights_used={"pain_severity": 0.20},
    )


def test_get_idea_evaluation_sensitivity_returns_deterministic_json(client, db_path) -> None:
    store = Store(db_path=db_path, wal_mode=True)
    try:
        store.insert_buildable_unit(_unit())
        store.insert_evaluation(_evaluation())
    finally:
        store.close()

    response = client.get("/api/v1/ideas/bu-sensitive-api/evaluation-sensitivity")

    assert response.status_code == 200
    payload = response.json()
    assert payload["idea_id"] == "bu-sensitive-api"
    assert payload["baseline_score"] == 78.0
    assert payload["baseline_recommendation"] == "yes"
    assert round(sum(payload["weight_profile"].values()), 6) == 1.0
    assert len(payload["dimensions"]) == 7
    assert payload["dimensions"][0] == {
        "dimension": "compounding_value",
        "label": "Compounding value",
        "score": 7.0,
        "confidence": 0.7,
        "weight": 0.15,
        "score_delta": 1.41,
        "recommendation_delta": 0,
        "leave_one_out_score": 79.41,
        "leave_one_out_recommendation": "yes",
        "weight_down_score": 78.12,
        "weight_down_delta": 0.12,
        "weight_down_recommendation": "yes",
        "weight_up_score": 77.88,
        "weight_up_delta": -0.12,
        "weight_up_recommendation": "yes",
        "explanation": (
            "Removing Compounding value would increase the score by "
            "1.41 points without changing the recommendation; it currently "
            "scores 7.0/10 at weight 0.15."
        ),
    }


def test_get_idea_evaluation_sensitivity_returns_404_for_missing_idea(client) -> None:
    response = client.get("/api/v1/ideas/missing/evaluation-sensitivity")

    assert response.status_code == 404
    assert response.json()["detail"] == "Idea not found: missing"


def test_get_idea_evaluation_sensitivity_returns_404_for_missing_evaluation(
    client,
    db_path,
) -> None:
    store = Store(db_path=db_path, wal_mode=True)
    try:
        store.insert_buildable_unit(_unit("bu-no-evaluation"))
    finally:
        store.close()

    response = client.get("/api/v1/ideas/bu-no-evaluation/evaluation-sensitivity")

    assert response.status_code == 404
    assert response.json()["detail"] == "Evaluation not found: bu-no-evaluation"
