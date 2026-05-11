"""Competitive landscape export for market positioning analysis."""

from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Iterable

if TYPE_CHECKING:
    from max.store.db import Store

SCHEMA_VERSION = "max.competitive_landscape.v1"
KIND = "max.competitive_landscape"

_COMPETITOR_MARKERS = (
    "competitor",
    "competitors",
    "alternative",
    "alternatives",
    "competes with",
    "compared to",
    "versus",
    "vs",
    "replace",
    "replaces",
    "instead of",
)
_DIRECT_MARKERS = ("competitor", "competes", "versus", "vs", "replace", "replaces")
_ADJACENT_MARKERS = ("alternative", "alternatives", "compared to", "instead of")
_DISRUPTOR_MARKERS = ("disrupt", "new entrant", "startup", "open source", "ai-native")
_COMPETITOR_KEYS = (
    "competitors",
    "competitor",
    "alternatives",
    "alternative",
    "existing_solutions",
    "existing_solution",
    "vendor",
    "company",
)
_DIFFERENTIATOR_FIELDS = (
    "value_proposition",
    "solution",
    "problem",
    "specific_user",
    "workflow_context",
    "why_now",
)


def build_competitive_landscape(
    store: Store,
    domain: str | None = None,
) -> dict[str, Any]:
    """Build a market positioning landscape for buildable units."""
    units = store.get_buildable_units(limit=1000, domain=domain)
    all_signals = _safe_get_signals(store)
    signal_by_id = {str(getattr(signal, "id", "")): signal for signal in all_signals}

    entries: list[dict[str, Any]] = []
    for unit in units:
        signals = _source_signals(unit, store, signal_by_id)
        competitors = _extract_competitors(signals)
        market_position = _classify_position(unit, competitors)
        entry = {
            "idea_id": str(getattr(unit, "id", "")),
            "title": str(getattr(unit, "title", "Untitled")),
            "competitors": competitors,
            "differentiators": _differentiators(unit),
            "market_position": market_position,
            "threat_level": _threat_level(competitors),
        }
        entries.append(entry)

    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": {
            "project": "max",
            "entity_type": "competitive_landscape",
            "domain_filter": domain,
        },
        "landscape_entries": entries,
        "market_gaps": _identify_market_gaps(entries),
        "positioning_summary": _positioning_summary(entries),
    }


def render_competitive_landscape_markdown(report: dict[str, Any]) -> str:
    """Render a competitive landscape report as Markdown."""
    lines = [
        "# Competitive Landscape",
        "",
        f"Schema: `{report['schema_version']}`",
        f"Generated: {report['generated_at']}",
        f"Total entries: {len(report.get('landscape_entries', []))}",
        "",
        "## Positioning Matrix",
        "",
        "| Idea | Market Position | Threat Level | Competitors | Differentiators |",
        "|------|-----------------|--------------|-------------|-----------------|",
    ]

    entries = report.get("landscape_entries", [])
    if entries:
        for entry in entries:
            competitors = ", ".join(comp["name"] for comp in entry.get("competitors", [])[:3]) or "None identified"
            differentiators = "; ".join(entry.get("differentiators", [])[:3]) or "Needs discovery"
            lines.append(
                f"| {_md(entry['title'])} | {entry['market_position']} | {entry['threat_level']} | "
                f"{_md(competitors)} | {_md(differentiators)} |"
            )
    else:
        lines.append("| No buildable units available | emerging | low | None identified | Needs discovery |")

    lines.extend([
        "",
        "## Market Gaps",
        "",
    ])
    gaps = report.get("market_gaps", [])
    if gaps:
        lines.extend([
            "| Segment | Gap Type | Opportunity Count | Description |",
            "|---------|----------|-------------------|-------------|",
        ])
        for gap in gaps:
            lines.append(
                f"| {_md(gap['segment'])} | {gap['gap_type']} | {gap['opportunity_count']} | "
                f"{_md(gap['description'])} |"
            )
    else:
        lines.append("- No market gaps identified.")

    summary = report.get("positioning_summary", {})
    lines.extend([
        "",
        "## Positioning Summary",
        "",
        f"- Entries: {summary.get('entry_count', 0)}",
        f"- Competitors: {summary.get('competitor_count', 0)}",
        f"- Direct competitor mentions: {summary.get('relationship_counts', {}).get('direct competitor', 0)}",
        f"- Adjacent mentions: {summary.get('relationship_counts', {}).get('adjacent', 0)}",
        f"- Potential disruptor mentions: {summary.get('relationship_counts', {}).get('potential disruptor', 0)}",
    ])

    return "\n".join(lines).rstrip() + "\n"


def render_competitive_landscape_json(report: dict[str, Any]) -> str:
    """Render a competitive landscape report as stable formatted JSON."""
    return json.dumps(report, indent=2, sort_keys=True, default=str)


