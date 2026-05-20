"""Evidence trace completeness audit for ideas, insights, and signals."""

from __future__ import annotations

import csv
import json
from collections import Counter
from collections.abc import Mapping
from io import StringIO
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from max.store.db import Store


SCHEMA_VERSION = "max.evidence_trace_completeness.v1"
KIND = "max.evidence_trace_completeness"
CSV_COLUMNS = (
    "section",
    "id",
    "title",
    "missing_insight_count",
    "unresolved_insight_count",
    "missing_signal_count",
    "unresolved_signal_count",
    "source_adapter",
    "signal_count",
    "share",
    "risk_level",
)


def build_evidence_trace_completeness_audit(
    store: "Store",
    *,
    limit: int = 500,
    concentration_threshold: float = 0.75,
) -> dict[str, Any]:
    """Audit idea and insight evidence trace completeness."""
    if limit < 1:
        raise ValueError("limit must be at least 1")
    if not 0 < concentration_threshold <= 1:
        raise ValueError("concentration_threshold must be greater than 0 and at most 1")

    ideas = store.get_buildable_units(limit=limit)
    insights = store.get_insights(limit=limit)
    signals = store.get_signals(limit=limit)
    insight_ids = {item.id for item in insights}
    signal_map = {item.id: item for item in signals}

    idea_rows = [_idea_row(unit, insight_ids, signal_map) for unit in ideas]
    insight_rows = [_insight_row(insight, signal_map) for insight in insights]
    incomplete_ideas = [row for row in sorted(idea_rows, key=_idea_sort_key) if not row["is_complete"]]
    incomplete_insights = [row for row in sorted(insight_rows, key=_insight_sort_key) if not row["is_complete"]]
    concentration = _source_concentration(ideas, signal_map, concentration_threshold)
    complete_ideas = sum(1 for row in idea_rows if row["is_complete"])
    complete_insights = sum(1 for row in insight_rows if row["is_complete"])
    summary = {
        "idea_count": len(idea_rows),
        "complete_idea_count": complete_ideas,
        "idea_completeness_pct": _pct(complete_ideas, len(idea_rows)),
        "insight_count": len(insight_rows),
        "complete_insight_count": complete_insights,
        "insight_completeness_pct": _pct(complete_insights, len(insight_rows)),
        "missing_insight_link_count": sum(row["missing_insight_count"] for row in idea_rows),
        "unresolved_insight_link_count": sum(row["unresolved_insight_count"] for row in idea_rows),
        "missing_signal_link_count": sum(row["missing_signal_count"] for row in idea_rows) + sum(row["missing_signal_count"] for row in insight_rows),
        "unresolved_signal_link_count": sum(row["unresolved_signal_count"] for row in idea_rows) + sum(row["unresolved_signal_count"] for row in insight_rows),
        "source_concentration_risk_count": len(concentration),
    }
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "filters": {"limit": limit, "concentration_threshold": concentration_threshold},
        "summary": summary,
        "incomplete_ideas": incomplete_ideas,
        "incomplete_insights": incomplete_insights,
        "source_concentration": concentration,
        "next_actions": _next_actions(summary, incomplete_ideas, incomplete_insights, concentration),
    }


def render_evidence_trace_completeness_audit(report: Mapping[str, Any], *, fmt: str = "json") -> str:
    """Render evidence trace completeness audit as JSON, Markdown, or CSV."""
    if fmt == "json":
        return json.dumps(report, indent=2, sort_keys=True) + "\n"
    if fmt == "csv":
        return _render_csv(report)
    if fmt != "markdown":
        raise ValueError(f"Unsupported evidence trace completeness audit format: {fmt}")

    summary = _mapping(report.get("summary"))
    lines = [
        "# Evidence Trace Completeness Audit",
        "",
        f"Schema: `{report.get('schema_version')}`",
        f"Idea completeness: {summary.get('idea_completeness_pct', 0.0):.1f}%",
        f"Insight completeness: {summary.get('insight_completeness_pct', 0.0):.1f}%",
        "",
        "## Incomplete Ideas",
        "",
        "| Idea | Missing Insights | Unresolved Insights | Missing Signals | Unresolved Signals |",
        "| --- | ---: | ---: | ---: | ---: |",
    ]
    for row in _list_of_maps(report.get("incomplete_ideas")):
        lines.append(
            "| `{}` | {} | {} | {} | {} |".format(
                row.get("id") or "",
                row.get("missing_insight_count", 0),
                row.get("unresolved_insight_count", 0),
                row.get("missing_signal_count", 0),
                row.get("unresolved_signal_count", 0),
            )
        )
    if not report.get("incomplete_ideas"):
        lines.append("| none | 0 | 0 | 0 | 0 |")
    lines.extend(["", "## Incomplete Insights", ""])
    lines.append("| Insight | Missing Signals | Unresolved Signals |")
    lines.append("| --- | ---: | ---: |")
    for row in _list_of_maps(report.get("incomplete_insights")):
        lines.append("| `{}` | {} | {} |".format(row.get("id") or "", row.get("missing_signal_count", 0), row.get("unresolved_signal_count", 0)))
    if not report.get("incomplete_insights"):
        lines.append("| none | 0 | 0 |")
    lines.extend(["", "## Next Actions", ""])
    actions = report.get("next_actions")
    lines.extend(f"- {item}" for item in actions) if isinstance(actions, list) and actions else lines.append("- None")
    return "\n".join(lines).rstrip() + "\n"


