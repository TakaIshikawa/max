"""Tests for the ClinicalTrials.gov source adapter."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from max.sources.clinical_trials import (
    CLINICAL_TRIALS_STUDIES_URL,
    ClinicalTrialsAdapter,
    _DEFAULT_TERMS,
)
from max.types.signal import SignalSourceType


ACTIVE_RECRUITING_RESPONSE = {
    "studies": [
        {
            "protocolSection": {
                "identificationModule": {
                    "nctId": "NCT06000001",
                    "briefTitle": "AI Triage Workflow for Heart Failure Care",
                },
                "descriptionModule": {
                    "briefSummary": "Testing AI-assisted triage in clinical workflows.",
                },
                "statusModule": {
                    "overallStatus": "RECRUITING",
                    "startDateStruct": {"date": "2026-01-15"},
                    "completionDateStruct": {"date": "2027-06"},
                },
                "conditionsModule": {"conditions": ["Heart Failure"]},
                "armsInterventionsModule": {
                    "interventions": [
                        {"type": "DEVICE", "name": "AI triage dashboard"},
                        {"type": "OTHER", "name": "Care coordination workflow"},
                    ]
                },
                "sponsorCollaboratorsModule": {
                    "leadSponsor": {"name": "Example Medical Center"},
                },
                "designModule": {
                    "phases": ["NA"],
                    "enrollmentInfo": {"count": 240},
                },
                "contactsLocationsModule": {
                    "locations": [{"facility": "Main Hospital"}, {"facility": "Clinic B"}],
                },
            }
        }
    ]
}


MISSING_OPTIONAL_RESPONSE = {
    "studies": [
        {
            "protocolSection": {
                "identificationModule": {
                    "nctId": "NCT06000002",
                    "briefTitle": "Remote Monitoring Pilot",
                },
            }
        }
    ]
}


DEDUP_RESPONSE = {
    "studies": [
        {
            "protocolSection": {
                "identificationModule": {
                    "nctId": "NCT06000003",
                    "briefTitle": "Clinical Decision Support Study",
                },
                "descriptionModule": {"briefSummary": "First copy."},
            }
        },
        {
            "protocolSection": {
                "identificationModule": {
                    "nctId": "NCT06000003",
                    "briefTitle": "Clinical Decision Support Study Duplicate",
                },
                "descriptionModule": {"briefSummary": "Second copy."},
            }
        },
    ]
}


def test_clinical_trials_adapter_properties() -> None:
    adapter = ClinicalTrialsAdapter()

    assert adapter.name == "clinical_trials"
    assert adapter.source_type == SignalSourceType.EXPERIMENT.value
    assert adapter.terms == _DEFAULT_TERMS
    assert adapter.conditions == []
    assert adapter.intervention_terms == []


def test_clinical_trials_adapter_custom_config() -> None:
    adapter = ClinicalTrialsAdapter(
        config={
            "terms": ["ambient documentation"],
            "conditions": ["diabetes"],
            "intervention_terms": ["machine learning"],
            "watchlist_terms": ["care navigation"],
            "max_results_per_query": "5",
        }
    )

    assert adapter.terms == ["ambient documentation", "care navigation"]
    assert adapter.conditions == ["diabetes", "care navigation"]
    assert adapter.intervention_terms == ["machine learning", "care navigation"]
    assert adapter.max_results_per_query == 5


@pytest.mark.asyncio
async def test_fetch_emits_normalized_signal_from_active_recruiting_study() -> None:
    adapter = ClinicalTrialsAdapter(config={"terms": ["AI triage"], "conditions": []})

    with patch("max.sources.clinical_trials.fetch_with_retry") as mock_fetch:
        mock_fetch.return_value = MagicMock(json=lambda: ACTIVE_RECRUITING_RESPONSE)

        signals = await adapter.fetch(limit=10)

    assert len(signals) == 1
    assert mock_fetch.call_args.args[0] == CLINICAL_TRIALS_STUDIES_URL
    assert mock_fetch.call_args.kwargs["params"] == {
        "query.term": "AI triage",
        "pageSize": 10,
        "format": "json",
    }

    signal = signals[0]
    assert signal.id == "clinical_trials:NCT06000001"
    assert signal.source_type == SignalSourceType.EXPERIMENT
    assert signal.source_adapter == "clinical_trials"
    assert signal.title == "AI Triage Workflow for Heart Failure Care"
    assert signal.content.startswith("Testing AI-assisted triage")
    assert signal.url == "https://clinicaltrials.gov/study/NCT06000001"
    assert signal.published_at == datetime(2026, 1, 15, tzinfo=timezone.utc)
    assert signal.credibility > 0.6
    assert "clinical-trials" in signal.tags
    assert "heart-failure" in signal.tags
    assert signal.metadata["nct_id"] == "NCT06000001"
    assert signal.metadata["status"] == "RECRUITING"
    assert signal.metadata["phases"] == ["NA"]
    assert signal.metadata["conditions"] == ["Heart Failure"]
    assert signal.metadata["interventions"] == [
        "AI triage dashboard",
        "Care coordination workflow",
    ]
    assert signal.metadata["sponsor"] == "Example Medical Center"
    assert signal.metadata["enrollment_count"] == 240
    assert signal.metadata["start_date"] == "2026-01-15"
    assert signal.metadata["completion_date"] == "2027-06"
    assert signal.metadata["locations_count"] == 2
    assert signal.metadata["source_url"] == signal.url
    assert signal.metadata["search_query"] == "AI triage"


@pytest.mark.asyncio
async def test_missing_optional_protocol_fields_do_not_block_signal() -> None:
    adapter = ClinicalTrialsAdapter(config={"terms": ["remote monitoring"], "conditions": []})

    with patch("max.sources.clinical_trials.fetch_with_retry") as mock_fetch:
        mock_fetch.return_value = MagicMock(json=lambda: MISSING_OPTIONAL_RESPONSE)

        signals = await adapter.fetch(limit=5)

    assert len(signals) == 1
    signal = signals[0]
    assert signal.id == "clinical_trials:NCT06000002"
    assert signal.title == "Remote Monitoring Pilot"
    assert signal.content == "Remote Monitoring Pilot"
    assert signal.published_at is None
    assert signal.metadata["status"] is None
    assert signal.metadata["phases"] == []
    assert signal.metadata["conditions"] == []
    assert signal.metadata["interventions"] == []
    assert signal.metadata["sponsor"] is None
    assert signal.metadata["enrollment_count"] is None
    assert signal.metadata["locations_count"] == 0


@pytest.mark.asyncio
async def test_fetch_uses_configured_conditions_and_intervention_terms() -> None:
    adapter = ClinicalTrialsAdapter(
        config={
            "terms": [],
            "conditions": ["hypertension"],
            "intervention_terms": ["ambient AI"],
        }
    )

    with patch("max.sources.clinical_trials.fetch_with_retry") as mock_fetch:
        mock_fetch.return_value = MagicMock(json=lambda: {"studies": []})

        signals = await adapter.fetch(limit=3)

    assert signals == []
    assert mock_fetch.call_count == 2
    assert mock_fetch.call_args_list[0].kwargs["params"] == {
        "query.cond": "hypertension",
        "pageSize": 3,
        "format": "json",
    }
    assert mock_fetch.call_args_list[1].kwargs["params"] == {
        "query.intr": "ambient AI",
        "pageSize": 3,
        "format": "json",
    }


@pytest.mark.asyncio
async def test_deduplicates_by_nct_id() -> None:
    adapter = ClinicalTrialsAdapter(config={"terms": ["decision support"], "conditions": []})

    with patch("max.sources.clinical_trials.fetch_with_retry") as mock_fetch:
        mock_fetch.return_value = MagicMock(json=lambda: DEDUP_RESPONSE)

        signals = await adapter.fetch(limit=10)

    assert len(signals) == 1
    assert signals[0].id == "clinical_trials:NCT06000003"
    assert signals[0].metadata["nct_id"] == "NCT06000003"
    assert signals[0].title == "Clinical Decision Support Study"


@pytest.mark.asyncio
async def test_respects_limit_across_queries() -> None:
    adapter = ClinicalTrialsAdapter(
        config={
            "terms": ["clinical workflow", "EHR automation"],
            "conditions": [],
            "max_results_per_query": 10,
        }
    )

    with patch("max.sources.clinical_trials.fetch_with_retry") as mock_fetch:
        mock_fetch.return_value = MagicMock(json=lambda: ACTIVE_RECRUITING_RESPONSE)

        signals = await adapter.fetch(limit=1)

    assert len(signals) == 1
    assert mock_fetch.call_count == 1
    assert mock_fetch.call_args.kwargs["params"]["pageSize"] == 1
