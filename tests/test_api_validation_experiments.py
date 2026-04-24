"""API tests for validation experiment signal export."""

from __future__ import annotations

from fastapi.testclient import TestClient

from max.server.app import create_app
from max.store.db import Store
from max.types.buildable_unit import BuildableCategory, BuildableUnit, IdeationMode


def _make_unit(unit_id: str = "bu-api-vexp001") -> BuildableUnit:
    return BuildableUnit(
        id=unit_id,
        title="API Validation Export",
        one_liner="Export validation experiments from the API",
        category=BuildableCategory.APPLICATION,
        ideation_mode=IdeationMode.DIRECT,
        problem="Experiment results are not available as signals",
        solution="Expose an export endpoint",
        value_proposition="Reuse validation outcomes as evidence",
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


def _create_experiment(db_path: str, *, status: str = "completed") -> dict:
    with Store(db_path=db_path, wal_mode=True) as store:
        store.insert_buildable_unit(_make_unit())
        experiment = store.create_validation_experiment(
            "bu-api-vexp001",
            hypothesis="Users will trust exported evidence",
            method="Concierge validation review",
            success_metric="5 reviewers cite the result",
            status=status,
            completed_at="2026-04-25T00:00:00+00:00" if status == "completed" else None,
            result_summary="6 reviewers cited the result",
            evidence_urls=["https://example.com/review"],
            confidence_delta=0.25,
        )
        assert experiment is not None
        return experiment


def test_export_completed_validation_experiment_creates_signal(tmp_path) -> None:
    db_path = str(tmp_path / "api.db")
    experiment = _create_experiment(db_path)
    client = _client(db_path)

    response = client.post(f"/api/v1/validation-experiments/{experiment['id']}/export-signal")

    assert response.status_code == 201
    payload = response.json()
    assert payload["status"] == "created"
    assert payload["signal_id"].startswith("sig-")

    with Store(db_path=db_path, wal_mode=True) as store:
        signal = store.get_signal(payload["signal_id"])
        assert signal is not None
        assert signal.source_adapter == "validation_experiment"
        assert signal.source_type.value == "experiment"
        assert signal.metadata["experiment_id"] == experiment["id"]
        assert signal.metadata["idea_id"] == "bu-api-vexp001"
        assert signal.metadata["hypothesis"] == "Users will trust exported evidence"
        assert signal.metadata["method"] == "Concierge validation review"
        assert signal.metadata["status"] == "completed"
        assert signal.metadata["confidence_delta"] == 0.25
        assert signal.metadata["evidence_urls"] == ["https://example.com/review"]


def test_export_completed_validation_experiment_is_idempotent(tmp_path) -> None:
    db_path = str(tmp_path / "api.db")
    experiment = _create_experiment(db_path)
    client = _client(db_path)

    first = client.post(f"/api/v1/validation-experiments/{experiment['id']}/export-signal")
    second = client.post(f"/api/v1/validation-experiments/{experiment['id']}/export-signal")

    assert first.status_code == 201
    assert second.status_code == 200
    assert second.json() == {"signal_id": first.json()["signal_id"], "status": "existing"}
    with Store(db_path=db_path, wal_mode=True) as store:
        assert store.count_signals(source_adapter="validation_experiment") == 1


def test_export_non_completed_validation_experiment_returns_409(tmp_path) -> None:
    db_path = str(tmp_path / "api.db")
    experiment = _create_experiment(db_path, status="running")
    client = _client(db_path)

    response = client.post(f"/api/v1/validation-experiments/{experiment['id']}/export-signal")

    assert response.status_code == 409
    with Store(db_path=db_path, wal_mode=True) as store:
        assert store.count_signals(source_adapter="validation_experiment") == 0


def test_export_missing_validation_experiment_returns_404(tmp_path) -> None:
    db_path = str(tmp_path / "api.db")
    client = _client(db_path)

    response = client.post("/api/v1/validation-experiments/missing/export-signal")

    assert response.status_code == 404
