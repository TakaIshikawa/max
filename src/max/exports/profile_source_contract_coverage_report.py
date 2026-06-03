"""Profile source contract coverage export report."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Iterable

SCHEMA_VERSION = "max.profile_source_contract_coverage_report.v1"
KIND = "max.profile_source_contract_coverage_report"
DEFAULT_AS_OF = "2026-06-01T00:00:00+00:00"
STATUS_RANK = {"missing_coverage": 0, "partial_coverage": 1, "stale_verification": 2, "healthy": 3}


def generate_profile_source_contract_coverage_report(
    records: Iterable[dict[str, Any]],
    *,
    as_of: str = DEFAULT_AS_OF,
    stale_after_days: int = 30,
) -> dict[str, Any]:
    checked_at = _datetime(as_of) or _datetime(DEFAULT_AS_OF)
    rows = [_row(raw, index, checked_at, stale_after_days) for index, raw in enumerate(records, start=1) if isinstance(raw, dict)]
    rows.sort(key=lambda row: (row["status_rank"], row["profile"].casefold(), row["source"].casefold()))
    for row in rows:
        row.pop("status_rank", None)
    return {"schema_version": SCHEMA_VERSION, "kind": KIND, "as_of": as_of, "summary": _summary(rows), "source_rows": rows}


def render_profile_source_contract_coverage_report_json(report: dict[str, Any]) -> str:
    return json.dumps(report, indent=2, sort_keys=True)


def render_profile_source_contract_coverage_report_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Profile Source Contract Coverage Report",
        "",
        f"- Profiles: {report['summary']['profile_count']}",
        f"- Sources: {report['summary']['source_count']}",
        f"- Undercovered sources: {report['summary']['undercovered_source_count']}",
        f"- Stale verification: {report['summary']['stale_verification_count']}",
        "",
    ]
    for row in report.get("source_rows", []):
        lines.append(f"- {row['profile']} / {row['source']}: {row['status']} ({row['coverage_ratio']:.4f})")
    return "\n".join(lines)


def _row(raw: dict[str, Any], index: int, as_of: datetime | None, stale_after_days: int) -> dict[str, Any]:
    contract_tests = _int(raw.get("contract_tests") or raw.get("covered_contract_tests"))
    required = _int(raw.get("required_contract_tests") or raw.get("required_tests"))
    verified_at = _text(raw.get("last_verified_at") or raw.get("verified_at"))
    age_days = _age_days(verified_at, as_of)
    stale = age_days is None or age_days > stale_after_days
    status = _status(contract_tests, required, stale)
    return {
        "profile": _text(raw.get("profile") or raw.get("profile_name")) or f"profile-{index}",
        "source": _text(raw.get("source") or raw.get("adapter") or raw.get("source_adapter")) or f"source-{index}",
        "contract_tests": contract_tests,
        "required_contract_tests": required,
        "coverage_ratio": _ratio(contract_tests, required),
        "last_verified_at": verified_at or None,
        "verification_age_days": age_days,
        "stale_verification": stale,
        "status": status,
        "status_rank": STATUS_RANK[status],
    }


def _status(contract_tests: int, required: int, stale: bool) -> str:
    if required > 0 and contract_tests == 0:
        return "missing_coverage"
    if contract_tests < required:
        return "partial_coverage"
    if stale:
        return "stale_verification"
    return "healthy"


def _summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "profile_count": len({row["profile"] for row in rows}),
        "source_count": len({row["source"] for row in rows}),
        "undercovered_source_count": sum(1 for row in rows if row["status"] in {"missing_coverage", "partial_coverage"}),
        "stale_verification_count": sum(1 for row in rows if row["status"] == "stale_verification"),
        "row_count": len(rows),
    }


def _ratio(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 1.0
    return round(min(max(numerator / denominator, 0.0), 1.0), 4)


def _age_days(value: str, as_of: datetime | None) -> int | None:
    checked_at = as_of or _datetime(DEFAULT_AS_OF)
    verified_at = _datetime(value)
    if checked_at is None or verified_at is None:
        return None
    return max(0, (checked_at - verified_at).days)


def _datetime(value: Any) -> datetime | None:
    text = _text(value)
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _int(value: Any) -> int:
    try:
        return max(0, int(float(value or 0)))
    except (TypeError, ValueError):
        return 0


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
