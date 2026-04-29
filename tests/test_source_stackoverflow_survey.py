"""Tests for Stack Overflow survey CSV adapter."""

from __future__ import annotations

import pytest

from max.sources.errors import SourceParseError
from max.sources.stackoverflow_survey import StackOverflowSurveyAdapter
from max.types.signal import SignalSourceType


def test_config_list_values_are_normalized_for_scalar_blank_list_and_none():
    adapter = StackOverflowSurveyAdapter(
        config={
            "survey_urls": "https://example.com/survey.csv",
            "local_paths": ["", "  ", "/tmp/survey.csv"],
            "question_filters": None,
        }
    )

    assert adapter.survey_urls == ["https://example.com/survey.csv"]
    assert adapter.local_paths == ["/tmp/survey.csv"]
    assert adapter.question_filters == []


def test_non_iterable_scalar_config_values_are_ignored():
    adapter = StackOverflowSurveyAdapter(
        config={
            "survey_urls": 42,
            "local_paths": object(),
            "question_filters": False,
        }
    )

    assert adapter.survey_urls == []
    assert adapter.local_paths == []
    assert adapter.question_filters == []


@pytest.mark.asyncio
async def test_respondent_rows_are_aggregated_into_market_signals(tmp_path):
    csv_path = tmp_path / "stack-overflow-developer-survey-2024.csv"
    csv_path.write_text(
        "DevType,LanguageHaveWorkedWith,Country\n"
        "\"Developer, back-end\",Python;JavaScript,United States\n"
        "\"Developer, back-end\",Python,Canada\n"
        "\"Developer, front-end\",JavaScript,Germany\n",
        encoding="utf-8",
    )
    adapter = StackOverflowSurveyAdapter(
        config={
            "local_paths": [str(csv_path)],
            "question_filters": ["LanguageHaveWorkedWith"],
        }
    )

    signals = await adapter.fetch(limit=10)

    by_answer = {signal.metadata["answer"]: signal for signal in signals}
    assert set(by_answer) == {"Python", "JavaScript"}
    assert by_answer["Python"].source_type == SignalSourceType.SURVEY
    assert by_answer["Python"].source_adapter == "stackoverflow_survey"
    assert by_answer["Python"].metadata == {
        "year": 2024,
        "question": "LanguageHaveWorkedWith",
        "answer": "Python",
        "percent": 66.67,
        "sample_size": 3,
        "signal_role": "market",
    }
    assert by_answer["Python"].id.startswith("stackoverflow_survey:")
    assert by_answer["Python"].id == StackOverflowSurveyAdapter(
        config={"local_paths": [str(csv_path)], "question_filters": ["LanguageHaveWorkedWith"]}
    )._build_signal(
        source_url=str(csv_path),
        year=2024,
        question="LanguageHaveWorkedWith",
        answer="Python",
        percent=66.67,
        sample_size=3,
    ).id


@pytest.mark.asyncio
async def test_question_filters_and_min_percent_remove_irrelevant_rows(tmp_path):
    csv_path = tmp_path / "survey.csv"
    csv_path.write_text(
        "Year,Question,Answer,Percent,Sample Size\n"
        "2023,Developer type,Back-end developer,52.5,90000\n"
        "2023,Developer type,Data scientist,7.5,90000\n"
        "2023,Database,PostgreSQL,45.0,70000\n",
        encoding="utf-8",
    )
    adapter = StackOverflowSurveyAdapter(
        config={
            "local_paths": [str(csv_path)],
            "question_filters": ["developer"],
            "min_percent": 10,
        }
    )

    signals = await adapter.fetch(limit=10)

    assert len(signals) == 1
    signal = signals[0]
    assert signal.title == "52.5% of 2023 survey respondents: Back-end developer"
    assert signal.metadata["question"] == "Developer type"
    assert signal.metadata["answer"] == "Back-end developer"
    assert signal.metadata["percent"] == 52.5
    assert signal.metadata["sample_size"] == 90000
    assert signal.metadata["signal_role"] == "market"


@pytest.mark.asyncio
async def test_max_rows_caps_returned_signals(tmp_path):
    csv_path = tmp_path / "stack-overflow-developer-survey-2022.csv"
    csv_path.write_text(
        "DevType\n"
        "\"Developer, back-end\"\n"
        "\"Developer, front-end\"\n"
        "\"Developer, full-stack\"\n",
        encoding="utf-8",
    )
    adapter = StackOverflowSurveyAdapter(
        config={"local_paths": [str(csv_path)], "question_filters": ["DevType"], "max_rows": 2}
    )

    signals = await adapter.fetch(limit=30)

    assert len(signals) == 2


@pytest.mark.asyncio
async def test_unsupported_csv_raises_clear_source_parse_error(tmp_path):
    csv_path = tmp_path / "bad.csv"
    csv_path.write_text("Year\n2024\n", encoding="utf-8")
    adapter = StackOverflowSurveyAdapter(config={"local_paths": [str(csv_path)]})

    with pytest.raises(SourceParseError, match="Unsupported survey CSV"):
        await adapter.fetch(limit=10)


@pytest.mark.asyncio
async def test_missing_local_file_raises_clear_source_parse_error(tmp_path):
    adapter = StackOverflowSurveyAdapter(config={"local_paths": [str(tmp_path / "missing.csv")]})

    with pytest.raises(SourceParseError, match="Unable to read survey CSV file"):
        await adapter.fetch(limit=10)
