"""Source duplicate signal export report."""

from __future__ import annotations

import json
from collections import defaultdict
from typing import Any, Iterable

SCHEMA_VERSION = "max.source_duplicate_signal_report.v1"
KIND = "max.source_duplicate_signal_report"
DEFAULT_GENERATED_AT = "2026-05-27T00:00:00+00:00"


def build_source_duplicate_signal_report(records: Iterable[dict[str, Any]], *, title: str = "Source Duplicate Signal Report", generated_at: str = DEFAULT_GENERATED_AT) -> dict[str, Any]:
    groups: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    total = 0
    for raw in records:
        if not isinstance(raw, dict):
            continue
        total += 1
        source = _text(raw.get("source")) or "unknown-source"
        key = _text(raw.get("duplicate_key") or raw.get("id") or raw.get("url") or raw.get("content_hash")) or "unknown-key"
        groups[(source, key)].append(raw)
    rows = []
    for (source, key), items in groups.items():
        if len(items) < 2:
            continue
        ids = sorted(_text(item.get("signal_id") or item.get("id")) or f"signal-{i}" for i, item in enumerate(items, 1))
        rows.append({"source": source, "duplicate_key": key, "duplicate_count": len(items), "affected_signal_ids": ids, "canonical_signal_id": ids[0], "deduplication_recommendation": "retain canonical signal and suppress duplicate emissions"})
    rows.sort(key=lambda row: (-row["duplicate_count"], row["source"].lower(), row["duplicate_key"]))
    return {"schema_version": SCHEMA_VERSION, "kind": KIND, "generated_at": _text(generated_at) or DEFAULT_GENERATED_AT, "title": _text(title) or "Source Duplicate Signal Report", "summary": {"signal_count": total, "singleton_count": total - sum(r["duplicate_count"] for r in rows), "duplicate_group_count": len(rows), "duplicate_signal_count": sum(r["duplicate_count"] for r in rows)}, "duplicate_rows": rows}


def render_source_duplicate_signal_report_json(report: dict[str, Any]) -> str:
    return json.dumps(report, indent=2, sort_keys=True, default=str) + "\n"


def render_source_duplicate_signal_report_markdown(report: dict[str, Any]) -> str:
    lines = [f"# {report.get('title') or 'Source Duplicate Signal Report'}", "", "## Duplicates", ""]
    lines.extend([f"- {r['source']} {r['duplicate_key']}: {r['duplicate_count']} signals, canonical {r['canonical_signal_id']}" for r in report.get("duplicate_rows") or []] or ["- No duplicate signals detected."])
    return "\n".join(lines).rstrip() + "\n"


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