def _render_csv(report: Mapping[str, Any]) -> str:
    output = StringIO()
    writer = csv.DictWriter(output, fieldnames=CSV_COLUMNS, lineterminator="\n")
    writer.writeheader()
    for row in _list_of_maps(report.get("incomplete_ideas")):
        writer.writerow({**{key: row.get(key, "") for key in CSV_COLUMNS}, "section": "idea"})
    for row in _list_of_maps(report.get("incomplete_insights")):
        writer.writerow({**{key: row.get(key, "") for key in CSV_COLUMNS}, "section": "insight"})
    for row in _list_of_maps(report.get("source_concentration")):
        writer.writerow({**{key: row.get(key, "") for key in CSV_COLUMNS}, "section": "source_concentration"})
    return output.getvalue()


def _idea_row(unit: Any, insight_ids: set[str], signal_map: Mapping[str, Any]) -> dict[str, Any]:
    unresolved_insights = [item for item in unit.inspiring_insights if item not in insight_ids]
    unresolved_signals = [item for item in unit.evidence_signals if item not in signal_map]
    missing_insight = 1 if not unit.inspiring_insights else 0
    missing_signal = 1 if not unit.evidence_signals else 0
    return {
        "id": unit.id,
        "title": unit.title,
        "domain": unit.domain or "unspecified",
        "missing_insight_count": missing_insight,
        "unresolved_insight_count": len(unresolved_insights),
        "unresolved_insight_ids": sorted(unresolved_insights),
        "missing_signal_count": missing_signal,
        "unresolved_signal_count": len(unresolved_signals),
        "unresolved_signal_ids": sorted(unresolved_signals),
        "is_complete": not missing_insight and not missing_signal and not unresolved_insights and not unresolved_signals,
    }


def _insight_row(insight: Any, signal_map: Mapping[str, Any]) -> dict[str, Any]:
    unresolved = [item for item in insight.evidence if item not in signal_map]
    missing = 1 if not insight.evidence else 0
    return {
        "id": insight.id,
        "title": insight.title,
        "missing_signal_count": missing,
        "unresolved_signal_count": len(unresolved),
        "unresolved_signal_ids": sorted(unresolved),
        "is_complete": not missing and not unresolved,
    }


def _source_concentration(ideas: list[Any], signal_map: Mapping[str, Any], threshold: float) -> list[dict[str, Any]]:
    counter: Counter[str] = Counter()
    for unit in ideas:
        for signal_id in unit.evidence_signals:
            signal = signal_map.get(signal_id)
            if signal is not None:
                counter[str(signal.source_adapter or "unknown")] += 1
    total = sum(counter.values())
    rows = []
    for adapter, count in counter.items():
        share = count / total if total else 0.0
        if share >= threshold:
            rows.append(
                {
                    "source_adapter": adapter,
                    "signal_count": count,
                    "share": round(share, 3),
                    "risk_level": "high" if share >= 0.9 else "watch",
                }
            )
    return sorted(rows, key=lambda row: (-float(row["share"]), -int(row["signal_count"]), str(row["source_adapter"])))


def _next_actions(
    summary: Mapping[str, Any],
    incomplete_ideas: list[dict[str, Any]],
    incomplete_insights: list[dict[str, Any]],
    concentration: list[dict[str, Any]],
) -> list[str]:
    actions = []
    if incomplete_ideas:
        actions.append(f"Attach or repair evidence links for {len(incomplete_ideas)} incomplete idea(s).")
    if incomplete_insights:
        actions.append(f"Attach or repair signal evidence for {len(incomplete_insights)} incomplete insight(s).")
    if concentration:
        actions.append("Diversify evidence sources for concentrated adapters before publication approval.")
    if not actions and summary.get("idea_count", 0):
        actions.append("Evidence traces are complete for analyzed ideas and insights.")
    return actions or ["Create ideas, insights, and signals before auditing trace completeness."]


def _idea_sort_key(row: Mapping[str, Any]) -> tuple[int, int, str]:
    missing = int(row.get("missing_insight_count", 0)) + int(row.get("missing_signal_count", 0))
    unresolved = int(row.get("unresolved_insight_count", 0)) + int(row.get("unresolved_signal_count", 0))
    return (-(missing + unresolved), -unresolved, str(row.get("id") or ""))


def _insight_sort_key(row: Mapping[str, Any]) -> tuple[int, int, str]:
    missing = int(row.get("missing_signal_count", 0))
    unresolved = int(row.get("unresolved_signal_count", 0))
    return (-(missing + unresolved), -unresolved, str(row.get("id") or ""))


def _pct(part: int, whole: int) -> float:
    return round(part / whole * 100, 1) if whole else 100.0


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _list_of_maps(value: Any) -> list[Mapping[str, Any]]:
    return [item for item in value if isinstance(item, Mapping)] if isinstance(value, list) else []
