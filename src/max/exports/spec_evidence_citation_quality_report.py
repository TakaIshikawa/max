"""Spec evidence citation quality export report."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Iterable

SCHEMA_VERSION = "max.spec_evidence_citation_quality_report.v1"
KIND = "max.spec_evidence_citation_quality_report"
DEFAULT_AS_OF = "2026-06-07"


def generate_spec_evidence_citation_quality_report(records: Iterable[dict[str, Any]], *, stale_after_days: int = 90, minimum_citation_count: int = 1, as_of: str = DEFAULT_AS_OF) -> dict[str, Any]:
    today = _date(as_of) or date(2026, 6, 7)
    rows = []
    for index, raw in enumerate(records):
        citations = _items(raw.get("citations") or raw.get("evidence"))
        citation_count = _int(raw.get("citation_count")) or len(citations)
        missing = _int(raw.get("missing_citation_count"))
        stale = _int(raw.get("stale_citation_count")) or sum(1 for item in citations if _is_stale(item, today=today, stale_after_days=stale_after_days))
        unsupported = _int(raw.get("unsupported_criteria_count") or raw.get("unsupported_acceptance_criteria_count"))
        if citation_count < minimum_citation_count:
            missing = max(missing, minimum_citation_count - citation_count)
        status = "blocked" if missing or unsupported else "warning" if stale else "ok"
        rows.append({"spec_id": _text(raw.get("spec_id") or raw.get("id")) or f"spec-{index + 1}", "citation_count": citation_count, "missing_citation_count": missing, "stale_citation_count": stale, "unsupported_criteria_count": unsupported, "status": status})
    rows.sort(key=lambda row: ({"blocked": 0, "warning": 1, "ok": 2}[row["status"]], row["spec_id"].lower()))
    return {"schema_version": SCHEMA_VERSION, "kind": KIND, "summary": {"spec_count": len(rows), "blocked_count": sum(1 for row in rows if row["status"] == "blocked"), "warning_count": sum(1 for row in rows if row["status"] == "warning"), "stale_after_days": stale_after_days, "minimum_citation_count": minimum_citation_count}, "rows": rows}


def _is_stale(value: Any, *, today: date, stale_after_days: int) -> bool:
    cited_at = _date(value.get("cited_at") or value.get("created_at") or value.get("date")) if isinstance(value, dict) else None
    return bool(cited_at and (today - cited_at).days > stale_after_days)


def _date(value: Any) -> date | None:
    text = _text(value)
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).date()
    except ValueError:
        return None


def _items(value: Any) -> list[Any]:
    if value is None or value == "":
        return []
    return list(value) if isinstance(value, (list, tuple, set)) else [value]


def _int(value: Any) -> int:
    try:
        return max(0, int(float(value)))
    except (TypeError, ValueError):
        return 0


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
