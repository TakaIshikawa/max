"""API tests for idea customer discovery scripts."""

from __future__ import annotations

from fastapi.testclient import TestClient

from max.server.app import create_app
from max.store.db import Store
from max.types.buildable_unit import BuildableCategory, BuildableUnit
from max.types.signal import Signal, SignalSourceType


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


def test_customer_discovery_script_api_returns_schema_backed_response(tmp_path) -> None:
    db_path = str(tmp_path / "customer-discovery-api.db")
    store = Store(db_path=db_path, wal_mode=True)
    store.insert_signal(
        Signal(
            id="sig-cd-api",
            source_type=SignalSourceType.FORUM,
            source_adapter="test",
            title="Manual onboarding pain",
            content="RevOps teams lose deals during manual onboarding handoffs.",
            url="https://example.com/manual-onboarding",
            credibility=0.8,
        )
    )
    store.insert_buildable_unit(
        BuildableUnit(
            id="bu-cd-api",
            title="Onboarding Handoff Tracker",
            one_liner="Track revenue onboarding handoffs",
            category=BuildableCategory.APPLICATION,
            problem="customer onboarding handoffs stall after sales close",
            solution="a shared handoff tracker with owner prompts",
            value_proposition="reduce delayed onboarding and churn risk",
            specific_user="revops manager",
            buyer="VP Customer Success",
            workflow_context="post-sale customer onboarding",
            current_workaround="CRM notes and weekly status meetings",
            evidence_signals=["sig-cd-api"],
        )
    )
    store.create_validation_experiment(
        "bu-cd-api",
        hypothesis="revops managers will share stalled handoff examples in interviews",
        method="problem interviews",
        target_sample_size=6,
        success_metric="4 of 6 describe a recent stalled handoff",
    )
    store.close()

    response = _client(db_path).get("/api/v1/ideas/bu-cd-api/customer-discovery-script")

    assert response.status_code == 200
    payload = response.json()
    assert payload["idea_id"] == "bu-cd-api"
    assert payload["sections"]["screening"]["questions"]
    assert payload["sections"]["interview"]["demo_prompts"]
    assert payload["sections"]["follow_up"]["artifacts"]
    assert any("revops manager" in profile for profile in payload["target_respondent_profiles"])
    assert any(
        "revops managers will share stalled handoff examples" in question["prompt"]
        for question in payload["disconfirming_questions"]
    )


def test_customer_discovery_script_api_returns_404_for_unknown_idea(tmp_path) -> None:
    db_path = str(tmp_path / "customer-discovery-missing.db")
    store = Store(db_path=db_path, wal_mode=True)
    store.close()

    response = _client(db_path).get("/api/v1/ideas/missing/customer-discovery-script")

    assert response.status_code == 404
