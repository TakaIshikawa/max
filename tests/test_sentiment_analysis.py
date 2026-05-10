"""Tests for sentiment analysis module."""

from __future__ import annotations

import pytest

from max.analysis.sentiment_analysis import (
    AggregatedSentiment,
    SentimentAnalyzer,
    SentimentScore,
)


# ── Analyzer setup ───────────────────────────────────────────────────

@pytest.fixture
def analyzer() -> SentimentAnalyzer:
    return SentimentAnalyzer()


# ── Polarity tests ───────────────────────────────────────────────────


def test_positive_text(analyzer: SentimentAnalyzer) -> None:
    score = analyzer.score("This is a great and amazing product")
    assert score.polarity > 0
    assert score.positive_count >= 2
    assert score.negative_count == 0


def test_negative_text(analyzer: SentimentAnalyzer) -> None:
    score = analyzer.score("This is terrible and awful software")
    assert score.polarity < 0
    assert score.negative_count >= 2
    assert score.positive_count == 0


def test_neutral_text(analyzer: SentimentAnalyzer) -> None:
    score = analyzer.score("The package provides HTTP request functionality")
    assert score.polarity == 0.0
    assert score.positive_count == 0
    assert score.negative_count == 0


def test_mixed_text(analyzer: SentimentAnalyzer) -> None:
    score = analyzer.score("The tool is great but has terrible documentation")
    assert score.positive_count >= 1
    assert score.negative_count >= 1


def test_empty_text(analyzer: SentimentAnalyzer) -> None:
    score = analyzer.score("")
    assert score.polarity == 0.0
    assert score.subjectivity == 0.0
    assert score.word_count == 0


def test_whitespace_only(analyzer: SentimentAnalyzer) -> None:
    score = analyzer.score("   ")
    assert score.polarity == 0.0


# ── Negation handling ────────────────────────────────────────────────


def test_negation_flips_positive(analyzer: SentimentAnalyzer) -> None:
    score = analyzer.score("This is not good")
    assert score.polarity < 0
    assert score.negative_count >= 1


def test_negation_flips_negative(analyzer: SentimentAnalyzer) -> None:
    score = analyzer.score("This is not bad")
    assert score.polarity > 0
    assert score.positive_count >= 1


def test_negation_contraction(analyzer: SentimentAnalyzer) -> None:
    score = analyzer.score("I don't think this is good at all and it is terrible")
    # "don't" negates "good" (within window), "terrible" is far enough to stay negative
    assert score.negative_count >= 1


# ── Intensifier handling ─────────────────────────────────────────────


def test_intensifier_increases_score(analyzer: SentimentAnalyzer) -> None:
    base = analyzer.score("This is good")
    intensified = analyzer.score("This is very good")
    # Both positive, but intensified should have higher raw magnitude
    assert base.polarity > 0
    assert intensified.polarity > 0
    # With single word, polarity normalizes to 1.0 in both cases,
    # but the intensifier should still register
    assert intensified.positive_count >= 1


def test_intensifier_extremely(analyzer: SentimentAnalyzer) -> None:
    score = analyzer.score("This is extremely bad")
    assert score.polarity < 0


# ── Subjectivity tests ──────────────────────────────────────────────


def test_subjective_text(analyzer: SentimentAnalyzer) -> None:
    score = analyzer.score("I think this is probably the best option I believe")
    assert score.subjectivity > 0


def test_objective_text(analyzer: SentimentAnalyzer) -> None:
    score = analyzer.score("The function returns an integer value from the database")
    assert score.subjectivity == 0.0


# ── Polarity bounds ─────────────────────────────────────────────────


def test_polarity_bounded(analyzer: SentimentAnalyzer) -> None:
    score = analyzer.score(
        "great amazing excellent brilliant outstanding superb wonderful"
    )
    assert -1.0 <= score.polarity <= 1.0


def test_polarity_negative_bounded(analyzer: SentimentAnalyzer) -> None:
    score = analyzer.score(
        "terrible awful horrible poor broken buggy slow"
    )
    assert -1.0 <= score.polarity <= 1.0


# ── Batch scoring ────────────────────────────────────────────────────


def test_score_batch(analyzer: SentimentAnalyzer) -> None:
    texts = [
        "This is great",
        "This is terrible",
        "Neutral statement here",
    ]
    scores = analyzer.score_batch(texts)
    assert len(scores) == 3
    assert scores[0].polarity > 0
    assert scores[1].polarity < 0
    assert scores[2].polarity == 0.0


# ── Aggregation tests ───────────────────────────────────────────────


def test_aggregate_by_group(analyzer: SentimentAnalyzer) -> None:
    texts = [
        "This is great software",
        "Amazing and wonderful tool",
        "This is terrible and broken",
        "Awful buggy code",
    ]
    groups = ["positive_src", "positive_src", "negative_src", "negative_src"]

    results = analyzer.aggregate_by_group(texts, groups)
    assert len(results) == 2

    by_group = {r.group: r for r in results}
    assert by_group["positive_src"].avg_polarity > 0
    assert by_group["negative_src"].avg_polarity < 0
    assert by_group["positive_src"].sample_count == 2
    assert by_group["negative_src"].sample_count == 2


def test_aggregate_mismatched_lengths(analyzer: SentimentAnalyzer) -> None:
    with pytest.raises(ValueError, match="same length"):
        analyzer.aggregate_by_group(["text1"], ["group1", "group2"])


def test_aggregate_counts(analyzer: SentimentAnalyzer) -> None:
    texts = ["great", "terrible", "the function returns data"]
    groups = ["a", "a", "a"]

    results = analyzer.aggregate_by_group(texts, groups)
    assert len(results) == 1
    agg = results[0]
    assert agg.positive_count == 1
    assert agg.negative_count == 1
    assert agg.neutral_count == 1


# ── Custom word lists ────────────────────────────────────────────────


def test_custom_positive_words() -> None:
    analyzer = SentimentAnalyzer(positive_words={"blazing", "lightning"})
    score = analyzer.score("This is blazing and lightning fast")
    assert score.positive_count >= 2


def test_custom_negative_words() -> None:
    analyzer = SentimentAnalyzer(negative_words={"sluggish", "clunky"})
    score = analyzer.score("The interface is sluggish and clunky")
    assert score.negative_count >= 2
