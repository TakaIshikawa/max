"""Tests for batch spec readiness API."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from max.server.app import create_app
from max.store.db import Store
from max.types.buildable_unit import BuildableCategory, BuildableUnit
from max.types.evaluation import DimensionScore, UtilityEvaluation


@pytest.fixture
def db_path(tmp_path) -> str:
    path = str(tmp_path / "spec_readiness_batch.db")
    store = Store(db_path=path, wal_mode=True)
    store.close()
    return path


@pytest.fixture
def client(db_path: str) -> TestClient:
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


def _ready_unit(
    unit_id: str,
    *,
    domain: str = "proptech",
    status: str = "approved",
    updated_at: datetime | None = None,
) -> BuildableUnit:
    return BuildableUnit(
        id=unit_id,
        title=f"Ready Idea {unit_id}",
        one_liner="A ready idea for handoff",
        category=BuildableCategory.APPLICATION,
        problem="Operators cannot reliably triage maintenance requests today",
        solution="Provide a shared queue that prioritizes requests by urgency",
        target_users="humans",
        value_proposition="Reduce delayed urgent maintenance work substantially",
        specific_user="property operations manager",
        workflow_context="daily maintenance request triage",
        validation_plan="pilot with three property teams for two weeks",
        domain_risks=["tenant adoption"],
        evidence_rationale="Interviews and tickets show repeated triage delays.",
        inspiring_insights=["ins-ready"],
        evidence_signals=["sig-ready"],
        tech_approach="Python API with React workflow dashboard",
        suggested_stack={"backend": "fastapi", "frontend": "react"},
        domain=domain,
        status=status,
        updated_at=updated_at or datetime.now(timezone.utc),
    )


def _incomplete_unit(unit_id: str, *, domain: str = "proptech", status: str = "approved") -> BuildableUnit:
    return BuildableUnit(
        id=unit_id,
        title=f"Incomplete Idea {unit_id}",
        one_liner="Too thin",
        category=BuildableCategory.APPLICATION,
        problem="Vague problem",
        solution="Vague solution",
        value_proposition="Value",
        domain=domain,
        status=status,
    )


def _evaluation(unit_id: str, recommendation: str = "yes") -> UtilityEvaluation:
    score = DimensionScore(value=8.0, confidence=0.7, reasoning="test")
    return UtilityEvaluation(
        buildable_unit_id=unit_id,
        pain_severity=score,
        addressable_scale=score,
        build_effort=score,
        composability=score,
        competitive_density=score,
        timing_fit=score,
        compounding_value=score,
        overall_score=80.0,
        recommendation=recommendation,
    )


def _seed(db_path: str, *units: BuildableUnit, evaluated_ids: set[str] | None = None) -> None:
    store = Store(db_path=db_path, wal_mode=True)
    try:
        for unit in units:
            store.insert_buildable_unit(unit)
            if evaluated_ids is None or unit.id in evaluated_ids:
                store.insert_evaluation(_evaluation(unit.id))
    finally:
        store.close()


def test_spec_readiness_batch_preserves_explicit_id_order(client: TestClient, db_path: str) -> None:
    _seed(
        db_path,
        _ready_unit("bu-ready-1"),
        _incomplete_unit("bu-incomplete-1"),
    )

    response = client.post(
        "/api/v1/ideas/spec-readiness-batch",
        json={"idea_ids": ["bu-incomplete-1", "bu-ready-1"]},
    )

    assert response.status_code == 200
    results = response.json()["results"]
    assert [item["idea_id"] for item in results] == ["bu-incomplete-1", "bu-ready-1"]
    assert results[0]["status"] == "evaluated"
    assert results[0]["success"] is True
    assert results[0]["score"] < 100.0
    assert "Problem clarity" in results[0]["missing_sections"]
    assert "Clarify the problem" in " ".join(results[0]["blockers"])
    assert results[1]["readiness_status"] == "pass"
    assert results[1]["passed"] is True
    assert results[1]["readiness"]["idea_id"] == "bu-ready-1"


def test_spec_readiness_batch_reports_missing_ids_without_aborting(
    client: TestClient,
    db_path: str,
) -> None:
    _seed(db_path, _ready_unit("bu-ready-1"))

    response = client.post(
        "/api/v1/ideas/spec-readiness-batch",
        json={"idea_ids": ["bu-ready-1", "bu-missing", "bu-ready-1"]},
    )

    assert response.status_code == 200
    results = response.json()["results"]
    assert [item["idea_id"] for item in results] == ["bu-ready-1", "bu-missing", "bu-ready-1"]
    assert results[0]["status"] == "evaluated"
    assert results[1] == {
        "idea_id": "bu-missing",
        "status": "not_found",
        "success": False,
        "score": None,
        "readiness_status": None,
        "passed": None,
        "missing_sections": [],
        "blockers": [],
        "failed_check_ids": [],
        "readiness": None,
        "error": "Idea not found: bu-missing",
    }
    assert results[2]["status"] == "evaluated"


def test_spec_readiness_batch_filters_by_domain_status_and_limit(
    client: TestClient,
    db_path: str,
) -> None:
    _seed(
        db_path,
        _ready_unit(
            "bu-old-approved-proptech",
            domain="proptech",
            status="approved",
            updated_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        ),
        _ready_unit(
            "bu-new-approved-proptech",
            domain="proptech",
            status="approved",
            updated_at=datetime(2026, 1, 2, tzinfo=timezone.utc),
        ),
        _ready_unit("bu-draft-proptech", domain="proptech", status="draft"),
        _ready_unit("bu-approved-fintech", domain="fintech", status="approved"),
    )

    response = client.post(
        "/api/v1/ideas/spec-readiness-batch",
        json={"domain": "proptech", "status": "approved", "limit": 1},
    )

    assert response.status_code == 200
    results = response.json()["results"]
    assert [item["idea_id"] for item in results] == ["bu-new-approved-proptech"]
    assert results[0]["readiness_status"] == "pass"


def test_spec_readiness_batch_requires_ids_or_filters(client: TestClient) -> None:
    response = client.post("/api/v1/ideas/spec-readiness-batch", json={})

    assert response.status_code == 422
