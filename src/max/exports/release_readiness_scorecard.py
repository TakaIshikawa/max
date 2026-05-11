"""Release readiness scorecard export for launch planning."""

from __future__ import annotations

import csv
import io
import json
from collections import Counter
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from max.store.db import Store

SCHEMA_VERSION = "max.release_readiness_scorecard.v1"
KIND = "max.release_readiness_scorecard"

_FIELDS = [
    "idea_id",
    "title",
    "qa_status",
    "docs_status",
    "security_review_status",
    "rollout_status",
    "dependency_risk",
    "open_blockers",
    "launch_date",
    "readiness_score",
    "readiness_band",
]

_STATUS_SCORES = {"complete": 1.0, "passed": 1.0, "ready": 1.0, "approved": 1.0, "in_progress": 0.5, "pending": 0.25, "blocked": 0.0, "failed": 0.0, "missing": 0.0}
_RISK_PENALTY = {"low": 0.0, "medium": 10.0, "high": 25.0, "critical": 40.0, "unknown": 10.0}


def build_release_readiness_scorecard_export(store: Store, domain: str | None = None) -> dict[str, Any]:
    """Evaluate buildable units for release readiness."""
    rows = [_row(unit) for unit in store.get_buildable_units(limit=1000, domain=domain)]
    rows.sort(key=lambda row: (row["readiness_score"] * -1, row["launch_date"] or "9999-99-99", row["title"], row["idea_id"]))
    blockers = [blocker for row in rows for blocker in row["blockers"]]
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": {"project": "max", "entity_type": "release_readiness_scorecard", "domain_filter": domain},
        "summary": {
            "idea_count": len(rows),
            "average_readiness_score": round(sum(row["readiness_score"] for row in rows) / len(rows), 1) if rows else 0.0,
            "ready_count": sum(1 for row in rows if row["readiness_band"] == "ready"),
            "blocked_count": sum(1 for row in rows if row["readiness_band"] == "blocked"),
            "blocker_count": len(blockers),
        },
        "status_rollups": _status_rollups(rows),
        "blockers": blockers,
        "ideas": rows,
    }


def render_release_readiness_scorecard_markdown(report: dict[str, Any]) -> str:
    summary = report.get("summary", {})
    lines = [
        "# Release Readiness Scorecard",
        "",
        f"Schema: `{report['schema_version']}`",
        f"Generated: {report['generated_at']}",
        "",
        "## Summary",
        "",
        f"- Ideas analyzed: {summary.get('idea_count', 0)}",
        f"- Average readiness score: {summary.get('average_readiness_score', 0.0):.1f}",
        f"- Ready ideas: {summary.get('ready_count', 0)}",
        f"- Blocked ideas: {summary.get('blocked_count', 0)}",
        "",
        "## Blockers",
        "",
    ]
    for blocker in report.get("blockers", []) or [{"title": "No launch blockers identified", "blocker": ""}]:
        lines.append(f"- {blocker['title']}: {blocker['blocker']}".rstrip(": "))
    lines.extend(["", "## Readiness Table", "", "| Idea | Score | Band | QA | Docs | Security | Rollout | Risk | Launch |", "|------|-------|------|----|------|----------|---------|------|--------|"])
    for row in report.get("ideas", []):
        lines.append(f"| {row['title']} | {row['readiness_score']:.1f} | {row['readiness_band']} | {row['qa_status']} | {row['docs_status']} | {row['security_review_status']} | {row['rollout_status']} | {row['dependency_risk']} | {row['launch_date'] or 'unknown'} |")
    return "\n".join(lines).rstrip() + "\n"


def render_release_readiness_scorecard_json(report: dict[str, Any]) -> str:
    return json.dumps(report, indent=2, sort_keys=True, default=str)


def render_release_readiness_scorecard_csv(report: dict[str, Any]) -> str:
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=_FIELDS)
    writer.writeheader()
    for row in report.get("ideas", []):
        writer.writerow({field: row.get(field) for field in _FIELDS})
    return output.getvalue()


def _row(unit: Any) -> dict[str, Any]:
    metadata = _metadata(unit)
    qa = _status(metadata, "qa_status")
    docs = _status(metadata, "docs_status")
    security = _status(metadata, "security_review_status")
    rollout = _status(metadata, "rollout_status")
    risk = _string(metadata, "dependency_risk", "unknown").lower()
    open_blockers = _blockers(metadata.get("open_blockers"))
    status_score = sum(_STATUS_SCORES.get(status, 0.0) for status in (qa, docs, security, rollout)) / 4 * 100
    score = max(0.0, status_score - _RISK_PENALTY.get(risk, 10.0) - len(open_blockers) * 10)
    row_blockers = [{"idea_id": str(getattr(unit, "id", "")), "title": str(getattr(unit, "title", "Untitled")), "blocker": blocker} for blocker in open_blockers]
    return {
        "idea_id": str(getattr(unit, "id", "")),
        "title": str(getattr(unit, "title", "Untitled")),
        "qa_status": qa,
        "docs_status": docs,
        "security_review_status": security,
        "rollout_status": rollout,
        "dependency_risk": risk,
        "open_blockers": len(open_blockers),
        "blockers": row_blockers,
        "launch_date": _string(metadata, "launch_date", "") or None,
        "readiness_score": round(score, 1),
        "readiness_band": _band(score, open_blockers),
    }


def _status_rollups(rows: list[dict[str, Any]]) -> dict[str, dict[str, int]]:
    return {
        field: dict(sorted(Counter(row[field] for row in rows).items()))
        for field in ("qa_status", "docs_status", "security_review_status", "rollout_status")
    }


def _band(score: float, blockers: list[str]) -> str:
    if blockers or score < 50:
        return "blocked"
    if score >= 85:
        return "ready"
    if score >= 70:
        return "watch"
    return "at_risk"


def _metadata(unit: Any) -> dict[str, Any]:
    metadata = getattr(unit, "metadata", None)
    return metadata if isinstance(metadata, dict) else {}


def _status(metadata: dict[str, Any], key: str) -> str:
    return _string(metadata, key, "missing").lower()


def _string(metadata: dict[str, Any], key: str, default: str) -> str:
    value = metadata.get(key, default)
    return str(value).strip() if value not in (None, "") else default


def _blockers(value: Any) -> list[str]:
    if value in (None, "", 0):
        return []
    if isinstance(value, list):
        return [str(item) for item in value if str(item).strip()]
    if isinstance(value, (int, float)):
        return [f"{int(value)} unresolved blocker(s)"] if value > 0 else []
    return [str(value)]
