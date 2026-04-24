"""Tests for the Federal Register healthcare source adapter."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest

from max.sources.federal_register_healthcare import (
    DEFAULT_BASE_URL,
    DOCUMENTS_ENDPOINT,
    FederalRegisterHealthcareAdapter,
)
from max.types.signal import SignalSourceType


def _response(payload: dict) -> MagicMock:
    response = MagicMock()
    response.json.return_value = payload
    return response


def _date(days_ago: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=days_ago)).date().isoformat()


def _document(
    *,
    number: str,
    title: str,
    document_type: str = "Rule",
    publication_date: str | None = None,
    abstract: str = "Updates healthcare compliance workflows for patient access.",
    agencies: list[dict] | None = None,
) -> dict:
    return {
        "document_number": number,
        "title": title,
        "type": document_type,
        "abstract": abstract,
        "html_url": f"https://www.federalregister.gov/documents/{number}",
        "publication_date": publication_date or _date(3),
        "effective_on": _date(30),
        "comment_url": f"https://www.regulations.gov/commenton/{number}",
        "docket_ids": [f"HHS-{number}"],
        "citation": "91 FR 12345",
        "agencies": agencies
        or [
            {
                "name": "Centers for Medicare & Medicaid Services",
                "slug": "centers-for-medicare-medicaid-services",
            }
        ],
    }


def test_federal_register_healthcare_adapter_properties() -> None:
    adapter = FederalRegisterHealthcareAdapter()

    assert adapter.name == "federal_register_healthcare"
    assert adapter.source_type == SignalSourceType.ROADMAP.value
    assert adapter.base_url == DEFAULT_BASE_URL
    assert "centers-for-medicare-medicaid-services" in adapter.agencies
    assert "food-and-drug-administration" in adapter.agencies
    assert "health-and-human-services-department" in adapter.agencies
    assert "health-and-human-services-department-office-for-civil-rights" in adapter.agencies
    assert adapter.document_types == ["RULE", "PRORULE", "NOTICE"]
    assert adapter.max_age_days == 90


def test_federal_register_healthcare_adapter_custom_config() -> None:
    adapter = FederalRegisterHealthcareAdapter(
        config={
            "base_url": "https://federalregister.example.test/api/v1/",
            "agencies": ["food-and-drug-administration"],
            "topics": ["medical-devices"],
            "search_terms": ["interoperability"],
            "document_types": ["proposed rule"],
            "max_age_days": "14",
        }
    )

    assert adapter.base_url == "https://federalregister.example.test/api/v1"
    assert adapter.agencies == ["food-and-drug-administration"]
    assert adapter.topics == ["medical-devices"]
    assert adapter.search_terms == ["interoperability"]
    assert adapter.document_types == ["PRORULE"]
    assert adapter.max_age_days == 14


@pytest.mark.asyncio
async def test_federal_register_healthcare_fetch_emits_normalized_signals() -> None:
    adapter = FederalRegisterHealthcareAdapter(
        config={
            "search_terms": ["interoperability"],
            "document_types": ["RULE", "NOTICE"],
            "topics": ["health-care"],
            "max_age_days": 30,
        }
    )
    payload = {
        "results": [
            _document(
                number="2026-00123",
                title="Medicare Program; Interoperability and Prior Authorization Final Rule",
                document_type="Rule",
            ),
            _document(
                number="2026-00456",
                title="Guidance for Patient Access API Interoperability",
                document_type="Notice",
                abstract="FDA announces guidance for patient access API interoperability compliance.",
                agencies=[{"name": "Food and Drug Administration"}],
            ),
        ]
    }

    with patch("max.sources.federal_register_healthcare.fetch_with_retry") as mock_fetch:
        mock_fetch.return_value = _response(payload)

        signals = await adapter.fetch(limit=10)

    assert len(signals) == 2
    assert mock_fetch.call_args.args[0] == f"{DEFAULT_BASE_URL}{DOCUMENTS_ENDPOINT}"
    params = mock_fetch.call_args.kwargs["params"]
    assert ("conditions[term]", "interoperability") in params
    assert ("conditions[topics][]", "health-care") in params
    assert ("conditions[type][]", "RULE") in params
    assert ("conditions[type][]", "NOTICE") in params
    assert any(key == "conditions[publication_date][gte]" for key, _ in params)

    first = signals[0]
    assert first.id.startswith("federal_register_healthcare:")
    assert first.source_type == SignalSourceType.ROADMAP
    assert first.source_adapter == "federal_register_healthcare"
    assert first.title == "Medicare Program; Interoperability and Prior Authorization Final Rule"
    assert first.url == "https://www.federalregister.gov/documents/2026-00123"
    assert first.author == "Centers for Medicare & Medicaid Services"
    assert first.published_at is not None
    assert first.metadata["agency_names"] == ["Centers for Medicare & Medicaid Services"]
    assert first.metadata["document_type"] == "Rule"
    assert first.metadata["publication_date"] == payload["results"][0]["publication_date"]
    assert first.metadata["effective_on"] == payload["results"][0]["effective_on"]
    assert first.metadata["comment_url"].endswith("/2026-00123")
    assert first.metadata["docket_id"] == "HHS-2026-00123"
    assert first.metadata["citation"] == "91 FR 12345"
    assert first.metadata["signal_role"] == "problem"

    second = signals[1]
    assert second.source_type == SignalSourceType.REPORT
    assert "guidance" in second.tags


@pytest.mark.asyncio
async def test_federal_register_healthcare_filters_search_terms_document_types_and_age() -> None:
    adapter = FederalRegisterHealthcareAdapter(
        config={
            "search_terms": ["billing"],
            "document_types": ["NOTICE"],
            "max_age_days": 10,
        }
    )
    payload = {
        "results": [
            _document(
                number="2026-10000",
                title="Billing transparency notice",
                document_type="Notice",
                abstract="Healthcare billing transparency changes.",
                publication_date=_date(1),
            ),
            _document(
                number="2026-10001",
                title="Billing transparency rule",
                document_type="Rule",
                abstract="Healthcare billing transparency changes.",
                publication_date=_date(1),
            ),
            _document(
                number="2026-10002",
                title="Patient access notice",
                document_type="Notice",
                abstract="Patient access updates.",
                publication_date=_date(1),
            ),
            _document(
                number="2026-10003",
                title="Billing archive notice",
                document_type="Notice",
                abstract="Healthcare billing transparency changes.",
                publication_date=_date(45),
            ),
        ]
    }

    with patch("max.sources.federal_register_healthcare.fetch_with_retry") as mock_fetch:
        mock_fetch.return_value = _response(payload)

        signals = await adapter.fetch(limit=10)

    assert [signal.metadata["document_number"] for signal in signals] == ["2026-10000"]


@pytest.mark.asyncio
async def test_federal_register_healthcare_missing_optional_fields_do_not_crash() -> None:
    adapter = FederalRegisterHealthcareAdapter(config={"search_terms": ["patient"], "max_age_days": None})
    payload = {
        "results": [
            {
                "document_number": "2026-20000",
                "title": "Patient access policy statement",
                "type": "Notice",
                "html_url": "https://www.federalregister.gov/documents/2026-20000",
                "abstract": "A policy statement for patient access.",
            }
        ]
    }

    with patch("max.sources.federal_register_healthcare.fetch_with_retry") as mock_fetch:
        mock_fetch.return_value = _response(payload)

        signals = await adapter.fetch(limit=5)

    assert len(signals) == 1
    signal = signals[0]
    assert signal.source_type == SignalSourceType.REPORT
    assert signal.metadata["agency_names"] == []
    assert signal.metadata["effective_on"] is None
    assert signal.metadata["comment_url"] is None
    assert signal.metadata["docket_id"] is None
    assert signal.metadata["citation"] is None
    assert signal.metadata["signal_role"] == "problem"


@pytest.mark.asyncio
async def test_federal_register_healthcare_returns_empty_for_empty_or_malformed_results() -> None:
    adapter = FederalRegisterHealthcareAdapter()

    with patch("max.sources.federal_register_healthcare.fetch_with_retry") as mock_fetch:
        mock_fetch.return_value = _response({"results": []})
        assert await adapter.fetch(limit=5) == []

        mock_fetch.return_value = _response({"results": "not-a-list"})
        assert await adapter.fetch(limit=5) == []


@pytest.mark.asyncio
async def test_federal_register_healthcare_signal_ids_are_deterministic() -> None:
    adapter = FederalRegisterHealthcareAdapter(config={"search_terms": ["patient"]})
    payload = {
        "results": [
            _document(
                number="2026-30000",
                title="Patient access final rule",
                abstract="Patient access compliance changes.",
            )
        ]
    }

    with patch("max.sources.federal_register_healthcare.fetch_with_retry") as mock_fetch:
        mock_fetch.return_value = _response(payload)
        first = await adapter.fetch(limit=5)
        second = await adapter.fetch(limit=5)

    assert [signal.id for signal in first] == [signal.id for signal in second]
