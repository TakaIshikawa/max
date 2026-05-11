"""Localization readiness export for international expansion."""

from __future__ import annotations

import csv
import io
import json
from collections import defaultdict
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from max.store.db import Store

SCHEMA_VERSION = "max.localization_readiness.v1"
KIND = "max.localization_readiness"
_FIELDS = ["idea_id", "title", "locale", "market_priority", "readiness_pct", "translation_ready", "currency_ready", "timezone_ready", "docs_ready", "legal_ready", "launch_blockers", "next_action"]


def build_localization_readiness_export(store: Store, domain: str | None = None) -> dict[str, Any]:
    units = store.get_buildable_units(limit=1000, domain=domain)
    rows = [row for unit in units for row in _rows(unit)]
    rows.sort(key=lambda row: (_priority_rank(row["market_priority"]), row["readiness_pct"], row["locale"], row["idea_id"]))
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": {"project": "max", "entity_type": "localization_readiness", "domain_filter": domain},
        "locale_row_count": len(rows),
        "locale_rows": rows,
        "summary": _summary(rows),
    }


def render_localization_readiness_markdown(report: dict[str, Any]) -> str:
    lines = ["# Localization Readiness", "", f"Schema: `{report['schema_version']}`", f"Generated: {report['generated_at']}", "", "## Locale Readiness", "", "| Locale | Unit | Priority | Readiness | Blockers | Next Action |", "|--------|------|----------|-----------|----------|-------------|"]
    for row in report.get("locale_rows", []):
        lines.append(f"| {row['locale']} | {row['title']} | {row['market_priority']} | {row['readiness_pct']:.0f}% | {', '.join(row['launch_blockers']) or 'none'} | {row['next_action']} |")
    lines.extend(["", "## High Priority Blockers", ""])
    blockers = [row for row in report.get("locale_rows", []) if row["market_priority"] == "high" and row["launch_blockers"]]
    if blockers:
        for row in blockers:
            lines.append(f"- {row['title']} {row['locale']}: {', '.join(row['launch_blockers'])}")
    else:
        lines.append("- No high-priority blockers detected.")
    return "\n".join(lines).rstrip() + "\n"


def render_localization_readiness_json(report: dict[str, Any]) -> str:
    return json.dumps(report, indent=2, sort_keys=True, default=str)


def render_localization_readiness_csv(report: dict[str, Any]) -> str:
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=_FIELDS)
    writer.writeheader()
    for row in report.get("locale_rows", []):
        writer.writerow({**{field: row.get(field) for field in _FIELDS}, "launch_blockers": "; ".join(row.get("launch_blockers", []))})
    return output.getvalue()


def _rows(unit: Any) -> list[dict[str, Any]]:
    metadata = _metadata(unit)
    locales = _items(metadata.get("target_locales"))
    translated = set(_items(metadata.get("translated_locales")))
    currency = set(_items(metadata.get("currency_support")))
    timezone = set(_items(metadata.get("timezone_support")))
    docs = set(_items(metadata.get("localized_docs")))
    legal_map = metadata.get("legal_review_status", {})
    priority = str(metadata.get("market_priority") or "medium").lower()
    rows = []
    for locale in locales:
        legal_ready = _legal_ready(legal_map, locale)
        checks = {
            "translation_ready": locale in translated,
            "currency_ready": locale in currency,
            "timezone_ready": locale in timezone,
            "docs_ready": locale in docs,
            "legal_ready": legal_ready,
        }
        blockers = [name.replace("_ready", "") for name, ready in checks.items() if not ready]
        rows.append({
            "idea_id": str(getattr(unit, "id", "")),
            "title": str(getattr(unit, "title", "Untitled")),
            "locale": locale,
            "market_priority": priority,
            **checks,
            "readiness_pct": round((sum(1 for ready in checks.values() if ready) / 5) * 100, 1),
            "launch_blockers": blockers,
            "next_action": _next_action(blockers),
        })
    return rows


def _summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    by_locale: dict[str, list[dict[str, Any]]] = defaultdict(list)
    by_priority: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        by_locale[row["locale"]].append(row)
        by_priority[row["market_priority"]].append(row)
    return {
        "by_locale": [{"locale": locale, "unit_count": len(items), "average_readiness_pct": round(sum(row["readiness_pct"] for row in items) / len(items), 1)} for locale, items in sorted(by_locale.items())],
        "by_market_priority": [{"market_priority": priority, "unit_count": len(items), "average_readiness_pct": round(sum(row["readiness_pct"] for row in items) / len(items), 1)} for priority, items in sorted(by_priority.items())],
    }


def _items(value: Any) -> list[str]:
    if isinstance(value, dict):
        return [str(key) for key, enabled in value.items() if _bool(enabled)]
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str):
        return [part.strip() for part in value.split(",") if part.strip()]
    return []


def _legal_ready(value: Any, locale: str) -> bool:
    if isinstance(value, dict):
        return str(value.get(locale, "")).lower() in {"approved", "complete", "ready", "true"}
    return str(value).lower() in {"approved", "complete", "ready", "true"}


def _next_action(blockers: list[str]) -> str:
    if not blockers:
        return "Ready for launch review"
    return f"Resolve {blockers[0]} coverage"


def _metadata(unit: Any) -> dict[str, Any]:
    metadata = getattr(unit, "metadata", None)
    return metadata if isinstance(metadata, dict) else {}


def _bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).lower() in {"true", "1", "yes", "ready", "supported", "complete", "approved"}


def _priority_rank(value: str) -> int:
    return {"high": 0, "medium": 1, "low": 2}.get(value, 3)
