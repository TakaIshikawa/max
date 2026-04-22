"""Contradiction analysis for evidence supporting insights and ideas."""

from __future__ import annotations

import re
from collections import defaultdict
from typing import Any

from max.server.evidence_chain import build_evidence_chain_graph
from max.store.db import Store
from max.types.buildable_unit import BuildableUnit
from max.types.insight import Insight
from max.types.signal import Signal

CLAIM_METADATA_KEYS = (
    "normalized_claim",
    "claim",
    "claim_text",
    "evidence_claim",
    "summary_claim",
)
SENTIMENT_METADATA_KEYS = ("sentiment", "stance", "polarity", "evidence_sentiment")
ROLE_METADATA_KEYS = (
    "contradiction_role",
    "evidence_role",
    "stance_role",
    "role",
    "signal_role",
)

POSITIVE_VALUES = {
    "positive",
    "support",
    "supports",
    "supporting",
    "supported",
    "agree",
    "agrees",
    "confirm",
    "confirms",
    "confirmed",
    "pro",
    "validates",
    "validated",
    "yes",
    "true",
}
NEGATIVE_VALUES = {
    "negative",
    "oppose",
    "opposes",
    "opposing",
    "contradict",
    "contradicts",
    "contradicting",
    "refute",
    "refutes",
    "refuting",
    "against",
    "con",
    "invalidates",
    "invalidated",
    "no",
    "false",
}
MIXED_VALUES = {"mixed", "neutral", "unclear", "unknown"}


def _compact(value: Any) -> str:
    return str(value or "").strip()


