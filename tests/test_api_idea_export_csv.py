from __future__ import annotations

import csv
from io import StringIO

import pytest
from fastapi.testclient import TestClient

from max.server.app import create_app
from max.server.dependencies import get_store
from max.store.db import Store
from max.types.buildable_unit import BuildableCategory, BuildableUnit, IdeationMode
from max.types.evaluation import DimensionScore, UtilityEvaluation


@pytest.fixture
def db_path(tmp_path):
    path = str(tmp_path / "api_idea_export_csv.db")
    store = Store(db_path=path, wal_mode=True)
    store.close()
    return path


@pytest.fixture
def client(db_path):
    app = create_app()

    def override_get_store():
        store = Store(db_path=db_path, wal_mode=True)
        try:
            yield store
        finally:
            store.close()

    app.dependency_overrides[get_store] = override_get_store
    return TestClient(app)


def test_export_ideas_accepts_format_csv_and_returns_csv_attachment(client, db_path) -> None:
    store = Store(db_path=db_path, wal_mode=True)
    try:
        store.insert_buildable_unit(_unit("bu-csv001"))
        store.insert_evaluation(_evaluation("bu-csv001", 82.5))
    finally:
        store.close()

    response = client.get("/api/v1/exports/ideas?format=csv")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    assert response.headers["content-disposition"] == 'attachment; filename="ideas-export.csv"'

    reader = csv.DictReader(StringIO(response.text))
    assert reader.fieldnames == [
        "id",
        "title",
        "domain",
        "status",
        "category",
        "recommendation",
        "overall_score",
        "source_adapters",
        "evidence_signal_count",
        "created_at",
        "updated_at",
    ]
    rows = list(reader)
    assert len(rows) == 1
    assert rows[0]["id"] == "bu-csv001"
    assert rows[0]["overall_score"] == "82.5"
    assert rows[0]["evidence_signal_count"] == "2"


def test_export_ideas_csv_keeps_existing_fmt_query(client, db_path) -> None:
    store = Store(db_path=db_path, wal_mode=True)
    try:
        store.insert_buildable_unit(_unit("bu-fmt001"))
    finally:
        store.close()

    response = client.get("/api/v1/exports/ideas?fmt=csv")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")


def test_export_ideas_invalid_format_returns_validation_error(client) -> None:
    response = client.get("/api/v1/exports/ideas?format=xml")

    assert response.status_code == 422


def _unit(unit_id: str) -> BuildableUnit:
    return BuildableUnit(
        id=unit_id,
        title="CSV Export Idea",
        one_liner="Review generated ideas in a spreadsheet",
        category=BuildableCategory.APPLICATION,
        ideation_mode=IdeationMode.DIRECT,
        problem="Operators need spreadsheet review",
        solution="Export ideas as CSV",
        value_proposition="Faster review",
        status="evaluated",
        domain="ops",
        evidence_signals=["sig-1", "sig-2"],
    )


def _evaluation(unit_id: str, score: float) -> UtilityEvaluation:
    return UtilityEvaluation(
        buildable_unit_id=unit_id,
        pain_severity=_dimension(8.0),
        addressable_scale=_dimension(7.0),
        build_effort=_dimension(6.0),
        composability=_dimension(8.0),
        competitive_density=_dimension(7.0),
        timing_fit=_dimension(8.0),
        compounding_value=_dimension(9.0),
        overall_score=score,
        recommendation="yes",
    )


def _dimension(value: float) -> DimensionScore:
    return DimensionScore(value=value, confidence=0.8, reasoning="test")
