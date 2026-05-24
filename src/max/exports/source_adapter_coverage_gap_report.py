"""Source adapter coverage gap export report."""

from __future__ import annotations

import json
from collections import defaultdict
from typing import Any, Iterable, TypedDict

SCHEMA_VERSION = "max.source_adapter_coverage_gap_report.v1"
KIND = "max.source_adapter_coverage_gap_report"
DEFAULT_GENERATED_AT = "2026-05-20T00:00:00+00:00"


class SourceAdapterCoverageGapInput(TypedDict, total=False):
    profile: str
    source: str
    adapter: str
    adapter_name: str
    expected_count: int | float | str
    observed_count: int | float | str
    metadata: dict[str, Any]


def build_source_adapter_coverage_gap_report(
    records: Iterable[SourceAdapterCoverageGapInput | dict[str, Any]],
    *,
    title: str = "Source Adapter Coverage Gap Report",
    generated_at: str = DEFAULT_GENERATED_AT,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    rows = _normalize_records(records)
    missing = [row for row in rows if row["status"] == "missing"]
    under_sampled = [row for row in rows if row["status"] == "under_sampled"]
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "generated_at": _text(generated_at) or DEFAULT_GENERATED_AT,
        "title": _text(title) or "Source Adapter Coverage Gap Report",
        "metadata": dict(metadata or {}),
        "summary": _summary(rows, missing, under_sampled),
        "totals": _totals(rows),
        "coverage_rows": rows,
        "missing_adapters": missing,
        "under_sampled_adapters": under_sampled,
        "next_actions": _next_actions(missing, under_sampled),
    }


def render_source_adapter_coverage_gap_report_markdown(report: dict[str, Any]) -> str:
    summary = report.get("summary", {})
    lines = [
        f"# {report.get('title') or 'Source Adapter Coverage Gap Report'}",
        "",
        "## Summary",
        "",
        f"- Coverage rows: {summary.get('coverage_row_count', 0)}",
        f"- Expected signals: {summary.get('expected_count', 0)}",
        f"- Observed signals: {summary.get('observed_count', 0)}",
        f"- Missing adapters: {summary.get('missing_adapter_count', 0)}",
        f"- Under-sampled adapters: {summary.get('under_sampled_adapter_count', 0)}",
        "",
        "## Gaps",
        "",
    ]
    gaps = list(report.get("missing_adapters") or []) + list(report.get("under_sampled_adapters") or [])
    if gaps:
        for row in gaps[:10]:
            lines.append(f"- {row['profile']} / {row['source']} / {row['adapter']}: {row['status']} gap {row['gap_count']}")
    else:
        lines.append("- No source adapter coverage gaps detected.")
    lines.extend(["", "## Next Actions", ""])
    lines.extend([f"- {item['action']}" for item in report.get("next_actions") or []] or ["- No action needed."])
    return "\n".join(lines).rstrip() + "\n"


def render_source_adapter_coverage_gap_report_json(report: dict[str, Any]) -> str:
    return json.dumps(report, indent=2, sort_keys=True, default=str) + "\n"


def _normalize_records(records: Iterable[SourceAdapterCoverageGapInput | dict[str, Any]]) -> list[dict[str, Any]]:
    rows = [_row(raw, index) for index, raw in enumerate(records)]
    rows.sort(
        key=lambda row: (
            -row["gap_count"],
            row["status_rank"],
            row["profile"].lower(),
            row["source"].lower(),
            row["adapter"].lower(),
            row["_input_order"],
        )
    )
    for row in rows:
        row.pop("_input_order", None)
        row.pop("status_rank", None)
    return rows


