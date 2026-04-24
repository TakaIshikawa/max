"""Tests for persisted validation experiments."""

from __future__ import annotations

import json
from unittest.mock import patch

from click.testing import CliRunner
from fastapi.testclient import TestClient

from max.cli import main
from max.server.app import create_app
from max.store.db import Store
from max.types.buildable_unit import BuildableCategory, BuildableUnit, IdeationMode


def _make_unit(unit_id: str = "bu-vexp001") -> BuildableUnit:
    return BuildableUnit(
        id=unit_id,
        title="Validation Experiment Idea",
        one_liner="Track validation work",
        category=BuildableCategory.APPLICATION,
        ideation_mode=IdeationMode.DIRECT,
        problem="Validation is not tracked",
        solution="Persist experiment outcomes",
        value_proposition="Better review prioritization",
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


def test_store_create_list_and_update_validation_experiment(store: Store) -> None:
    store.insert_buildable_unit(_make_unit())

    created = store.create_validation_experiment(
        "bu-vexp001",
        hypothesis="Teams will book interviews",
        method="Landing page concierge test",
        target_sample_size=25,
        success_metric="5 booked interviews",
        status="running",
        started_at="2026-04-24T00:00:00+00:00",
        evidence_urls=["https://example.com/results"],
        confidence_delta=0.2,
    )

    assert created is not None
    assert created["id"].startswith("vexp-")
    assert created["idea_id"] == "bu-vexp001"
    assert created["evidence_urls"] == ["https://example.com/results"]

    listed = store.list_validation_experiments("bu-vexp001")
    assert listed is not None
    assert [experiment["id"] for experiment in listed] == [created["id"]]

    updated = store.update_validation_experiment(
        created["id"],
        status="completed",
        completed_at="2026-04-25T00:00:00+00:00",
        result_summary="6 interviews booked",
        confidence_delta=0.35,
        evidence_urls=["https://example.com/final"],
    )

    assert updated is not None
    assert updated["status"] == "completed"
    assert updated["result_summary"] == "6 interviews booked"
    assert updated["evidence_urls"] == ["https://example.com/final"]
    assert updated["confidence_delta"] == 0.35


def test_store_validation_experiments_return_none_for_unknown_records(store: Store) -> None:
    assert store.create_validation_experiment(
        "missing",
        hypothesis="x",
        method="y",
        success_metric="z",
    ) is None
    assert store.list_validation_experiments("missing") is None
    assert store.update_validation_experiment("missing", status="completed") is None


def test_api_create_list_update_and_404(tmp_path) -> None:
    db_path = str(tmp_path / "api.db")
    with Store(db_path=db_path, wal_mode=True) as store:
        store.insert_buildable_unit(_make_unit())

    client = _client(db_path)
    create_response = client.post(
        "/api/v1/ideas/bu-vexp001/validation-experiments",
        json={
            "hypothesis": "Users will share evidence",
            "method": "Prototype interview",
            "target_sample_size": 10,
            "success_metric": "7 positive responses",
            "status": "planned",
            "evidence_urls": ["https://example.com/prototype"],
        },
    )
    assert create_response.status_code == 201
    experiment = create_response.json()
    assert experiment["idea_id"] == "bu-vexp001"
    assert experiment["evidence_urls"] == ["https://example.com/prototype"]

    list_response = client.get("/api/v1/ideas/bu-vexp001/validation-experiments")
    assert list_response.status_code == 200
    assert [item["id"] for item in list_response.json()] == [experiment["id"]]

    update_response = client.patch(
        f"/api/v1/validation-experiments/{experiment['id']}",
        json={
            "status": "completed",
            "result_summary": "8 positive responses",
            "confidence_delta": 0.4,
        },
    )
    assert update_response.status_code == 200
    assert update_response.json()["status"] == "completed"
    assert update_response.json()["confidence_delta"] == 0.4

    assert client.get("/api/v1/ideas/missing/validation-experiments").status_code == 404
    assert client.post(
        "/api/v1/ideas/missing/validation-experiments",
        json={
            "hypothesis": "x",
            "method": "y",
            "success_metric": "z",
        },
    ).status_code == 404
    assert client.patch(
        "/api/v1/validation-experiments/missing",
        json={"status": "completed"},
    ).status_code == 404


def test_cli_create_list_and_update_validation_experiment(tmp_path) -> None:
    db_path = str(tmp_path / "cli.db")
    RealStore = Store
    with RealStore(db_path=db_path) as store:
        store.insert_buildable_unit(_make_unit())

    def store_factory(*args, **kwargs):
        return RealStore(db_path=db_path, **kwargs)

    runner = CliRunner()
    with patch("max.store.db.Store", side_effect=store_factory):
        created = runner.invoke(
            main,
            [
                "validation-experiments",
                "create",
                "bu-vexp001",
                "--hypothesis",
                "Users will pay",
                "--method",
                "Smoke test",
                "--target-sample-size",
                "30",
                "--success-metric",
                "3 preorders",
                "--evidence-url",
                "https://example.com/smoke",
                "--format",
                "json",
            ],
        )
        assert created.exit_code == 0, created.output
        experiment = json.loads(created.output)
        assert experiment["hypothesis"] == "Users will pay"

        listed = runner.invoke(
            main,
            ["validation-experiments", "list", "bu-vexp001", "--format", "json"],
        )
        assert listed.exit_code == 0, listed.output
        assert json.loads(listed.output)[0]["id"] == experiment["id"]

        updated = runner.invoke(
            main,
            [
                "validation-experiments",
                "update",
                experiment["id"],
                "--status",
                "completed",
                "--result-summary",
                "4 preorders",
                "--confidence-delta",
                "0.5",
                "--format",
                "json",
            ],
        )
        assert updated.exit_code == 0, updated.output
        payload = json.loads(updated.output)
        assert payload["status"] == "completed"
        assert payload["result_summary"] == "4 preorders"
