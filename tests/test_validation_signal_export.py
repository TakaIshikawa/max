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


def _make_experiment(evidence_urls: object) -> dict:
    return {
        "id": "vexp-export001",
        "idea_id": "bu-export001",
        "hypothesis": "Teams will export validation evidence",
        "method": "Prototype interview",
        "success_metric": "6 teams ask to reuse the evidence",
        "status": "completed",
        "completed_at": "2026-04-25T00:00:00+00:00",
        "result_summary": "7 teams asked to reuse the evidence",
        "evidence_urls": evidence_urls,
        "confidence_delta": 0.35,
    }


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


def test_validation_experiment_signal_treats_string_evidence_url_as_single_url() -> None:
    signal = validation_experiment_signal(
        _make_experiment(" https://example.com/notes "),
        _make_unit(),
    )

    assert signal.metadata["evidence_urls"] == ["https://example.com/notes"]
    assert "Evidence URLs: https://example.com/notes" in signal.content


def test_validation_experiment_signal_filters_malformed_evidence_url_iterables() -> None:
    signal = validation_experiment_signal(
        _make_experiment(
            [
                " https://example.com/notes ",
                "",
                "   ",
                None,
                12,
                "https://example.com/results",
            ]
        ),
        _make_unit(),
    )

    assert signal.metadata["evidence_urls"] == [
        "https://example.com/notes",
        "https://example.com/results",
    ]
    assert (
        "Evidence URLs: https://example.com/notes, https://example.com/results"
        in signal.content
    )


def test_validation_experiment_signal_ignores_scalar_evidence_url_values() -> None:
    signal = validation_experiment_signal(_make_experiment(12), _make_unit())

    assert signal.metadata["evidence_urls"] == []
    assert "Evidence URLs:" not in signal.content


def test_validation_experiment_signal_handles_tuple_evidence_urls() -> None:
    signal = validation_experiment_signal(
        _make_experiment((" https://example.com/notes ", "https://example.com/results")),
        _make_unit(),
    )

    assert signal.metadata["evidence_urls"] == [
        "https://example.com/notes",
        "https://example.com/results",
    ]


def test_validation_experiment_signal_handles_set_evidence_urls() -> None:
    signal = validation_experiment_signal(
        _make_experiment({"https://example.com/notes", "https://example.com/results"}),
        _make_unit(),
    )

    # Sets are unordered, so check both URLs are present
    assert len(signal.metadata["evidence_urls"]) == 2
    assert "https://example.com/notes" in signal.metadata["evidence_urls"]
    assert "https://example.com/results" in signal.metadata["evidence_urls"]


def test_validation_experiment_signal_ignores_dict_evidence_urls() -> None:
    signal = validation_experiment_signal(
        _make_experiment({"url": "https://example.com/notes"}),
        _make_unit(),
    )

    assert signal.metadata["evidence_urls"] == []
    assert "Evidence URLs:" not in signal.content


def test_validation_experiment_signal_ignores_bytes_evidence_urls() -> None:
    signal = validation_experiment_signal(
        _make_experiment(b"https://example.com/notes"),
        _make_unit(),
    )

    assert signal.metadata["evidence_urls"] == []
    assert "Evidence URLs:" not in signal.content


def test_validation_experiment_signal_ignores_none_evidence_urls() -> None:
    signal = validation_experiment_signal(
        _make_experiment(None),
        _make_unit(),
    )

    assert signal.metadata["evidence_urls"] == []
    assert "Evidence URLs:" not in signal.content


def test_validation_experiment_signal_handles_mixed_iterable_with_non_strings() -> None:
    signal = validation_experiment_signal(
        _make_experiment(["https://example.com/notes", 42, None, b"bytes", {"key": "val"}]),
        _make_unit(),
    )

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
