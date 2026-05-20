"""SOC 2 control evidence gap report export."""

from __future__ import annotations

import json
from collections import defaultdict
from typing import Any, Iterable, Literal, TypedDict

SCHEMA_VERSION = "max.soc2_control_evidence_gap.v1"
KIND = "max.soc2_control_evidence_gap"

GapStatus = Literal["missing", "stale", "rejected", "partial", "ready"]
RiskLevel = Literal["critical", "high", "medium", "low", "unknown"]
GroupBy = Literal["domain", "owner"]


class Soc2ControlEvidenceInput(TypedDict, total=False):
    control_id: str
    control: str
    control_name: str
    domain: str
    owner: str
    evidence: str | list[str]
    evidence_name: str
    evidence_status: str
    status: str
    risk: str
    risk_level: str
    due_date: str
    remediation: str | list[str]
    guidance: str


def build_soc2_control_evidence_gap_report(
    records: Iterable[Soc2ControlEvidenceInput | dict[str, Any]],
    *,
    title: str = "SOC 2 Control Evidence Gap Report",
    group_by: GroupBy = "domain",
) -> dict[str, Any]:
    gaps = _normalize_gaps(records)
    groups = _groups(gaps, group_by)
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "title": _text(title) or "SOC 2 Control Evidence Gap Report",
        "group_by": group_by,
        "summary": _summary(gaps, groups),
        "groups": groups,
        "gaps": gaps,
        "fallback_guidance": _fallback_guidance(gaps),
    }


def render_soc2_control_evidence_gap_markdown(report: dict[str, Any]) -> str:
    summary = report.get("summary", {})
    lines = [
        f"# {report.get('title') or 'SOC 2 Control Evidence Gap Report'}",
        "",
        f"Schema: `{report.get('schema_version', SCHEMA_VERSION)}`",
        "",
        "## Summary",
        "",
        f"- Controls with gaps: {summary.get('control_count', 0)}",
        f"- Evidence gaps: {summary.get('gap_count', 0)}",
        f"- Critical/high-risk gaps: {summary.get('critical_high_count', 0)}",
        f"- Missing evidence: {summary.get('missing_count', 0)}",
        f"- Stale evidence: {summary.get('stale_count', 0)}",
        f"- Rejected evidence: {summary.get('rejected_count', 0)}",
        "",
        "## Gap Register",
        "",
    ]
    groups = report.get("groups") or []
    if groups:
        for group in groups:
            lines.extend([f"### {group['name']}", ""])
            for gap in group["gaps"]:
                lines.extend([
                    f"#### {gap['control_id']} - {gap['control_name']}",
                    f"- Domain: {gap['domain']}",
                    f"- Owner: {gap['owner']}",
                    f"- Risk: {gap['risk_level']}",
                    f"- Status: {gap['evidence_status']}",
                    f"- Evidence: {', '.join(gap['evidence']) or 'Unspecified evidence'}",
                    f"- Due date: {gap['due_date'] or 'Unscheduled'}",
                    f"- Remediation: {gap['remediation']}",
                    "",
                ])
    else:
        lines.append("- No SOC 2 evidence gaps were supplied.")
    lines.extend(["", "## Audit Prep Guidance", ""])
    lines.extend(f"- {item}" for item in report.get("fallback_guidance", []))
    return "\n".join(lines).rstrip() + "\n"


def render_soc2_control_evidence_gap_json(report: dict[str, Any]) -> str:
    return json.dumps(report, indent=2, sort_keys=True, default=str) + "\n"


def _normalize_gaps(records: Iterable[Soc2ControlEvidenceInput | dict[str, Any]]) -> list[dict[str, Any]]:
    merged: dict[tuple[str, str], dict[str, Any]] = {}
    for raw in records:
        status = _status(raw.get("evidence_status") or raw.get("status"))
        if status == "ready":
            continue
        control_id = _text(raw.get("control_id") or raw.get("control") or "Unmapped control")
        evidence = _items(raw.get("evidence") or raw.get("evidence_name")) or ["Unspecified evidence"]
        key = (control_id.lower(), "|".join(item.lower() for item in evidence))
        row = {
            "control_id": control_id,
            "control_name": _text(raw.get("control_name") or raw.get("control") or control_id),
            "domain": _text(raw.get("domain") or "Unassigned domain"),
            "owner": _text(raw.get("owner") or "Unassigned"),
            "evidence": evidence,
            "evidence_status": status,
            "risk_level": _risk(raw.get("risk_level") or raw.get("risk")),
            "due_date": _text(raw.get("due_date")),
            "remediation": _remediation(raw),
        }
        existing = merged.get(key)
        if existing is None:
            merged[key] = row
            continue
        existing["control_name"] = min(existing["control_name"], row["control_name"])
        existing["domain"] = _prefer_assigned(existing["domain"], row["domain"], "Unassigned domain")
        existing["owner"] = _prefer_assigned(existing["owner"], row["owner"], "Unassigned")
        existing["evidence_status"] = _worst_status(existing["evidence_status"], row["evidence_status"])
        existing["risk_level"] = _worst_risk(existing["risk_level"], row["risk_level"])
        existing["due_date"] = min(filter(None, [existing["due_date"], row["due_date"]]), default="")
        existing["remediation"] = _prefer_guidance(existing["remediation"], row["remediation"])
    gaps = list(merged.values())
    gaps.sort(key=_gap_sort_key)
    return gaps