def normalize_claim_text(value: str) -> str:
    """Normalize a claim string for grouping related evidence."""
    text = value.lower()
    text = re.sub(r"https?://\S+", " ", text)
    text = re.sub(r"[^a-z0-9]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _metadata_text(metadata: dict, keys: tuple[str, ...]) -> str:
    for key in keys:
        value = metadata.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _claim_text(signal: Signal) -> str:
    metadata_claim = _metadata_text(signal.metadata, CLAIM_METADATA_KEYS)
    if metadata_claim:
        return metadata_claim
    title = _compact(signal.title)
    if title:
        return title
    content = _compact(signal.content)
    return content[:180]


def _polarity(value: str) -> str:
    normalized = normalize_claim_text(value).replace(" ", "_")
    if normalized in POSITIVE_VALUES:
        return "positive"
    if normalized in NEGATIVE_VALUES:
        return "negative"
    if normalized in MIXED_VALUES:
        return "mixed"
    return ""


def _sentiment(signal: Signal) -> tuple[str, str]:
    sentiment = _metadata_text(signal.metadata, SENTIMENT_METADATA_KEYS)
    sentiment_polarity = _polarity(sentiment)
    if sentiment_polarity:
        return sentiment_polarity, sentiment

    role = _metadata_text(signal.metadata, ROLE_METADATA_KEYS) or signal.signal_role
    role_polarity = _polarity(role)
    if role_polarity:
        return role_polarity, role

    return "unknown", role or sentiment or "unknown"


def _source_key(signal: Signal) -> str:
    return signal.source_adapter or (
        signal.source_type.value if hasattr(signal.source_type, "value") else str(signal.source_type)
    )


def _signal_record(signal: Signal, *, via: str) -> dict:
    claim_text = _claim_text(signal)
    sentiment, sentiment_source = _sentiment(signal)
    source_type = signal.source_type.value if hasattr(signal.source_type, "value") else signal.source_type
    return {
        "signal_id": signal.id,
        "source": _source_key(signal),
        "source_adapter": signal.source_adapter,
        "source_type": source_type,
        "sentiment": sentiment,
        "sentiment_source": sentiment_source,
        "role": signal.signal_role or _metadata_text(signal.metadata, ROLE_METADATA_KEYS) or "",
        "claim_text": claim_text,
        "normalized_claim": normalize_claim_text(claim_text),
        "credibility": signal.credibility,
        "via": via,
    }


def _dedupe_records(records: list[dict]) -> list[dict]:
    deduped: dict[str, dict] = {}
    for record in records:
        existing = deduped.get(record["signal_id"])
        if existing is None:
            deduped[record["signal_id"]] = record
            continue
        if existing["via"] != "direct" and record["via"] == "direct":
            deduped[record["signal_id"]] = record
    return list(deduped.values())


def _severity(records: list[dict]) -> str:
    distinct_sources = {record["source"] for record in records}
    avg_credibility = sum(float(record["credibility"] or 0.0) for record in records) / len(records)
    if len(records) >= 3 and len(distinct_sources) >= 2 and avg_credibility >= 0.65:
        return "high"
    if len(distinct_sources) >= 2 or avg_credibility >= 0.7:
        return "medium"
    return "low"


def _review_note(claim: str, records: list[dict], severity: str) -> str:
    positive = [record["signal_id"] for record in records if record["sentiment"] == "positive"]
    negative = [record["signal_id"] for record in records if record["sentiment"] == "negative"]
    sources = ", ".join(sorted({record["source"] for record in records}))
    return (
        f"Review {severity}-severity conflict on '{claim}': "
        f"{len(positive)} supporting and {len(negative)} opposing signal(s) across {sources}. "
        "Check the underlying claim wording, source freshness, and whether the evidence should be split."
    )


def _summarize_group(group_key: str, records: list[dict], group_type: str) -> dict | None:
    polarities = {record["sentiment"] for record in records}
    if "positive" not in polarities or "negative" not in polarities:
        return None

    records = sorted(records, key=lambda record: record["signal_id"])
    severity = _severity(records)
    claim = records[0]["claim_text"] or group_key
    return {
        "group_type": group_type,
        "group_key": group_key,
        "claim": claim,
        "normalized_claim": records[0]["normalized_claim"],
        "severity": severity,
        "involved_signal_ids": [record["signal_id"] for record in records],
        "sources": sorted({record["source"] for record in records}),
        "sentiments": {
            "positive": [record["signal_id"] for record in records if record["sentiment"] == "positive"],
            "negative": [record["signal_id"] for record in records if record["sentiment"] == "negative"],
            "mixed": [record["signal_id"] for record in records if record["sentiment"] == "mixed"],
            "unknown": [record["signal_id"] for record in records if record["sentiment"] == "unknown"],
        },
        "roles": {
            role: [record["signal_id"] for record in records if record["role"] == role]
            for role in sorted({record["role"] for record in records if record["role"]})
        },
        "suggested_review_note": _review_note(claim, records, severity),
    }


def _build_report(entity_type: str, entity_id: str, records: list[dict]) -> dict:
    records = _dedupe_records(records)

    by_claim: dict[str, list[dict]] = defaultdict(list)
    by_source_claim: dict[str, list[dict]] = defaultdict(list)
    by_role_claim: dict[str, list[dict]] = defaultdict(list)

    for record in records:
        if not record["normalized_claim"]:
            continue
        by_claim[record["normalized_claim"]].append(record)
        by_source_claim[f"{record['source']}::{record['normalized_claim']}"].append(record)
        if record["role"]:
            by_role_claim[f"{record['role']}::{record['normalized_claim']}"].append(record)

    summaries: list[dict] = []
    seen: set[tuple[str, tuple[str, ...]]] = set()
    for group_type, groups in (
        ("claim", by_claim),
        ("source_claim", by_source_claim),
        ("role_claim", by_role_claim),
    ):
        for key, group_records in groups.items():
            summary = _summarize_group(key, group_records, group_type)
            if not summary:
                continue
            dedupe_key = (
                summary["normalized_claim"],
                tuple(summary["involved_signal_ids"]),
            )
            if dedupe_key in seen:
                continue
            seen.add(dedupe_key)
            summaries.append(summary)

    severity_rank = {"high": 0, "medium": 1, "low": 2}
    summaries.sort(
        key=lambda item: (
            severity_rank[item["severity"]],
            item["normalized_claim"],
            item["group_type"],
        )
    )

    return {
        "entity_type": entity_type,
        "entity_id": entity_id,
        "signal_count": len(records),
        "contradiction_count": len(summaries),
        "contradictions": summaries,
    }


def build_insight_contradiction_report(insight: Insight, store: Store) -> dict:
    """Find contradictions among signals supporting one insight."""
    records: list[dict] = []
    for signal_id in insight.evidence:
        signal = store.get_signal(signal_id)
        if signal:
            records.append(_signal_record(signal, via=f"insight:{insight.id}"))
    return _build_report("insight", insight.id, records)


def build_idea_contradiction_report(unit: BuildableUnit, store: Store) -> dict:
    """Find contradictions among resolved evidence signals supporting one idea."""
    graph = build_evidence_chain_graph(unit, store)
    records = []
    direct_signal_ids = set(unit.evidence_signals)
    for signal_payload in graph["signals"]:
        signal = store.get_signal(signal_payload["id"])
        if not signal:
            continue
        via = "direct" if signal.id in direct_signal_ids else "insight"
        records.append(_signal_record(signal, via=via))
    return _build_report("idea", unit.id, records)