def _extract_competitors(signals: list[Any]) -> list[dict[str, Any]]:
    """Extract competitor mentions from signal titles, content, tags, and metadata."""
    competitors: dict[str, dict[str, Any]] = {}

    for signal in signals:
        metadata = _metadata(signal)
        for raw in _metadata_competitors(metadata):
            _add_competitor(competitors, raw, signal=signal, relationship=_relationship_for_text(str(raw)))

        text = " ".join(
            item
            for item in [
                str(getattr(signal, "title", "") or ""),
                str(getattr(signal, "content", "") or ""),
                " ".join(str(tag) for tag in getattr(signal, "tags", []) or []),
            ]
            if item
        )
        if not _mentions_market_solution(text):
            continue
        relationship = _relationship_for_text(text)
        for name in _names_from_text(text):
            _add_competitor(competitors, name, signal=signal, relationship=relationship)

    result = []
    for comp in competitors.values():
        mentions = comp.pop("_mentions")
        overlap = min(1.0, 0.35 + mentions * 0.2 + comp.pop("_relationship_weight"))
        comp["overlap_score"] = round(overlap, 2)
        result.append(comp)
    return sorted(result, key=lambda item: (-item["overlap_score"], item["name"]))[:10]


def _classify_position(unit: Any, competitors: list[dict[str, Any]]) -> str:
    """Classify an idea's market position from competitor density and quality signals."""
    quality = _float(getattr(unit, "quality_score", 0.0))
    novelty = _float(getattr(unit, "novelty_score", 0.0))
    direct_count = sum(1 for comp in competitors if comp.get("relationship") == "direct competitor")
    avg_overlap = (
        sum(_float(comp.get("overlap_score", 0.0)) for comp in competitors) / len(competitors)
        if competitors
        else 0.0
    )

    if not competitors:
        return "emerging"
    if direct_count >= 2 and avg_overlap >= 0.7:
        return "challenger"
    if quality >= 0.8 and len(competitors) >= 3:
        return "leader"
    if novelty >= 0.65 or len(competitors) <= 1:
        return "niche"
    return "challenger"


