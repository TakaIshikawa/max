"""Comprehensive tests for PubMed source adapter."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from max.sources.base import (
    AdapterCircuitOpenError,
    AdapterFetchError,
    AdapterRateLimitError,
    SourceAdapter,
)
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

MOCK_ESEARCH_SINGLE = {
    "esearchresult": {
        "count": "1",
        "idlist": ["39002001"],
    },
}

MOCK_ESUMMARY_SINGLE = {
    "result": {
        "uids": ["39002001"],
        "39002001": {
            "uid": "39002001",
            "title": "Telemedicine in Primary Care",
            "fulljournalname": "Telemedicine and e-Health",
            "source": "Telemed e-Health",
            "pubdate": "2026 Mar 15",
            "authors": [
                {"name": "Garcia ML", "authtype": "Author"},
            ],
            "elocationid": "",
        },
    },
}

MOCK_ESUMMARY_NO_AUTHOR = {
    "result": {
        "uids": ["39003001"],
        "39003001": {
            "uid": "39003001",
            "title": "Anonymous Study on FHIR Interoperability",
            "fulljournalname": "Digital Health",
            "source": "Digit Health",
            "pubdate": "2026 Apr",
            "authors": [],
            "elocationid": "",
        },
    },
}


# ── Unit Tests: _journal_credibility ─────────────────────────────────


class TestJournalCredibility:
    def test_high_impact_nejm(self) -> None:
        assert _journal_credibility("The New England Journal of Medicine") == 0.9

    def test_high_impact_lancet(self) -> None:
        assert _journal_credibility("The Lancet") == 0.9

    def test_high_impact_jama(self) -> None:
        assert _journal_credibility("JAMA") == 0.9

    def test_high_impact_nature_medicine(self) -> None:
        assert _journal_credibility("Nature Medicine") == 0.9

    def test_high_impact_bmj(self) -> None:
        assert _journal_credibility("BMJ") == 0.9

    def test_high_impact_npj_digital(self) -> None:
        assert _journal_credibility("npj Digital Medicine") == 0.9

    def test_mid_impact_jamia(self) -> None:
        assert _journal_credibility("Journal of the American Medical Informatics Association") == 0.6

    def test_mid_impact_jmir(self) -> None:
        assert _journal_credibility("Journal of Medical Internet Research") == 0.6

    def test_mid_impact_telemedicine(self) -> None:
        assert _journal_credibility("Telemedicine and e-Health") == 0.6

    def test_mid_impact_digital_health(self) -> None:
        assert _journal_credibility("Digital Health") == 0.6

    def test_unknown_journal(self) -> None:
        assert _journal_credibility("Obscure Journal of Things") == 0.4

    def test_empty_string(self) -> None:
        assert _journal_credibility("") == 0.4

    def test_case_insensitive(self) -> None:
        assert _journal_credibility("the new england journal of medicine") == 0.9
        assert _journal_credibility("THE LANCET") == 0.9


# ── Unit Tests: _parse_date ──────────────────────────────────────────


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

    def test_empty_string(self) -> None:
        assert _parse_date("") is None

    def test_has_timezone(self) -> None:
        dt = _parse_date("2026 Apr 10")
        assert dt is not None
        assert dt.tzinfo is not None

    def test_whitespace_stripped(self) -> None:
        dt = _parse_date("  2026 Apr 10  ")
        assert dt is not None
        assert dt.year == 2026


# ── Unit Tests: _extract_tags ────────────────────────────────────────


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

    def test_ml_keyword(self) -> None:
        tags = _extract_tags("Machine learning for clinical prediction", [])
        assert "ml" in tags

    def test_deep_learning_keyword(self) -> None:
        tags = _extract_tags("Deep learning in radiology", [])
        assert "ml" in tags

    def test_fhir_keyword(self) -> None:
        tags = _extract_tags("FHIR-based interoperability", [])
        assert "fhir" in tags

    def test_telemedicine_keyword(self) -> None:
        tags = _extract_tags("Telemedicine outcomes review", [])
        assert "telemedicine" in tags

    def test_patient_safety_keyword(self) -> None:
        tags = _extract_tags("Patient safety in AI systems", [])
        assert "patient-safety" in tags

    def test_limits_to_10(self) -> None:
        mesh = [f"Term {i}" for i in range(15)]
        tags = _extract_tags("EHR FHIR telemedicine burnout AI", mesh)
        assert len(tags) <= 10

    def test_takes_first_8_mesh_terms(self) -> None:
        mesh = [f"Term{i}" for i in range(10)]
        tags = _extract_tags("title", mesh)
        assert "term8" not in tags
        assert "term9" not in tags


# ── Adapter Property Tests ───────────────────────────────────────────


class TestPubMedAdapterProperties:
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

    def test_inherits_from_source_adapter(self) -> None:
        assert isinstance(PubMedAdapter(), SourceAdapter)

    def test_no_config(self) -> None:
        a = PubMedAdapter()
        assert a._config == {}


# ── Adapter Fetch Tests ──────────────────────────────────────────────


class TestPubMedAdapterFetch:
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
        assert signals[0].source_type == SignalSourceType.SURVEY
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

        # NEJM -> high impact -> 0.9
        assert signals[0].credibility == pytest.approx(0.9)
        # JAMIA -> mid impact -> 0.6
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

        # query1: search -> summary, query2: search (PMIDs already seen -> skip summary)
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

    @pytest.mark.asyncio
    @patch("max.sources.pubmed._get_api_key", return_value=None)
    async def test_fetch_metadata_fields(self, _mock_key) -> None:
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

        meta = signals[0].metadata
        assert meta["pmid"] == "39001001"
        assert meta["journal"] == "The New England Journal of Medicine"
        assert meta["authors"] == ["Smith JA", "Jones BK"]
        assert meta["pub_date"] == "2026 Apr 10"
        assert "doi" in meta["doi"]
        assert meta["search_query"] == "test"

    @pytest.mark.asyncio
    @patch("max.sources.pubmed._get_api_key", return_value=None)
    async def test_fetch_published_at_parsed(self, _mock_key) -> None:
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

        assert signals[0].published_at is not None
        assert signals[0].published_at.year == 2026
        assert signals[0].published_at.month == 4
        assert signals[0].published_at.day == 10

    @pytest.mark.asyncio
    @patch("max.sources.pubmed._get_api_key", return_value=None)
    async def test_fetch_content_is_title(self, _mock_key) -> None:
        """ESummary doesn't include abstracts, so content = title."""
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

        assert signals[0].content == signals[0].title

    @pytest.mark.asyncio
    @patch("max.sources.pubmed._get_api_key", return_value=None)
    async def test_fetch_no_author(self, _mock_key) -> None:
        adapter = PubMedAdapter(config={"queries": ["test"]})

        mock_search_resp = MagicMock()
        mock_search_resp.json.return_value = {"esearchresult": {"idlist": ["39003001"]}}
        mock_search_resp.status_code = 200

        mock_summary_resp = MagicMock()
        mock_summary_resp.json.return_value = MOCK_ESUMMARY_NO_AUTHOR
        mock_summary_resp.status_code = 200

        with patch(
            "max.sources.pubmed.fetch_with_retry",
            new_callable=AsyncMock,
            side_effect=[mock_search_resp, mock_summary_resp],
        ):
            with patch("asyncio.sleep", new_callable=AsyncMock):
                signals = await adapter.fetch(limit=10)

        assert len(signals) == 1
        assert signals[0].author is None

    @pytest.mark.asyncio
    @patch("max.sources.pubmed._get_api_key", return_value=None)
    async def test_fetch_skips_non_dict_articles(self, _mock_key) -> None:
        """Adapter skips PMIDs where the result entry is not a dict."""
        adapter = PubMedAdapter(config={"queries": ["test"]})

        mock_search_resp = MagicMock()
        mock_search_resp.json.return_value = {"esearchresult": {"idlist": ["39004001"]}}
        mock_search_resp.status_code = 200

        mock_summary_resp = MagicMock()
        mock_summary_resp.json.return_value = {"result": {"uids": ["39004001"], "39004001": "invalid"}}
        mock_summary_resp.status_code = 200

        with patch(
            "max.sources.pubmed.fetch_with_retry",
            new_callable=AsyncMock,
            side_effect=[mock_search_resp, mock_summary_resp],
        ):
            with patch("asyncio.sleep", new_callable=AsyncMock):
                signals = await adapter.fetch(limit=10)

        assert signals == []

    @pytest.mark.asyncio
    @patch("max.sources.pubmed._get_api_key", return_value=None)
    async def test_fetch_url_format(self, _mock_key) -> None:
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

        assert signals[0].url == "https://pubmed.ncbi.nlm.nih.gov/39001001/"
        assert signals[1].url == "https://pubmed.ncbi.nlm.nih.gov/39001002/"

    @pytest.mark.asyncio
    @patch("max.sources.pubmed._get_api_key", return_value=None)
    async def test_fetch_journal_fallback_to_source(self, _mock_key) -> None:
        """Uses 'source' field when 'fulljournalname' is missing."""
        adapter = PubMedAdapter(config={"queries": ["test"]})

        mock_search_resp = MagicMock()
        mock_search_resp.json.return_value = {"esearchresult": {"idlist": ["39005001"]}}
        mock_search_resp.status_code = 200

        mock_summary_resp = MagicMock()
        mock_summary_resp.json.return_value = {
            "result": {
                "uids": ["39005001"],
                "39005001": {
                    "uid": "39005001",
                    "title": "Test Article",
                    "source": "Some Journal",
                    "pubdate": "2026",
                    "authors": [],
                    "elocationid": "",
                },
            },
        }
        mock_summary_resp.status_code = 200

        with patch(
            "max.sources.pubmed.fetch_with_retry",
            new_callable=AsyncMock,
            side_effect=[mock_search_resp, mock_summary_resp],
        ):
            with patch("asyncio.sleep", new_callable=AsyncMock):
                signals = await adapter.fetch(limit=10)

        assert signals[0].metadata["journal"] == "Some Journal"

    @pytest.mark.asyncio
    @patch("max.sources.pubmed._get_api_key", return_value="key123")
    async def test_fetch_passes_api_key_to_both_steps(self, _mock_key) -> None:
        """API key should be passed to both esearch and esummary requests."""
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
        ) as mock_fetch:
            with patch("asyncio.sleep", new_callable=AsyncMock):
                await adapter.fetch(limit=10)

        # Both calls should include the api_key
        for call in mock_fetch.call_args_list:
            params = call.kwargs.get("params") or call[1].get("params", {})
            assert params.get("api_key") == "key123"


