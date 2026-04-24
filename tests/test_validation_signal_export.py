"""Tests for exporting validation experiments as evidence signals."""

from __future__ import annotations

from max.analysis.validation_signal_export import validation_experiment_signal
from max.store.db import Store
from max.types.buildable_unit import BuildableCategory, BuildableUnit, IdeationMode
from max.types.signal import SignalSourceType


def _make_unit(unit_id: str = "bu-export001") -> BuildableUnit:
    return BuildableUnit(
        id=unit_id,
        title="Validation Signal Idea",
        one_liner="Export validation results",
        category=BuildableCategory.APPLICATION,
        ideation_mode=IdeationMode.DIRECT,
        problem="Validation outcomes are disconnected",
        solution="Turn completed experiments into signals",
        value_proposition="Future ideation learns from validation",
    )


def _create_completed_experiment(store: Store, idea_id: str = "bu-export001") -> dict:
    experiment = store.create_validation_experiment(
        idea_id,
        hypothesis="Teams will export validation evidence",
        method="Prototype interview",
        target_sample_size=8,
        success_metric="6 teams ask to reuse the evidence",
        status="completed",
        completed_at="2026-04-25T00:00:00+00:00",
        result_summary="7 teams asked to reuse the evidence",
        evidence_urls=["https://example.com/notes"],
        confidence_delta=0.35,
    )
    assert experiment is not None
    return experiment


def test_validation_experiment_signal_payload_links_experiment_and_idea(store: Store) -> None:
    idea = _make_unit()
    store.insert_buildable_unit(idea)
    experiment = _create_completed_experiment(store)

    signal = validation_experiment_signal(experiment, idea)

    assert signal.source_type == SignalSourceType.EXPERIMENT
    assert signal.source_adapter == "validation_experiment"
    assert signal.url == f"max://validation-experiments/{experiment['id']}"
    assert signal.metadata["experiment_id"] == experiment["id"]
    assert signal.metadata["idea_id"] == idea.id
    assert signal.metadata["hypothesis"] == experiment["hypothesis"]
    assert signal.metadata["method"] == experiment["method"]
    assert signal.metadata["status"] == "completed"
    assert signal.metadata["confidence_delta"] == 0.35
    assert signal.metadata["evidence_urls"] == ["https://example.com/notes"]


def test_store_finds_exported_signal_by_validation_experiment_metadata(store: Store) -> None:
    idea = _make_unit()
    store.insert_buildable_unit(idea)
    experiment = _create_completed_experiment(store)
    inserted = store.insert_signal(validation_experiment_signal(experiment, idea))

    found = store.get_signal_by_validation_experiment_id(experiment["id"])

    assert found is not None
    assert found.id == inserted.id
    assert found.metadata["idea_id"] == idea.id
    assert store.get_signal_by_validation_experiment_id("missing") is None