def _row(raw: dict[str, Any], index: int) -> dict[str, Any]:
    expected = _int(_first_value(raw, ("expected_count", "configured_count", "target_count")))
    observed = _int(_first_value(raw, ("observed_count", "actual_count", "signal_count")))
    gap = max(expected - observed, 0)
    status = _status(expected, observed)
    return {
        "profile": _text(raw.get("profile") or raw.get("profile_name")) or "Unassigned profile",
        "source": _text(raw.get("source") or raw.get("source_name")) or "Unspecified source",
        "adapter": _text(raw.get("adapter") or raw.get("adapter_name") or raw.get("name")) or "Unspecified adapter",
        "expected_count": expected,
        "observed_count": observed,
        "gap_count": gap,
        "coverage_ratio": _ratio(observed, expected),
        "status": status,
        "metadata": _metadata(raw.get("metadata")),
        "status_rank": {"missing": 0, "under_sampled": 1, "covered": 2}.get(status, 3),
        "_input_order": index,
    }


def _summary(rows: list[dict[str, Any]], missing: list[dict[str, Any]], under_sampled: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "coverage_row_count": len(rows),
        "profile_count": len({row["profile"] for row in rows}),
        "source_count": len({row["source"] for row in rows}),
        "adapter_count": len({row["adapter"] for row in rows}),
        "expected_count": sum(row["expected_count"] for row in rows),
        "observed_count": sum(row["observed_count"] for row in rows),
        "gap_count": sum(row["gap_count"] for row in rows),
        "coverage_ratio": _ratio(sum(row["observed_count"] for row in rows), sum(row["expected_count"] for row in rows)),
        "missing_adapter_count": len(missing),
        "under_sampled_adapter_count": len(under_sampled),
    }


def _totals(rows: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    return {
        "profiles": _group_totals(rows, ("profile",)),
        "sources": _group_totals(rows, ("profile", "source")),
        "adapters": _group_totals(rows, ("profile", "source", "adapter")),
    }


def _group_totals(rows: list[dict[str, Any]], keys: tuple[str, ...]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, ...], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[tuple(row[key] for key in keys)].append(row)
    totals = []
    for values, items in grouped.items():
        expected = sum(row["expected_count"] for row in items)
        observed = sum(row["observed_count"] for row in items)
        total = {key: value for key, value in zip(keys, values)}
        total.update(
            {
                "expected_count": expected,
                "observed_count": observed,
                "gap_count": max(expected - observed, 0),
                "coverage_ratio": _ratio(observed, expected),
                "missing_adapter_count": sum(1 for row in items if row["status"] == "missing"),
                "under_sampled_adapter_count": sum(1 for row in items if row["status"] == "under_sampled"),
            }
        )
        totals.append(total)
    totals.sort(key=lambda row: (-row["gap_count"], *(str(row[key]).lower() for key in keys)))
    return totals


def _next_actions(missing: list[dict[str, Any]], under_sampled: list[dict[str, Any]]) -> list[dict[str, Any]]:
    actions = []
    for row in missing:
        actions.append(
            {
                "type": "restore_missing_adapter",
                "profile": row["profile"],
                "source": row["source"],
                "adapter": row["adapter"],
                "gap_count": row["gap_count"],
                "action": f"Restore or configure {row['adapter']} for {row['profile']} / {row['source']}.",
            }
        )
    for row in under_sampled:
        actions.append(
            {
                "type": "increase_adapter_sampling",
                "profile": row["profile"],
                "source": row["source"],
                "adapter": row["adapter"],
                "gap_count": row["gap_count"],
                "action": f"Increase sampling for {row['adapter']} by {row['gap_count']} signal(s).",
            }
        )
    actions.sort(key=lambda row: (-row["gap_count"], row["profile"].lower(), row["source"].lower(), row["adapter"].lower()))
    return actions


def _status(expected: int, observed: int) -> str:
    if expected > 0 and observed == 0:
        return "missing"
    if observed < expected:
        return "under_sampled"
    return "covered"


def _ratio(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 0.0
    return round(min(max(numerator / denominator, 0.0), 1.0), 4)


def _int(value: Any) -> int:
    try:
        return max(0, int(float(value)))
    except (TypeError, ValueError):
        return 0


def _first_value(raw: dict[str, Any], keys: tuple[str, ...]) -> Any:
    for key in keys:
        if key in raw:
            return raw[key]
    return None


def _metadata(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
