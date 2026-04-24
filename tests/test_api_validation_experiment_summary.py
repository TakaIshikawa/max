"""API tests for validation experiment summary reports."""

from __future__ import annotations

import json

from fastapi.testclient import TestClient

from max.server.app import create_app
from max.store.db import Store
from max.types.buildable_unit import BuildableCategory, BuildableUnit, IdeationMode


def _unit(unit_id: str, domain: str) -> BuildableUnit:
    return BuildableUnit(
        id=unit_id,
        title=f"{domain} API summary idea",
        one_liner="Expose validation experiment summaries",
        category=BuildableCategory.APPLICATION,
        ideation_mode=IdeationMode.DIRECT,
        problem="Validation experiments are hard to compare",
        solution="Provide an aggregate API report",
        value_proposition="Prioritize validation follow-up work",
        domain=domain,
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


def _seed(db_path: str) -> None:
    with Store(db_path=db_path, wal_mode=True) as store:
        store.insert_buildable_unit(_unit("bu-api-summary-devtools", "devtools"))
        store.insert_buildable_unit(_unit("bu-api-summary-finops", "finops"))
        store.create_validation_experiment(
            "bu-api-summary-devtools",
            hypothesis="Developers complete onboarding",
            method="prototype",
            success_metric="8 activations",
            status="completed",
            due_date="2000-01-01",
            completed_at="2000-01-02T00:00:00+00:00",
            result_summary=json.dumps({"outcome": "validated", "result_score": 0.9}),
            confidence_delta=0.4,
        )
        store.create_validation_experiment(
            "bu-api-summary-devtools",
            hypothesis="Managers approve rollout",
            method="interview",
            success_metric="4 approvals",
            status="blocked",
            due_date="2000-01-01",
            result_summary=json.dumps(
                {"outcome": "blocked", "follow_up_actions": ["find rollout owners"]}
            ),
        )
        store.create_validation_experiment(
            "bu-api-summary-finops",
            hypothesis="Finance teams trust recommendations",
            method="survey",
            success_metric="80 percent confidence",
            status="running",
            due_date="2999-01-01",
            result_summary=json.dumps({"outcome": "inconclusive", "result_score": 0.5}),
            confidence_delta=0.2,
        )


def _counts(items: list[dict]) -> dict[str, int]:
    return {item["key"]: item["count"] for item in items}


def test_validation_experiment_summary_api_returns_aggregates(tmp_path) -> None:
    db_path = str(tmp_path / "api.db")
    _seed(db_path)
    client = _client(db_path)

    response = client.get("/api/v1/validation-experiments/summary")

    assert response.status_code == 200
    payload = response.json()
    assert payload["total_count"] == 3
    assert payload["completed_count"] == 1
    assert payload["overdue_count"] == 1
    assert payload["completion_rate"] == 0.333
    assert payload["average_confidence_delta"] == 0.3
    assert payload["average_result_score"] == 0.7
    assert _counts(payload["by_domain"]) == {"devtools": 2, "finops": 1}
    assert _counts(payload["by_status"]) == {"blocked": 1, "completed": 1, "running": 1}
    assert payload["top_follow_up_actions"] == [
        {"action": "find rollout owners", "count": 1}
    ]


def test_validation_experiment_summary_api_filters_change_aggregates(tmp_path) -> None:
    db_path = str(tmp_path / "api.db")
    _seed(db_path)
    client = _client(db_path)

    domain = client.get("/api/v1/validation-experiments/summary?domain=devtools").json()
    idea = client.get(
        "/api/v1/validation-experiments/summary?idea_id=bu-api-summary-finops"
    ).json()
    status = client.get("/api/v1/validation-experiments/summary?status=blocked").json()
    overdue = client.get("/api/v1/validation-experiments/summary?overdue_only=true").json()

    assert domain["total_count"] == 2
    assert _counts(domain["by_domain"]) == {"devtools": 2}
    assert idea["total_count"] == 1
    assert _counts(idea["by_domain"]) == {"finops": 1}
    assert status["total_count"] == 1
    assert _counts(status["by_status"]) == {"blocked": 1}
    assert overdue["total_count"] == 1
    assert overdue["overdue_count"] == 1
    assert _counts(overdue["by_status"]) == {"blocked": 1}


def test_validation_experiment_summary_api_empty_report(tmp_path) -> None:
    db_path = str(tmp_path / "api.db")
    _seed(db_path)
    client = _client(db_path)

    response = client.get("/api/v1/validation-experiments/summary?domain=missing")

    assert response.status_code == 200
    payload = response.json()
    assert payload["filters"]["domain"] == "missing"
    assert payload["total_count"] == 0
    assert payload["completed_count"] == 0
    assert payload["overdue_count"] == 0
    assert payload["completion_rate"] == 0.0
    assert payload["by_status"] == []
    assert payload["by_domain"] == []
    assert payload["top_follow_up_actions"] == []