def _groups(gaps: list[dict[str, Any]], group_by: GroupBy) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for gap in gaps:
        grouped[gap[group_by]].append(gap)
    rows = [{"name": name, "gap_count": len(items), "gaps": items} for name, items in grouped.items()]
    rows.sort(key=lambda row: (_group_worst_key(row["gaps"]), row["name"].lower()))
    return rows


def _summary(gaps: list[dict[str, Any]], groups: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "control_count": len({gap["control_id"] for gap in gaps}),
        "gap_count": len(gaps),
        "group_count": len(groups),
        "critical_high_count": sum(1 for gap in gaps if gap["risk_level"] in {"critical", "high"}),
        "missing_count": sum(1 for gap in gaps if gap["evidence_status"] == "missing"),
        "stale_count": sum(1 for gap in gaps if gap["evidence_status"] == "stale"),
        "rejected_count": sum(1 for gap in gaps if gap["evidence_status"] == "rejected"),
    }


def _fallback_guidance(gaps: list[dict[str, Any]]) -> list[str]:
    if not gaps:
        return [
            "Confirm each SOC 2 control has a named owner, expected evidence artifact, review cadence, and auditor-ready storage location.",
            "Re-run this export after mapping missing, stale, or rejected evidence items.",
        ]
    guidance = []
    if any(gap["evidence_status"] == "missing" for gap in gaps):
        guidance.append("Collect missing artifacts before auditor walkthrough scheduling.")
    if any(gap["evidence_status"] == "stale" for gap in gaps):
        guidance.append("Refresh stale evidence and record the review date for the current audit period.")
    if any(gap["evidence_status"] == "rejected" for gap in gaps):
        guidance.append("Attach rejection reasons to remediation tickets and request reviewer sign-off after replacement evidence is uploaded.")
    if any(gap["owner"] == "Unassigned" for gap in gaps):
        guidance.append("Assign evidence owners for unowned controls before the next audit prep checkpoint.")
    return guidance or ["Package current evidence for auditor review."]


_STATUS_ORDER = {"missing": 0, "stale": 1, "rejected": 2, "partial": 3, "ready": 4}
_RISK_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3, "unknown": 4}


def _gap_sort_key(gap: dict[str, Any]) -> tuple[int, int, str, str, str]:
    return (
        _RISK_ORDER[gap["risk_level"]],
        _STATUS_ORDER[gap["evidence_status"]],
        gap["due_date"] or "9999-12-31",
        gap["control_id"].lower(),
        "|".join(gap["evidence"]).lower(),
    )


def _group_worst_key(gaps: list[dict[str, Any]]) -> tuple[int, int, str]:
    first = min(gaps, key=_gap_sort_key)
    return (_RISK_ORDER[first["risk_level"]], _STATUS_ORDER[first["evidence_status"]], first["due_date"] or "9999-12-31")


def _status(value: Any) -> GapStatus:
    text = _text(value).lower()
    if text in {"ok", "approved", "complete", "current", "ready"}:
        return "ready"
    if text in {"stale", "expired", "outdated"}:
        return "stale"
    if text in {"rejected", "failed"}:
        return "rejected"
    if text in {"partial", "incomplete"}:
        return "partial"
    return "missing"


def _risk(value: Any) -> RiskLevel:
    text = _text(value).lower()
    if text in _RISK_ORDER:
        return text  # type: ignore[return-value]
    return "unknown"


def _worst_status(left: GapStatus, right: GapStatus) -> GapStatus:
    return left if _STATUS_ORDER[left] <= _STATUS_ORDER[right] else right


def _worst_risk(left: RiskLevel, right: RiskLevel) -> RiskLevel:
    return left if _RISK_ORDER[left] <= _RISK_ORDER[right] else right


def _remediation(raw: Soc2ControlEvidenceInput | dict[str, Any]) -> str:
    explicit = _items(raw.get("remediation") or raw.get("guidance"))
    if explicit:
        return "; ".join(explicit)
    return "Collect replacement evidence, attach reviewer notes, and update the SOC 2 evidence index."


def _prefer_assigned(left: str, right: str, fallback: str) -> str:
    if left == fallback:
        return right
    if right == fallback:
        return left
    return min(left, right)


def _prefer_guidance(left: str, right: str) -> str:
    default = "Collect replacement evidence, attach reviewer notes, and update the SOC 2 evidence index."
    if left == default:
        return right
    if right == default:
        return left
    return min(left, right)


def _items(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return sorted({part.strip() for part in value.replace(";", ",").split(",") if part.strip()})
    if isinstance(value, (list, tuple, set)):
        return sorted({_text(item) for item in value if _text(item)})
    return [_text(value)] if _text(value) else []


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
