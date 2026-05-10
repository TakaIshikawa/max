"""Tests for developer survey import adapter — sentiment signal collection."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from max.imports.survey_adapter import (
    SurveyAdapter,
    _build_tags,
    _normalize_score,
    _safe_float,
    parse_csv_survey,
    parse_json_survey,
)
from max.types.signal import SignalSourceType


# ── Test Data ────────────────────────────────────────────────────────

SAMPLE_CSV = """\
language,rank,popularity,satisfaction,salary,respondents
Python,1,48.2,73.1,120000,50000
JavaScript,2,62.5,58.3,110000,55000
Rust,3,12.1,87.0,130000,8000
TypeScript,4,38.5,72.5,125000,30000
"""

SAMPLE_CSV_ALT_HEADERS = """\
tech,position,usage_pct,loved_pct,median_salary,responses
Go,1,15.0,65.0,140000,12000
Kotlin,2,10.5,70.2,115000,9000
"""

SAMPLE_JSON = """[
  {"language": "Python", "rank": 1, "popularity": 48.2, "satisfaction": 73.1, "salary": 120000, "respondents": 50000},
  {"language": "JavaScript", "rank": 2, "popularity": 62.5, "satisfaction": 58.3, "salary": 110000, "respondents": 55000},
  {"language": "Rust", "rank": 3, "popularity": 12.1, "satisfaction": 87.0, "salary": 130000, "respondents": 8000}
]"""

SAMPLE_JSON_WRAPPED = """{
  "results": [
    {"name": "Go", "rank": 1, "usage_pct": 15.0, "loved_pct": 65.0, "median_salary": 140000, "count": 12000}
  ]
}"""


# ── Unit tests: helpers ──────────────────────────────────────────────


def test_safe_float_normal() -> None:
    assert _safe_float("42.5") == 42.5


def test_safe_float_percent() -> None:
    assert _safe_float("73.1%") == 73.1


def test_safe_float_comma() -> None:
    assert _safe_float("1,200") == 1200.0


def test_safe_float_none() -> None:
    assert _safe_float(None) is None


def test_safe_float_invalid() -> None:
    assert _safe_float("not-a-number") is None


def test_normalize_score_middle() -> None:
    assert _normalize_score(50.0, max_val=100.0) == 0.5


def test_normalize_score_capped() -> None:
    assert _normalize_score(200.0, max_val=100.0) == 1.0


def test_normalize_score_none() -> None:
    assert _normalize_score(None) == 0.5


def test_build_tags_python() -> None:
    tags = _build_tags("Python", "stackoverflow", "language_ranking")
    assert "survey" in tags
    assert "python" in tags
    assert "stackoverflow" in tags
    assert "language_ranking" in tags


def test_build_tags_typescript() -> None:
    tags = _build_tags("TypeScript", "jetbrains", "satisfaction")
    assert "typescript" in tags
    assert "jetbrains" in tags


# ── Unit tests: CSV parsing ──────────────────────────────────────────


def test_parse_csv_basic() -> None:
    rows = parse_csv_survey(SAMPLE_CSV, survey_source="stackoverflow")
    assert len(rows) == 4
    assert rows[0]["language"] == "Python"
    assert rows[0]["rank"] == 1
    assert rows[0]["popularity"] == 48.2
    assert rows[0]["satisfaction"] == 73.1
    assert rows[0]["salary"] == 120000.0
    assert rows[0]["respondents"] == 50000


def test_parse_csv_alt_headers() -> None:
    rows = parse_csv_survey(SAMPLE_CSV_ALT_HEADERS, survey_source="jetbrains")
    assert len(rows) == 2
    assert rows[0]["language"] == "Go"
    assert rows[0]["rank"] == 1
    assert rows[0]["popularity"] == 15.0
    assert rows[0]["satisfaction"] == 65.0  # loved_pct column
    assert rows[0]["salary"] == 140000.0


def test_parse_csv_empty() -> None:
    rows = parse_csv_survey("", survey_source="test")
    assert rows == []


def test_parse_csv_no_language_column() -> None:
    csv_data = "name,count\nfoo,10\n"
    rows = parse_csv_survey(csv_data)
    assert rows == []


# ── Unit tests: JSON parsing ─────────────────────────────────────────


def test_parse_json_array() -> None:
    rows = parse_json_survey(SAMPLE_JSON, survey_source="stackoverflow")
    assert len(rows) == 3
    assert rows[0]["language"] == "Python"
    assert rows[0]["rank"] == 1
    assert rows[0]["popularity"] == 48.2
    assert rows[2]["language"] == "Rust"
    assert rows[2]["satisfaction"] == 87.0


def test_parse_json_wrapped() -> None:
    rows = parse_json_survey(SAMPLE_JSON_WRAPPED, survey_source="jetbrains")
    assert len(rows) == 1
    assert rows[0]["language"] == "Go"
    assert rows[0]["popularity"] == 15.0
    assert rows[0]["satisfaction"] == 65.0


def test_parse_json_invalid() -> None:
    rows = parse_json_survey("not json")
    assert rows == []


def test_parse_json_empty_array() -> None:
    rows = parse_json_survey("[]")
    assert rows == []


# ── Adapter property tests ───────────────────────────────────────────


def test_adapter_name() -> None:
    adapter = SurveyAdapter()
    assert adapter.name == "survey_import"


def test_adapter_source_type() -> None:
    adapter = SurveyAdapter()
    assert adapter.source_type == SignalSourceType.SURVEY.value


def test_adapter_default_survey_source() -> None:
    adapter = SurveyAdapter()
    assert adapter.survey_source == "survey"


def test_adapter_custom_survey_source() -> None:
    adapter = SurveyAdapter(config={"survey_source": "stackoverflow"})
    assert adapter.survey_source == "stackoverflow"


# ── Fetch tests with file parsing ────────────────────────────────────


@pytest.mark.asyncio
async def test_fetch_from_csv_file() -> None:
    with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
        f.write(SAMPLE_CSV)
        f.flush()
        path = f.name

    adapter = SurveyAdapter(config={
        "files": [path],
        "survey_source": "stackoverflow",
    })
    signals = await adapter.fetch(limit=10)

    assert len(signals) == 4
    sig = signals[0]
    assert sig.source_type == SignalSourceType.SURVEY
    assert sig.source_adapter == "survey_import"
    assert "Python" in sig.title
    assert sig.metadata["language"] == "Python"
    assert sig.metadata["rank"] == 1
    assert sig.metadata["popularity"] == 48.2
    assert sig.metadata["satisfaction"] == 73.1
    assert sig.metadata["salary"] == 120000.0
    assert sig.metadata["respondents"] == 50000

    Path(path).unlink()


@pytest.mark.asyncio
async def test_fetch_from_json_file() -> None:
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        f.write(SAMPLE_JSON)
        f.flush()
        path = f.name

    adapter = SurveyAdapter(config={
        "files": [path],
        "survey_source": "jetbrains",
    })
    signals = await adapter.fetch(limit=10)

    assert len(signals) == 3
    assert signals[2].metadata["language"] == "Rust"
    assert signals[2].metadata["satisfaction"] == 87.0

    Path(path).unlink()


@pytest.mark.asyncio
async def test_fetch_from_inline_data() -> None:
    adapter = SurveyAdapter(config={
        "survey_source": "custom",
        "data": [
            {"language": "Python", "rank": 1, "popularity": 50.0, "satisfaction": 80.0},
            {"language": "Go", "rank": 2, "popularity": 20.0, "salary": 140000},
        ],
    })
    signals = await adapter.fetch(limit=10)

    assert len(signals) == 2
    assert signals[0].metadata["language"] == "Python"
    assert signals[1].metadata["language"] == "Go"
    assert signals[1].metadata["salary"] == 140000.0


@pytest.mark.asyncio
async def test_fetch_respects_limit() -> None:
    adapter = SurveyAdapter(config={
        "data": [
            {"language": "Python", "rank": 1},
            {"language": "Go", "rank": 2},
            {"language": "Rust", "rank": 3},
        ],
    })
    signals = await adapter.fetch(limit=2)
    assert len(signals) == 2


@pytest.mark.asyncio
async def test_fetch_deduplicates() -> None:
    adapter = SurveyAdapter(config={
        "data": [
            {"language": "Python", "rank": 1},
            {"language": "Python", "rank": 1},
        ],
    })
    signals = await adapter.fetch(limit=10)
    assert len(signals) == 1


@pytest.mark.asyncio
async def test_fetch_handles_missing_file() -> None:
    adapter = SurveyAdapter(config={
        "files": ["/nonexistent/survey.csv"],
    })
    signals = await adapter.fetch(limit=10)
    assert signals == []


@pytest.mark.asyncio
async def test_fetch_credibility_based_on_respondents() -> None:
    adapter = SurveyAdapter(config={
        "data": [
            {"language": "Python", "rank": 1, "respondents": 100000},
        ],
    })
    signals = await adapter.fetch(limit=10)
    assert signals[0].credibility == 1.0


@pytest.mark.asyncio
async def test_fetch_normalizes_across_formats() -> None:
    """Verify CSV and JSON produce consistent signal structure."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
        f.write("language,rank,popularity\nPython,1,48.2\n")
        csv_path = f.name

    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        f.write('[{"language": "Python", "rank": 1, "popularity": 48.2}]')
        json_path = f.name

    csv_adapter = SurveyAdapter(config={"files": [csv_path], "survey_source": "s1"})
    json_adapter = SurveyAdapter(config={"files": [json_path], "survey_source": "s2"})

    csv_signals = await csv_adapter.fetch(limit=10)
    json_signals = await json_adapter.fetch(limit=10)

    assert csv_signals[0].metadata["language"] == json_signals[0].metadata["language"]
    assert csv_signals[0].metadata["rank"] == json_signals[0].metadata["rank"]
    assert csv_signals[0].metadata["popularity"] == json_signals[0].metadata["popularity"]

    Path(csv_path).unlink()
    Path(json_path).unlink()