# ── Error Handling Tests ─────────────────────────────────────────────


class TestPubMedAdapterErrors:
    @pytest.mark.asyncio
    @patch("max.sources.pubmed._get_api_key", return_value=None)
    async def test_fetch_continues_on_search_error(self, _mock_key) -> None:
        """Adapter continues with next query when search fails."""
        adapter = PubMedAdapter(config={"queries": ["bad_query", "good_query"]})

        mock_search_good = MagicMock()
        mock_search_good.json.return_value = MOCK_ESEARCH_SINGLE
        mock_search_good.status_code = 200

        mock_summary_good = MagicMock()
        mock_summary_good.json.return_value = MOCK_ESUMMARY_SINGLE
        mock_summary_good.status_code = 200

        with patch(
            "max.sources.pubmed.fetch_with_retry",
            new_callable=AsyncMock,
            side_effect=[
                AdapterFetchError("pubmed", 500, "url"),
                mock_search_good,
                mock_summary_good,
            ],
        ):
            with patch("asyncio.sleep", new_callable=AsyncMock):
                signals = await adapter.fetch(limit=10)

        assert len(signals) == 1

    @pytest.mark.asyncio
    @patch("max.sources.pubmed._get_api_key", return_value=None)
    async def test_fetch_continues_on_summary_error(self, _mock_key) -> None:
        """Adapter continues with next query when summary fetch fails."""
        adapter = PubMedAdapter(config={"queries": ["q1", "q2"]})

        mock_search_resp = MagicMock()
        mock_search_resp.json.return_value = MOCK_ESEARCH_SINGLE
        mock_search_resp.status_code = 200

        mock_search_2 = MagicMock()
        mock_search_2.json.return_value = {"esearchresult": {"idlist": ["39009001"]}}
        mock_search_2.status_code = 200

        mock_summary_2 = MagicMock()
        mock_summary_2.json.return_value = {
            "result": {
                "uids": ["39009001"],
                "39009001": {
                    "uid": "39009001",
                    "title": "Recovered Article",
                    "fulljournalname": "BMJ",
                    "source": "BMJ",
                    "pubdate": "2026 Apr",
                    "authors": [{"name": "Test A"}],
                    "elocationid": "",
                },
            },
        }
        mock_summary_2.status_code = 200

        with patch(
            "max.sources.pubmed.fetch_with_retry",
            new_callable=AsyncMock,
            side_effect=[
                mock_search_resp,
                AdapterFetchError("pubmed", 503, "url"),
                mock_search_2,
                mock_summary_2,
            ],
        ):
            with patch("asyncio.sleep", new_callable=AsyncMock):
                signals = await adapter.fetch(limit=10)

        assert len(signals) == 1

    @pytest.mark.asyncio
    @patch("max.sources.pubmed._get_api_key", return_value=None)
    async def test_fetch_continues_on_rate_limit(self, _mock_key) -> None:
        adapter = PubMedAdapter(config={"queries": ["q1", "q2"]})

        mock_search_good = MagicMock()
        mock_search_good.json.return_value = MOCK_ESEARCH_SINGLE
        mock_search_good.status_code = 200

        mock_summary_good = MagicMock()
        mock_summary_good.json.return_value = MOCK_ESUMMARY_SINGLE
        mock_summary_good.status_code = 200

        with patch(
            "max.sources.pubmed.fetch_with_retry",
            new_callable=AsyncMock,
            side_effect=[
                AdapterRateLimitError("pubmed", "url"),
                mock_search_good,
                mock_summary_good,
            ],
        ):
            with patch("asyncio.sleep", new_callable=AsyncMock):
                signals = await adapter.fetch(limit=10)

        assert len(signals) == 1

    @pytest.mark.asyncio
    @patch("max.sources.pubmed._get_api_key", return_value=None)
    async def test_fetch_continues_on_circuit_open(self, _mock_key) -> None:
        adapter = PubMedAdapter(config={"queries": ["q1", "q2"]})

        mock_search_good = MagicMock()
        mock_search_good.json.return_value = MOCK_ESEARCH_SINGLE
        mock_search_good.status_code = 200

        mock_summary_good = MagicMock()
        mock_summary_good.json.return_value = MOCK_ESUMMARY_SINGLE
        mock_summary_good.status_code = 200

        with patch(
            "max.sources.pubmed.fetch_with_retry",
            new_callable=AsyncMock,
            side_effect=[
                AdapterCircuitOpenError("pubmed", retry_after=300.0),
                mock_search_good,
                mock_summary_good,
            ],
        ):
            with patch("asyncio.sleep", new_callable=AsyncMock):
                signals = await adapter.fetch(limit=10)

        assert len(signals) == 1

    @pytest.mark.asyncio
    @patch("max.sources.pubmed._get_api_key", return_value=None)
    async def test_fetch_continues_on_timeout(self, _mock_key) -> None:
        adapter = PubMedAdapter(config={"queries": ["q1", "q2"]})

        mock_search_good = MagicMock()
        mock_search_good.json.return_value = MOCK_ESEARCH_SINGLE
        mock_search_good.status_code = 200

        mock_summary_good = MagicMock()
        mock_summary_good.json.return_value = MOCK_ESUMMARY_SINGLE
        mock_summary_good.status_code = 200

        with patch(
            "max.sources.pubmed.fetch_with_retry",
            new_callable=AsyncMock,
            side_effect=[
                httpx.TimeoutException("timeout"),
                mock_search_good,
                mock_summary_good,
            ],
        ):
            with patch("asyncio.sleep", new_callable=AsyncMock):
                signals = await adapter.fetch(limit=10)

        assert len(signals) == 1

    @pytest.mark.asyncio
    @patch("max.sources.pubmed._get_api_key", return_value=None)
    async def test_fetch_all_queries_fail_returns_empty(self, _mock_key) -> None:
        adapter = PubMedAdapter(config={"queries": ["q1"]})

        with patch(
            "max.sources.pubmed.fetch_with_retry",
            new_callable=AsyncMock,
            side_effect=AdapterFetchError("pubmed", 503, "url"),
        ):
            signals = await adapter.fetch(limit=10)

        assert signals == []

    @pytest.mark.asyncio
    @patch("max.sources.pubmed._get_api_key", return_value=None)
    async def test_fetch_sleeps_between_queries(self, _mock_key) -> None:
        adapter = PubMedAdapter(config={"queries": ["q1", "q2"]})

        mock_search_resp = MagicMock()
        mock_search_resp.json.return_value = MOCK_ESEARCH_EMPTY
        mock_search_resp.status_code = 200

        with patch(
            "max.sources.pubmed.fetch_with_retry",
            new_callable=AsyncMock,
            return_value=mock_search_resp,
        ):
            with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
                await adapter.fetch(limit=10)

        # Should sleep between queries (0.5s rate-limit courtesy)
        mock_sleep.assert_called_with(0.5)


# ── API Key Resolution Tests ────────────────────────────────────────


class TestGetApiKey:
    @patch.dict("os.environ", {"NCBI_API_KEY": "env-key-123"})
    def test_from_env(self) -> None:
        from max.sources.pubmed import _get_api_key
        assert _get_api_key() == "env-key-123"

    @patch.dict("os.environ", {}, clear=True)
    @patch("subprocess.run")
    def test_from_vault(self, mock_run) -> None:
        from max.sources.pubmed import _get_api_key
        mock_run.return_value = MagicMock(returncode=0, stdout="vault-key-456\n")
        assert _get_api_key() == "vault-key-456"

    @patch.dict("os.environ", {}, clear=True)
    @patch("subprocess.run")
    def test_vault_failure_returns_none(self, mock_run) -> None:
        from max.sources.pubmed import _get_api_key
        mock_run.return_value = MagicMock(returncode=1, stdout="")
        assert _get_api_key() is None

    @patch.dict("os.environ", {}, clear=True)
    @patch("subprocess.run", side_effect=FileNotFoundError("vault not found"))
    def test_vault_exception_returns_none(self, _mock_run) -> None:
        from max.sources.pubmed import _get_api_key
        assert _get_api_key() is None