def _identify_market_gaps(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Find underserved segments from low competitor density and niche positioning."""
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for entry in entries:
        segment = _segment_from_entry(entry)
        groups[segment].append(entry)

    gaps: list[dict[str, Any]] = []
    for segment, segment_entries in sorted(groups.items()):
        no_competitor = [entry for entry in segment_entries if not entry.get("competitors")]
        low_threat = [
            entry
            for entry in segment_entries
            if entry.get("threat_level") == "low" or entry.get("market_position") in {"emerging", "niche"}
        ]
        if no_competitor:
            gaps.append({
                "segment": segment,
                "gap_type": "underserved",
                "opportunity_count": len(no_competitor),
                "description": f"{segment} has buildable ideas with no named incumbent in source evidence.",
            })
        elif len(low_threat) >= max(1, len(segment_entries) // 2):
            gaps.append({
                "segment": segment,
                "gap_type": "white space",
                "opportunity_count": len(low_threat),
                "description": f"{segment} shows low competitive threat across multiple positioning entries.",
            })
    return gaps


def _safe_get_signals(store: Any) -> list[Any]:
    get_signals = getattr(store, "get_signals", None)
    if not callable(get_signals):
        return []
    try:
        signals = get_signals(limit=1000)
    except TypeError:
        signals = get_signals()
    return signals if isinstance(signals, list) else []


def _source_signals(unit: Any, store: Any, signal_by_id: dict[str, Any]) -> list[Any]:
    signal_ids = [str(item) for item in getattr(unit, "evidence_signals", []) or []]
    signals: list[Any] = []
    for signal_id in signal_ids:
        signal = signal_by_id.get(signal_id) or _get_signal(store, signal_id)
        if _looks_like_signal(signal):
            signals.append(signal)
    return signals


def _get_signal(store: Any, signal_id: str) -> Any | None:
    get_signal = getattr(store, "get_signal", None)
    if not callable(get_signal):
        return None
    try:
        return get_signal(signal_id)
    except Exception:
        return None


def _looks_like_signal(value: Any) -> bool:
    return isinstance(value, dict) or any(hasattr(value, attr) for attr in ("title", "content", "metadata"))


def _metadata(value: Any) -> dict[str, Any]:
    metadata = value.get("metadata", {}) if isinstance(value, dict) else getattr(value, "metadata", {})
    return metadata if isinstance(metadata, dict) else {}


def _metadata_competitors(metadata: dict[str, Any]) -> Iterable[Any]:
    for key in _COMPETITOR_KEYS:
        value = metadata.get(key)
        if value:
            yield from _flatten_competitor_values(value)


def _flatten_competitor_values(value: Any) -> Iterable[Any]:
    if isinstance(value, dict):
        if value.get("name"):
            yield value
        else:
            for item in value.values():
                yield from _flatten_competitor_values(item)
    elif isinstance(value, (list, tuple, set)):
        for item in value:
            yield from _flatten_competitor_values(item)
    else:
        yield value


def _mentions_market_solution(text: str) -> bool:
    lowered = text.lower()
    return any(marker in lowered for marker in _COMPETITOR_MARKERS)


def _relationship_for_text(text: str) -> str:
    lowered = text.lower()
    if any(marker in lowered for marker in _DISRUPTOR_MARKERS):
        return "potential disruptor"
    if any(marker in lowered for marker in _ADJACENT_MARKERS):
        return "adjacent"
    if any(marker in lowered for marker in _DIRECT_MARKERS):
        return "direct competitor"
    return "adjacent"


def _names_from_text(text: str) -> list[str]:
    names: list[str] = []
    for marker in _COMPETITOR_MARKERS:
        pattern = rf"(?:{re.escape(marker)})\s*(?:include|includes|like|such as|are|:)?\s+([^.;\n]+)"
        for match in re.finditer(pattern, text, flags=re.IGNORECASE):
            names.extend(_split_names(match.group(1)))
    return names


def _split_names(text: str) -> list[str]:
    cleaned = re.sub(r"\([^)]*\)", "", text)
    pieces = re.split(r",|/|\band\b|\bor\b|\bplus\b", cleaned)
    names: list[str] = []
    for piece in pieces:
        name = _clean_name(piece)
        if name:
            names.append(name)
    return names


def _clean_name(value: Any) -> str:
    if isinstance(value, dict):
        value = value.get("name") or value.get("title") or value.get("company") or ""
    text = str(value).strip(" .:;,-")
    text = re.split(
        r"\s+\b(?:are|is|was|were|for|in|with|when|while|but|that|which)\b\s+",
        text,
        maxsplit=1,
        flags=re.IGNORECASE,
    )[0]
    text = re.sub(r"^(the|a|an)\s+", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\s+", " ", text)
    if not text or len(text) > 80:
        return ""
    if text.lower() in set(_COMPETITOR_MARKERS) | {"tool", "platform", "solution", "incumbents"}:
        return ""
    return text


def _add_competitor(
    competitors: dict[str, dict[str, Any]],
    raw: Any,
    *,
    signal: Any,
    relationship: str,
) -> None:
    name = _clean_name(raw)
    if not name:
        return
    key = name.casefold()
    url = ""
    if isinstance(raw, dict):
        url = str(raw.get("url") or raw.get("website") or "")
    if not url:
        url = str(getattr(signal, "url", "") or "")
    if key not in competitors:
        competitors[key] = {
            "name": name,
            "url": url,
            "relationship": relationship,
            "_mentions": 0,
            "_relationship_weight": 0.0,
        }
    competitors[key]["_mentions"] += 1
    competitors[key]["_relationship_weight"] = max(
        competitors[key]["_relationship_weight"],
        {"direct competitor": 0.25, "adjacent": 0.1, "potential disruptor": 0.15}.get(relationship, 0.0),
    )
    if relationship == "direct competitor":
        competitors[key]["relationship"] = relationship


def _differentiators(unit: Any) -> list[str]:
    metadata = getattr(unit, "metadata", {}) or {}
    differentiators: list[str] = []
    if isinstance(metadata, dict):
        differentiators.extend(_as_list(metadata.get("differentiators")))
        differentiators.extend(_as_list(metadata.get("key_differentiators")))

    for field in _DIFFERENTIATOR_FIELDS:
        text = str(getattr(unit, field, "") or "").strip()
        if text and text not in differentiators:
            differentiators.append(text)
        if len(differentiators) >= 5:
            break
    return differentiators[:5]


def _as_list(value: Any) -> list[str]:
    if not value:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, (list, tuple, set)):
        return [str(item) for item in value if str(item).strip()]
    return [str(value)]


def _threat_level(competitors: list[dict[str, Any]]) -> str:
    if not competitors:
        return "low"
    direct_count = sum(1 for comp in competitors if comp.get("relationship") == "direct competitor")
    max_overlap = max(_float(comp.get("overlap_score", 0.0)) for comp in competitors)
    if direct_count >= 2 or max_overlap >= 0.8:
        return "high"
    if direct_count == 1 or max_overlap >= 0.55:
        return "medium"
    return "low"


def _positioning_summary(entries: list[dict[str, Any]]) -> dict[str, Any]:
    position_counts = Counter(entry.get("market_position", "unknown") for entry in entries)
    threat_counts = Counter(entry.get("threat_level", "unknown") for entry in entries)
    relationship_counts = Counter(
        comp.get("relationship", "unknown")
        for entry in entries
        for comp in entry.get("competitors", [])
    )
    competitor_names = {
        comp.get("name", "")
        for entry in entries
        for comp in entry.get("competitors", [])
        if comp.get("name")
    }
    return {
        "entry_count": len(entries),
        "competitor_count": len(competitor_names),
        "position_counts": dict(sorted(position_counts.items())),
        "threat_counts": dict(sorted(threat_counts.items())),
        "relationship_counts": dict(sorted(relationship_counts.items())),
    }


def _segment_from_entry(entry: dict[str, Any]) -> str:
    title = str(entry.get("title") or "general")
    return title.split()[0].lower() if title else "general"


def _float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _md(value: Any) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ")
