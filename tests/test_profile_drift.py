"""Tests for profile drift analysis."""

from __future__ import annotations

from datetime import datetime, timezone

from max.analysis.profile_drift import build_profile_drift_report
from max.profiles.schema import DomainContext, EvaluationConfig, PipelineProfile, SourceConfig
from max.store.db import Store
from max.types.buildable_unit import BuildableUnit
from max.types.evaluation import DimensionScore, UtilityEvaluation
from max.types.signal import Signal


def _profile() -> PipelineProfile:
    return PipelineProfile(
        name="test-profile",
        domain=DomainContext(
            name="test-domain",
            description="Test domain",
            categories=["application", "integration"],
            target_user_types=["admins", "operators"],
        ),
        sources=[
            SourceConfig(adapter="reddit", weight=3.0),
            SourceConfig(adapter="github", weight=1.0),
            SourceConfig(adapter="hackernews", enabled=False),
        ],
        evaluation=EvaluationConfig(weight_profile="default"),
    )


def _evaluation(unit_id: str, weights: dict[str, float]) -> UtilityEvaluation:
    score = DimensionScore(value=7.0, confidence=0.8, reasoning="ok")
    return UtilityEvaluation(
        buildable_unit_id=unit_id,
        pain_severity=score,
        addressable_scale=score,
        build_effort=score,
        composability=score,
        competitive_density=score,
        timing_fit=score,
        compounding_value=score,
        overall_score=70.0,
        weights_used=weights,
    )


def test_profile_drift_reports_observed_distribution_mismatches(tmp_path):
    profile = _profile()
    with Store(str(tmp_path / "max.db")) as store:
        sig1 = store.insert_signal(
            Signal(
                source_type="forum",
                source_adapter="reddit",
                title="Signal 1",
                content="content",
                url="https://example.com/1",
                fetched_at=datetime.now(timezone.utc),
            )
        )
        sig2 = store.insert_signal(
            Signal(
                source_type="forum",
                source_adapter="hackernews",
                title="Signal 2",
                content="content",
                url="https://example.com/2",
                fetched_at=datetime.now(timezone.utc),
            )
        )
        unit = store.insert_buildable_unit(
            BuildableUnit(
                title="Unexpected unit",
                one_liner="one liner",
                category="workflow",
                problem="problem",
                solution="solution",
                target_users="founders",
                value_proposition="value",
                evidence_signals=[sig1.id, sig2.id],
                domain=profile.domain.name,
            )
        )
        store.insert_evaluation(_evaluation(unit.id, {"pain_severity": 1.0}))

        report = build_profile_drift_report(profile, store)

    assert report.profile_name == "test-profile"
    assert report.units_analyzed == 1
    assert report.signals_analyzed == 2
    assert report.category_drift.unexpected == ["workflow"]
    assert report.target_user_drift.unexpected == ["founders"]
    assert report.source_mix_drift.unexpected == ["hackernews"]
    assert report.evaluation_weight_mismatch.mismatched_evaluation_count == 1
    assert report.overall_drift_score > 0


def test_profile_drift_to_dict_is_api_serializable(tmp_path):
    profile = _profile()
    with Store(str(tmp_path / "max.db")) as store:
        report = build_profile_drift_report(profile, store)

    payload = report.to_dict()

    assert payload["profile_name"] == "test-profile"
    assert payload["category_drift"]["metric"] == "category_drift"
    assert payload["evaluation_weight_mismatch"]["status"] == "insufficient_data"
