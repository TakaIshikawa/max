"""Tests for JetBrains Developer Ecosystem survey CSV adapter."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from max.sources.errors import SourceParseError
from max.sources.jetbrains_survey import JetBrainsSurveyAdapter
from max.types.signal import SignalSourceType


@pytest.mark.asyncio
async def test_local_aggregate_rows_return_deterministic_survey_signals(tmp_path) -> None:
    csv_path = tmp_path / "jetbrains-developer-ecosystem-2024.csv"
    csv_path.write_text(
        "Question,Answer,Percent,Sample Size\n"
        "Which programming languages have you used in the last 12 months?,Python,55.2,26000\n"
        "Which programming languages have you used in the last 12 months?,Kotlin,36.4,26000\n",
        encoding="utf-8",
    )
    adapter = JetBrainsSurveyAdapter(config={"local_paths": [str(csv_path)]})

    signals = await adapter.fetch(limit=10)

    assert len(signals) == 2
    first = signals[0]
    assert first.source_type == SignalSourceType.SURVEY
    assert first.source_adapter == "jetbrains_survey"
    assert first.title == (
        "JetBrains 2024 survey: Which programming languages have you used in the last "
        "12 months? - Python (55.2%)"
    )
    assert first.credibility == 0.9
    assert first.metadata == {
        "question": "Which programming languages have you used in the last 12 months?",
        "answer": "Python",
        "percent": 55.2,
        "sample_size": 26000,
        "year": 2024,
        "source_url": first.url,
        "signal_role": "market",
    }
    assert first.id == JetBrainsSurveyAdapter(config={"local_paths": [str(csv_path)]})._build_signal(
        source_url=str(csv_path),
        year=2024,
        question="Which programming languages have you used in the last 12 months?",
        answer="Python",
        percent=55.2,
        sample_size=26000,
    ).id


@pytest.mark.asyncio
async def test_question_filters_and_min_percent_remove_irrelevant_rows(tmp_path) -> None:
    csv_path = tmp_path / "jetbrains-survey.csv"
    csv_path.write_text(
        "Year,Survey Question,Response,Percentage,Respondents\n"
        "2025,What are your biggest challenges with AI coding tools?,Lack of trust,34.5,12000\n"
        "2025,What are your biggest challenges with AI coding tools?,Setup difficulty,8.5,12000\n"
        "2025,Which IDE do you use?,IntelliJ IDEA,42.0,11000\n",
        encoding="utf-8",
    )
    adapter = JetBrainsSurveyAdapter(
        config={
            "local_paths": [str(csv_path)],
            "question_filters": ["AI coding"],
            "min_percent": 10,
        }
    )

    signals = await adapter.fetch(limit=10)

    assert len(signals) == 1
    signal = signals[0]
    assert signal.metadata["question"] == "What are your biggest challenges with AI coding tools?"
    assert signal.metadata["answer"] == "Lack of trust"
    assert signal.metadata["percent"] == 34.5
    assert signal.metadata["sample_size"] == 12000
    assert signal.metadata["year"] == 2025
    assert signal.metadata["signal_role"] == "problem"


@pytest.mark.asyncio
async def test_respondent_rows_are_aggregated_and_year_can_come_from_config(tmp_path) -> None:
    csv_path = tmp_path / "jetbrains-responses.csv"
    csv_path.write_text(
        "Primary IDE,AI assistant pain points\n"
        "IntelliJ IDEA,Slow suggestions;Lack of trust\n"
        "PyCharm,Lack of trust\n"
        "IntelliJ IDEA,Slow suggestions\n",
        encoding="utf-8",
    )
    adapter = JetBrainsSurveyAdapter(
        config={
            "local_paths": [str(csv_path)],
            "question_filters": ["AI assistant"],
            "year": "2026",
        }
    )

    signals = await adapter.fetch(limit=10)

    by_answer = {signal.metadata["answer"]: signal for signal in signals}
    assert set(by_answer) == {"Slow suggestions", "Lack of trust"}
    assert by_answer["Slow suggestions"].metadata["percent"] == 66.67
    assert by_answer["Slow suggestions"].metadata["sample_size"] == 3
    assert by_answer["Slow suggestions"].metadata["year"] == 2026
    assert by_answer["Slow suggestions"].metadata["signal_role"] == "problem"


@pytest.mark.asyncio
async def test_fetch_reads_mocked_survey_url_response() -> None:
    adapter = JetBrainsSurveyAdapter(
        config={
            "survey_urls": ["https://example.test/jetbrains-2024.csv"],
            "question_filters": ["IDE"],
        }
    )
    response = SimpleNamespace(
        text=(
            "Question,Answer,Percent,Sample Size\n"
            "Which IDE do you use?,IntelliJ IDEA,48.2,24000\n"
        )
    )

    with patch(
        "max.sources.jetbrains_survey.fetch_with_retry",
        new=AsyncMock(return_value=response),
    ) as mock_fetch:
        signals = await adapter.fetch(limit=10)

    assert len(signals) == 1
    assert signals[0].url == "https://example.test/jetbrains-2024.csv"
    assert signals[0].metadata["source_url"] == "https://example.test/jetbrains-2024.csv"
    assert signals[0].metadata["year"] == 2024
    mock_fetch.assert_awaited_once()


@pytest.mark.asyncio
async def test_max_rows_caps_returned_signals(tmp_path) -> None:
    csv_path = tmp_path / "jetbrains-2024.csv"
    csv_path.write_text(
        "Question,Answer,Percent\n"
        "Which IDE do you use?,IntelliJ IDEA,48.2\n"
        "Which IDE do you use?,PyCharm,29.0\n"
        "Which IDE do you use?,WebStorm,18.0\n",
        encoding="utf-8",
    )
    adapter = JetBrainsSurveyAdapter(config={"local_paths": [str(csv_path)], "max_rows": 2})

    signals = await adapter.fetch(limit=30)

    assert len(signals) == 2


@pytest.mark.asyncio
async def test_unsupported_csv_raises_clear_source_parse_error(tmp_path) -> None:
    csv_path = tmp_path / "bad.csv"
    csv_path.write_text("Year\n2024\n", encoding="utf-8")
    adapter = JetBrainsSurveyAdapter(config={"local_paths": [str(csv_path)]})

    with pytest.raises(SourceParseError, match="Unsupported JetBrains survey CSV"):
        await adapter.fetch(limit=10)
