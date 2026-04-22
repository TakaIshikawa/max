"""Tests for PubMed source adapter."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from max.sources.pubmed import (
    PubMedAdapter,
    _extract_tags,
    _journal_credibility,
    _parse_date,
)
from max.types.signal import SignalSourceType


# ── Test Data ────────────────────────────────────────────────────────


MOCK_ESEARCH_RESPONSE = {
    "esearchresult": {
        "count": "2",
        "idlist": ["39001001", "39001002"],
    },
}

MOCK_ESUMMARY_RESPONSE = {
    "result": {
        "uids": ["39001001", "39001002"],
        "39001001": {
            "uid": "39001001",
            "title": "AI-Assisted Clinical Decision Support Reduces Diagnostic Errors",
            "fulljournalname": "The New England Journal of Medicine",
            "source": "N Engl J Med",
            "pubdate": "2026 Apr 10",
            "authors": [
                {"name": "Smith JA", "authtype": "Author"},
                {"name": "Jones BK", "authtype": "Author"},
            ],
            "elocationid": "doi: 10.1056/NEJMoa2604001",
        },
        "39001002": {
            "uid": "39001002",
            "title": "EHR Usability and Clinician Burnout: A Cross-Sectional Study",
            "fulljournalname": "Journal of the American Medical Informatics Association",
            "source": "J Am Med Inform Assoc",
            "pubdate": "2026 Apr 12",
            "authors": [
                {"name": "Brown CD", "authtype": "Author"},
            ],
            "elocationid": "doi: 10.1093/jamia/ocae123",
        },
    },
}

MOCK_ESEARCH_EMPTY = {
    "esearchresult": {
        "count": "0",
        "idlist": [],
    },
}


# ── Unit Tests ────────────────────────────────────────────────────────


class TestJournalCredibility:
    def test_high_impact_nejm(self) -> None:
        assert _journal_credibility("The New England Journal of Medicine") == 0.9

    def test_high_impact_lancet(self) -> None:
        assert _journal_credibility("The Lancet") == 0.9

    def test_high_impact_jama(self) -> None:
        assert _journal_credibility("JAMA") == 0.9

    def test_high_impact_nature_medicine(self) -> None:
        assert _journal_credibility("Nature Medicine") == 0.9

    def test_mid_impact_jamia(self) -> None:
        assert _journal_credibility("Journal of the American Medical Informatics Association") == 0.6

    def test_mid_impact_jmir(self) -> None:
        assert _journal_credibility("Journal of Medical Internet Research") == 0.6

    def test_unknown_journal(self) -> None:
        assert _journal_credibility("Obscure Journal of Things") == 0.4

    def test_empty_string(self) -> None:
        assert _journal_credibility("") == 0.4


class TestParseDate:
    def test_month_day_format(self) -> None:
        dt = _parse_date("2026 Apr 10")
        assert dt is not None
        assert dt.year == 2026
        assert dt.month == 4
        assert dt.day == 10

    def test_slash_format(self) -> None:
        dt = _parse_date("2026/04/15")
        assert dt is not None
        assert dt.year == 2026
        assert dt.month == 4

    def test_month_only(self) -> None:
        dt = _parse_date("2026 Apr")
        assert dt is not None
        assert dt.year == 2026
        assert dt.month == 4

    def test_year_only(self) -> None:
        dt = _parse_date("2026")
        assert dt is not None
        assert dt.year == 2026

    def test_invalid(self) -> None:
        assert _parse_date("not-a-date") is None


class TestExtractTags:
    def test_includes_mesh_terms(self) -> None:
        tags = _extract_tags("some title", ["Artificial Intelligence", "Electronic Health Records"])
        assert "artificial-intelligence" in tags
        assert "electronic-health-records" in tags

    def test_extracts_keywords_from_title(self) -> None:
        tags = _extract_tags("EHR usability and clinician burnout", [])
        assert "ehr" in tags
        assert "burnout" in tags

    def test_always_includes_pubmed(self) -> None:
        tags = _extract_tags("random title", [])
        assert "pubmed" in tags

    def test_ai_keyword(self) -> None:
        tags = _extract_tags("Artificial Intelligence in diagnosis", [])
        assert "ai" in tags

    def test_limits_to_10(self) -> None:
        mesh = [f"Term {i}" for i in range(15)]
        tags = _extract_tags("EHR FHIR telemedicine burnout AI", mesh)
        assert len(tags) <= 10


# ── Adapter Tests ────────────────────────────────────────────────────


class TestPubMedAdapter:
    def test_name(self) -> None:
        assert PubMedAdapter().name == "pubmed"

    def test_source_type(self) -> None:
        assert PubMedAdapter().source_type == SignalSourceType.SURVEY.value

    def test_config_defaults(self) -> None:
        a = PubMedAdapter()
        assert len(a.queries) > 0
        assert a.max_results_per_query == 10
        assert a.recent_days == 30

    def test_config_overrides(self) -> None:
        a = PubMedAdapter(config={
            "queries": ["custom query"],
            "max_results_per_query": 5,
            "recent_days": 60,
        })
        assert a.queries == ["custom query"]
        assert a.max_results_per_query == 5
        assert a.recent_days == 60

    @pytest.mark.asyncio
    @patch("max.sources.pubmed._get_api_key", return_value=None)
    async def test_fetch_parses_articles(self, _mock_key) -> None:
        adapter = PubMedAdapter(config={"queries": ["test query"]})

        mock_search_resp = MagicMock()
        mock_search_resp.json.return_value = MOCK_ESEARCH_RESPONSE
        mock_search_resp.status_code = 200

        mock_summary_resp = MagicMock()
        mock_summary_resp.json.return_value = MOCK_ESUMMARY_RESPONSE
        mock_summary_resp.status_code = 200

        with patch(
            "max.sources.pubmed.fetch_with_retry",
            new_callable=AsyncMock,
            side_effect=[mock_search_resp, mock_summary_resp],
        ):
            with patch("asyncio.sleep", new_callable=AsyncMock):
                signals = await adapter.fetch(limit=10)

        assert len(signals) == 2
        assert signals[0].source_adapter == "pubmed"
        assert "Clinical Decision Support" in signals[0].title
        assert signals[0].url == "https://pubmed.ncbi.nlm.nih.gov/39001001/"
        assert signals[0].author == "Smith JA"
        assert signals[0].metadata["pmid"] == "39001001"
        assert signals[0].metadata["journal"] == "The New England Journal of Medicine"

    @pytest.mark.asyncio
    @patch("max.sources.pubmed._get_api_key", return_value=None)
    async def test_fetch_credibility_from_journal(self, _mock_key) -> None:
        adapter = PubMedAdapter(config={"queries": ["test"]})

        mock_search_resp = MagicMock()
        mock_search_resp.json.return_value = MOCK_ESEARCH_RESPONSE
        mock_search_resp.status_code = 200

        mock_summary_resp = MagicMock()
        mock_summary_resp.json.return_value = MOCK_ESUMMARY_RESPONSE
        mock_summary_resp.status_code = 200

        with patch(
            "max.sources.pubmed.fetch_with_retry",
            new_callable=AsyncMock,
            side_effect=[mock_search_resp, mock_summary_resp],
        ):
            with patch("asyncio.sleep", new_callable=AsyncMock):
                signals = await adapter.fetch(limit=10)

        # NEJM → high impact → 0.9
        assert signals[0].credibility == pytest.approx(0.9)
        # JAMIA → mid impact → 0.6
        assert signals[1].credibility == pytest.approx(0.6)

    @pytest.mark.asyncio
    @patch("max.sources.pubmed._get_api_key", return_value=None)
    async def test_fetch_respects_limit(self, _mock_key) -> None:
        adapter = PubMedAdapter(config={"queries": ["test"]})

        mock_search_resp = MagicMock()
        mock_search_resp.json.return_value = MOCK_ESEARCH_RESPONSE
        mock_search_resp.status_code = 200

        mock_summary_resp = MagicMock()
        mock_summary_resp.json.return_value = MOCK_ESUMMARY_RESPONSE
        mock_summary_resp.status_code = 200

        with patch(
            "max.sources.pubmed.fetch_with_retry",
            new_callable=AsyncMock,
            side_effect=[mock_search_resp, mock_summary_resp],
        ):
            with patch("asyncio.sleep", new_callable=AsyncMock):
                signals = await adapter.fetch(limit=1)

        assert len(signals) == 1

    @pytest.mark.asyncio
    @patch("max.sources.pubmed._get_api_key", return_value=None)
    async def test_fetch_deduplicates_across_queries(self, _mock_key) -> None:
        adapter = PubMedAdapter(config={"queries": ["query1", "query2"]})

        mock_search_resp = MagicMock()
        mock_search_resp.json.return_value = MOCK_ESEARCH_RESPONSE
        mock_search_resp.status_code = 200

        mock_summary_resp = MagicMock()
        mock_summary_resp.json.return_value = MOCK_ESUMMARY_RESPONSE
        mock_summary_resp.status_code = 200

        # query1: search → summary, query2: search (PMIDs already seen → skip summary)
        with patch(
            "max.sources.pubmed.fetch_with_retry",
            new_callable=AsyncMock,
            side_effect=[mock_search_resp, mock_summary_resp, mock_search_resp],
        ):
            with patch("asyncio.sleep", new_callable=AsyncMock):
                signals = await adapter.fetch(limit=10)

        # Same PMIDs from both queries, dedup should yield only 2
        assert len(signals) == 2

    @pytest.mark.asyncio
    @patch("max.sources.pubmed._get_api_key", return_value=None)
    async def test_fetch_handles_empty_search(self, _mock_key) -> None:
        adapter = PubMedAdapter(config={"queries": ["no results query"]})

        mock_search_resp = MagicMock()
        mock_search_resp.json.return_value = MOCK_ESEARCH_EMPTY
        mock_search_resp.status_code = 200

        with patch(
            "max.sources.pubmed.fetch_with_retry",
            new_callable=AsyncMock,
            return_value=mock_search_resp,
        ):
            signals = await adapter.fetch(limit=10)

        assert signals == []

    @pytest.mark.asyncio
    @patch("max.sources.pubmed._get_api_key", return_value="test-ncbi-key")
    async def test_fetch_passes_api_key(self, _mock_key) -> None:
        adapter = PubMedAdapter(config={"queries": ["test"]})

        mock_search_resp = MagicMock()
        mock_search_resp.json.return_value = MOCK_ESEARCH_EMPTY
        mock_search_resp.status_code = 200

        with patch(
            "max.sources.pubmed.fetch_with_retry",
            new_callable=AsyncMock,
            return_value=mock_search_resp,
        ) as mock_fetch:
            await adapter.fetch(limit=5)

        # API key should be in search params
        call_kwargs = mock_fetch.call_args
        params = call_kwargs.kwargs.get("params") or call_kwargs[1].get("params", {})
        assert params.get("api_key") == "test-ncbi-key"
