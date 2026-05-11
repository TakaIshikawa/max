"""Technology adoption lifecycle analysis for signal collections."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any


class AdoptionStage(StrEnum):
    """Technology adoption lifecycle stages."""

    INNOVATORS = "innovators"
    EARLY_ADOPTERS = "early_adopters"
    EARLY_MAJORITY = "early_majority"
    LATE_MAJORITY = "late_majority"
    LAGGARDS = "laggards"


@dataclass(frozen=True)
class AdoptionClassification:
    """Adoption lifecycle classification for a set of signals."""

    stage: AdoptionStage
    confidence: float
    indicators: list[str]
    signal_count: int


@dataclass(frozen=True)
class AdoptionProfile:
    """Adoption lifecycle profile for a topic."""

    topic: str
    classifications: list[AdoptionClassification]
    dominant_stage: AdoptionStage
    trajectory: str


STAGE_ORDER: dict[AdoptionStage, int] = {
    AdoptionStage.INNOVATORS: 0,
    AdoptionStage.EARLY_ADOPTERS: 1,
    AdoptionStage.EARLY_MAJORITY: 2,
    AdoptionStage.LATE_MAJORITY: 3,
    AdoptionStage.LAGGARDS: 4,
}

EXPERIMENTAL_TERMS = {
    "prototype",
    "experiment",
    "experimental",
    "research",
    "preview",
    "alpha",
    "hackathon",
    "proof of concept",
}
GROWTH_TERMS = {
    "adoption",
    "growing",
    "pilot",
    "case study",
    "community",
    "launch",
    "beta",
}
DOCUMENTATION_TERMS = {
    "documentation",
    "docs",
    "tutorial",
    "quickstart",
    "guide",
    "api reference",
    "sdk",
}
ENTERPRISE_TERMS = {
    "enterprise",
    "procurement",
    "compliance",
    "security review",
    "soc 2",
    "sso",
    "sla",
    "governance",
}
MATURE_TERMS = {
    "standard",
    "best practice",
    "production",
    "mature",
    "widely used",
    "mainstream",
}
LAGGARD_TERMS = {
    "legacy",
    "maintenance mode",
    "deprecated",
    "migration",
    "sunset",
    "end of life",
    "replacement",
}


def classify_adoption_stage(signals: list[dict[str, Any]]) -> AdoptionClassification:
    """Classify signals into a technology adoption lifecycle stage.

    The heuristic favors concrete adoption evidence: number of signals, source
    diversity, community size, documentation maturity, enterprise readiness,
    and explicit lifecycle language in signal text.
    """
    if not signals:
        return AdoptionClassification(
            stage=AdoptionStage.INNOVATORS,
            confidence=0.0,
            indicators=["No signals available"],
            signal_count=0,
        )

    signal_count = len(signals)
    texts = [_signal_text(signal) for signal in signals]
    combined_text = " ".join(texts)
    source_count = len({_source_name(signal) for signal in signals if _source_name(signal)})
    community_size = max((_community_size(signal) for signal in signals), default=0)
    enterprise_hits = _count_term_hits(combined_text, ENTERPRISE_TERMS) + sum(
        _int_field(signal, "enterprise_mentions") for signal in signals
    )
    doc_hits = _count_term_hits(combined_text, DOCUMENTATION_TERMS)
    experimental_hits = _count_term_hits(combined_text, EXPERIMENTAL_TERMS)
    growth_hits = _count_term_hits(combined_text, GROWTH_TERMS)
    mature_hits = _count_term_hits(combined_text, MATURE_TERMS)
    laggard_hits = _count_term_hits(combined_text, LAGGARD_TERMS)

    score = 0.0
    indicators: list[str] = []

    if signal_count >= 12:
        score += 2.0
        indicators.append("High signal volume")
    elif signal_count >= 6:
        score += 1.4
        indicators.append("Moderate signal volume")
    elif signal_count >= 3:
        score += 0.8
        indicators.append("Emerging signal volume")
    else:
        indicators.append("Sparse signal volume")

    if source_count >= 5:
        score += 1.0
        indicators.append("Broad source diversity")
    elif source_count >= 3:
        score += 0.6
        indicators.append("Multiple source types")
    elif source_count >= 2:
        score += 0.3
        indicators.append("Multiple source types")

    if community_size >= 50_000:
        score += 1.8
        indicators.append("Very large community")
    elif community_size >= 10_000:
        score += 1.3
        indicators.append("Large community")
    elif community_size >= 1_000:
        score += 1.1
        indicators.append("Visible community traction")
    elif community_size >= 100:
        score += 0.5
        indicators.append("Early community traction")

    if doc_hits >= 3:
        score += 1.0
        indicators.append("Mature documentation")
    elif doc_hits > 0:
        score += 0.6
        indicators.append("Documentation present")

    if enterprise_hits >= 4:
        score += 1.1
        indicators.append("Repeated enterprise mentions")
    elif enterprise_hits > 0:
        score += 0.6
        indicators.append("Enterprise readiness signals")

    if growth_hits:
        score += min(0.8, growth_hits * 0.2)
        indicators.append("Adoption growth language")
    if mature_hits:
        score += min(1.2, mature_hits * 0.4)
        indicators.append("Mainstream maturity language")
    if experimental_hits:
        score -= min(0.8, experimental_hits * 0.2)
        indicators.append("Experimental usage language")
    if laggard_hits:
        score += min(2.4, laggard_hits * 0.8)
        indicators.append("Legacy or replacement language")

    recent_span_days = _signal_span_days(signals)
    if recent_span_days is not None and recent_span_days <= 45 and signal_count <= 3:
        score -= 0.3
        indicators.append("Recent concentrated activity")
    elif recent_span_days is not None and recent_span_days >= 365:
        score += 0.4
        indicators.append("Long-running signal history")

    stage = _stage_from_score(score, laggard_hits)
    confidence = _confidence(score, signal_count, source_count, len(indicators))

    return AdoptionClassification(
        stage=stage,
        confidence=confidence,
        indicators=indicators or ["Insufficient adoption indicators"],
        signal_count=signal_count,
    )


def build_adoption_profile(topic: str, signals: list[dict[str, Any]]) -> AdoptionProfile:
    """Build an adoption profile with overall and time-sliced classifications."""
    if not signals:
        classification = classify_adoption_stage(signals)
        return AdoptionProfile(
            topic=topic,
            classifications=[classification],
            dominant_stage=classification.stage,
            trajectory="stable",
        )

    sorted_signals = sorted(signals, key=_published_at_sort_key)
    midpoint = max(1, len(sorted_signals) // 2)
    classifications = [
        classify_adoption_stage(sorted_signals[:midpoint]),
        classify_adoption_stage(sorted_signals[midpoint:]),
        classify_adoption_stage(sorted_signals),
    ]
    dominant_stage = classifications[-1].stage
    trajectory = _trajectory(classifications[0].stage, classifications[1].stage)

    return AdoptionProfile(
        topic=topic,
        classifications=classifications,
        dominant_stage=dominant_stage,
        trajectory=trajectory,
    )


def render_adoption_profile_markdown(profile: AdoptionProfile) -> str:
    """Render an adoption profile as Markdown."""
    lines = [
        f"# Adoption Lifecycle Profile: {profile.topic}",
        "",
        f"- Dominant stage: {profile.dominant_stage.value.replace('_', ' ').title()}",
        f"- Trajectory: {profile.trajectory}",
        "",
        "| Segment | Stage | Confidence | Signals | Indicators |",
        "| --- | --- | ---: | ---: | --- |",
    ]
    labels = _classification_labels(len(profile.classifications))
    for label, classification in zip(labels, profile.classifications):
        indicators = "; ".join(classification.indicators)
        lines.append(
            "| "
            f"{label} | "
            f"{classification.stage.value.replace('_', ' ').title()} | "
            f"{classification.confidence:.2f} | "
            f"{classification.signal_count} | "
            f"{indicators} |"
        )
    return "\n".join(lines)


def render_adoption_profile_json(profile: AdoptionProfile) -> str:
    """Render an adoption profile as stable JSON."""
    payload = asdict(profile)
    payload["dominant_stage"] = profile.dominant_stage.value
    for classification in payload["classifications"]:
        classification["stage"] = classification["stage"].value
    return json.dumps(payload, indent=2, sort_keys=True)


def _stage_from_score(score: float, laggard_hits: int) -> AdoptionStage:
    if laggard_hits > 0 and score >= 6.0:
        return AdoptionStage.LAGGARDS
    if score >= 6.5:
        return AdoptionStage.LATE_MAJORITY
    if score >= 4.0:
        return AdoptionStage.EARLY_MAJORITY
    if score >= 1.4:
        return AdoptionStage.EARLY_ADOPTERS
    return AdoptionStage.INNOVATORS


def _confidence(score: float, signal_count: int, source_count: int, indicator_count: int) -> float:
    threshold_distance = min(
        abs(score - boundary) for boundary in (1.4, 4.0, 6.5, 7.0)
    )
    evidence = min(0.35, signal_count * 0.025) + min(0.2, source_count * 0.05)
    indicator_strength = min(0.2, indicator_count * 0.035)
    separation = min(0.25, threshold_distance * 0.12)
    return round(min(0.98, 0.2 + evidence + indicator_strength + separation), 4)


def _trajectory(first: AdoptionStage, second: AdoptionStage) -> str:
    delta = STAGE_ORDER[second] - STAGE_ORDER[first]
    if delta > 0:
        return "ascending"
    if delta < 0:
        return "declining"
    return "stable"


def _signal_text(signal: dict[str, Any]) -> str:
    parts: list[str] = []
    for key in ("title", "content", "summary", "description", "body"):
        value = signal.get(key)
        if value:
            parts.append(str(value).lower())
    metadata = signal.get("metadata")
    if isinstance(metadata, dict):
        parts.extend(str(value).lower() for value in metadata.values() if isinstance(value, str))
    return " ".join(parts)


def _source_name(signal: dict[str, Any]) -> str:
    for key in ("source_type", "source", "source_adapter", "publisher"):
        value = signal.get(key)
        if value:
            return str(value)
    metadata = signal.get("metadata")
    if isinstance(metadata, dict) and metadata.get("source"):
        return str(metadata["source"])
    return ""


def _community_size(signal: dict[str, Any]) -> int:
    candidates = [
        signal.get("community_size"),
        signal.get("stars"),
        signal.get("followers"),
        signal.get("downloads"),
    ]
    metadata = signal.get("metadata")
    if isinstance(metadata, dict):
        candidates.extend(
            metadata.get(key)
            for key in ("community_size", "stars", "followers", "downloads")
        )
    return max((_coerce_int(value) for value in candidates), default=0)


def _int_field(signal: dict[str, Any], field: str) -> int:
    value = signal.get(field)
    metadata = signal.get("metadata")
    if value is None and isinstance(metadata, dict):
        value = metadata.get(field)
    return _coerce_int(value)


def _coerce_int(value: Any) -> int:
    if isinstance(value, bool) or value is None:
        return 0
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        try:
            return int(float(value.replace(",", "")))
        except ValueError:
            return 0
    return 0


def _count_term_hits(text: str, terms: set[str]) -> int:
    return sum(1 for term in terms if term in text)


def _signal_span_days(signals: list[dict[str, Any]]) -> int | None:
    dates = [_parse_datetime(signal.get("published_at") or signal.get("created_at")) for signal in signals]
    dates = [date for date in dates if date is not None]
    if len(dates) < 2:
        return None
    return (max(dates) - min(dates)).days


def _published_at_sort_key(signal: dict[str, Any]) -> datetime:
    parsed = _parse_datetime(signal.get("published_at") or signal.get("created_at"))
    return parsed or datetime.min.replace(tzinfo=timezone.utc)


def _parse_datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value
    if isinstance(value, str):
        try:
            normalized = value.replace("Z", "+00:00")
            parsed = datetime.fromisoformat(normalized)
            if parsed.tzinfo is None:
                return parsed.replace(tzinfo=timezone.utc)
            return parsed
        except ValueError:
            return None
    return None


def _classification_labels(count: int) -> list[str]:
    if count == 1:
        return ["Overall"]
    if count == 3:
        return ["Earlier", "Recent", "Overall"]
    return [f"Segment {index}" for index in range(1, count + 1)]
