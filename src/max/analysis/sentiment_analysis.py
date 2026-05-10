"""Sentiment analysis module for signal text.

Scores sentiment polarity and subjectivity of collected signal text using
keyword-based scoring with positive/negative word lists and negation handling.
Produces per-signal sentiment scores and aggregated sentiment trends by
source or topic.
"""

from __future__ import annotations

from dataclasses import dataclass

# ── Word lists ────────────────────────────────────────────────────────

POSITIVE_WORDS: set[str] = {
    "good", "great", "excellent", "amazing", "awesome", "fantastic",
    "wonderful", "brilliant", "outstanding", "superb", "love", "best",
    "perfect", "impressive", "innovative", "powerful", "reliable",
    "fast", "efficient", "easy", "simple", "clean", "elegant",
    "robust", "stable", "growing", "improved", "better", "success",
    "popular", "recommended", "useful", "helpful", "strong",
    "exciting", "promising", "remarkable", "superior", "thriving",
}

NEGATIVE_WORDS: set[str] = {
    "bad", "terrible", "awful", "horrible", "poor", "worst",
    "ugly", "broken", "slow", "buggy", "complex", "difficult",
    "confusing", "deprecated", "abandoned", "insecure", "vulnerable",
    "bloated", "unstable", "failing", "crashed", "error", "issue",
    "problem", "risk", "warning", "decline", "loss", "weak",
    "outdated", "legacy", "unmaintained", "flawed", "frustrating",
    "disappointing", "limited", "lacking", "painful", "annoying",
}

NEGATION_WORDS: set[str] = {
    "not", "no", "never", "neither", "nor", "hardly", "barely",
    "scarcely", "don't", "doesn't", "didn't", "won't", "wouldn't",
    "shouldn't", "couldn't", "isn't", "aren't", "wasn't", "weren't",
    "cannot", "can't",
}

INTENSIFIERS: dict[str, float] = {
    "very": 1.5,
    "extremely": 2.0,
    "incredibly": 2.0,
    "really": 1.5,
    "absolutely": 2.0,
    "highly": 1.5,
    "quite": 1.3,
    "somewhat": 0.7,
    "slightly": 0.5,
    "fairly": 0.8,
    "rather": 1.2,
    "mostly": 0.9,
}

SUBJECTIVE_WORDS: set[str] = {
    "think", "believe", "feel", "opinion", "seems", "maybe",
    "probably", "possibly", "might", "could", "guess", "suppose",
    "prefer", "like", "dislike", "love", "hate", "wish",
    "hope", "fear", "expect", "assume", "personally",
} | POSITIVE_WORDS | NEGATIVE_WORDS


# ── Data classes ─────────────────────────────────────────────────────


@dataclass(frozen=True)
class SentimentScore:
    """Sentiment analysis result for a single text."""

    polarity: float  # -1.0 to +1.0
    subjectivity: float  # 0.0 (objective) to 1.0 (subjective)
    positive_count: int = 0
    negative_count: int = 0
    word_count: int = 0


@dataclass
class AggregatedSentiment:
    """Aggregated sentiment across multiple texts."""

    group: str
    avg_polarity: float
    avg_subjectivity: float
    sample_count: int
    positive_count: int = 0
    negative_count: int = 0
    neutral_count: int = 0


# ── Analyzer ─────────────────────────────────────────────────────────


class SentimentAnalyzer:
    """Keyword-based sentiment analyzer with negation and intensifier handling.

    Scores text polarity from -1.0 (most negative) to +1.0 (most positive)
    and subjectivity from 0.0 (objective) to 1.0 (subjective).
    """

    def __init__(
        self,
        *,
        positive_words: set[str] | None = None,
        negative_words: set[str] | None = None,
    ) -> None:
        self._positive = positive_words or POSITIVE_WORDS
        self._negative = negative_words or NEGATIVE_WORDS

    def score(self, text: str) -> SentimentScore:
        """Score a single text for sentiment polarity and subjectivity."""
        if not text or not text.strip():
            return SentimentScore(polarity=0.0, subjectivity=0.0, word_count=0)

        words = text.lower().split()
        word_count = len(words)
        if word_count == 0:
            return SentimentScore(polarity=0.0, subjectivity=0.0, word_count=0)

        positive_hits = 0
        negative_hits = 0
        subjective_hits = 0
        raw_score = 0.0

        for i, word in enumerate(words):
            # Strip basic punctuation for matching
            clean = word.strip(".,!?;:\"'()-[]{}")

            if clean in SUBJECTIVE_WORDS:
                subjective_hits += 1

            is_positive = clean in self._positive
            is_negative = clean in self._negative

            if not is_positive and not is_negative:
                continue

            # Check for negation in preceding 1-3 words
            negated = False
            for j in range(max(0, i - 3), i):
                prev = words[j].strip(".,!?;:\"'()-[]{}")
                if prev in NEGATION_WORDS:
                    negated = True
                    break

            # Check for intensifier in preceding word
            multiplier = 1.0
            if i > 0:
                prev_clean = words[i - 1].strip(".,!?;:\"'()-[]{}")
                if prev_clean in INTENSIFIERS:
                    multiplier = INTENSIFIERS[prev_clean]

            if is_positive:
                if negated:
                    negative_hits += 1
                    raw_score -= 1.0 * multiplier
                else:
                    positive_hits += 1
                    raw_score += 1.0 * multiplier
            elif is_negative:
                if negated:
                    positive_hits += 1
                    raw_score += 1.0 * multiplier
                else:
                    negative_hits += 1
                    raw_score -= 1.0 * multiplier

        # Normalize polarity to [-1, 1]
        sentiment_words = positive_hits + negative_hits
        if sentiment_words == 0:
            polarity = 0.0
        else:
            polarity = max(-1.0, min(1.0, raw_score / sentiment_words))

        # Subjectivity: ratio of subjective words to total words
        subjectivity = min(1.0, subjective_hits / word_count) if word_count > 0 else 0.0

        return SentimentScore(
            polarity=round(polarity, 4),
            subjectivity=round(subjectivity, 4),
            positive_count=positive_hits,
            negative_count=negative_hits,
            word_count=word_count,
        )

    def score_batch(self, texts: list[str]) -> list[SentimentScore]:
        """Score multiple texts."""
        return [self.score(t) for t in texts]

    def aggregate_by_group(
        self,
        texts: list[str],
        groups: list[str],
    ) -> list[AggregatedSentiment]:
        """Aggregate sentiment scores by group (source or topic).

        Args:
            texts: list of text strings to score.
            groups: parallel list of group labels (e.g., source names).

        Returns:
            List of AggregatedSentiment, one per unique group.
        """
        if len(texts) != len(groups):
            raise ValueError("texts and groups must have the same length")

        group_scores: dict[str, list[SentimentScore]] = {}
        for text, group in zip(texts, groups):
            score = self.score(text)
            group_scores.setdefault(group, []).append(score)

        results: list[AggregatedSentiment] = []
        for group, scores in sorted(group_scores.items()):
            count = len(scores)
            avg_pol = sum(s.polarity for s in scores) / count
            avg_sub = sum(s.subjectivity for s in scores) / count
            pos = sum(1 for s in scores if s.polarity > 0.05)
            neg = sum(1 for s in scores if s.polarity < -0.05)
            neu = count - pos - neg

            results.append(AggregatedSentiment(
                group=group,
                avg_polarity=round(avg_pol, 4),
                avg_subjectivity=round(avg_sub, 4),
                sample_count=count,
                positive_count=pos,
                negative_count=neg,
                neutral_count=neu,
            ))

        return results
