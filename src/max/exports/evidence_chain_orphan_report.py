"""Evidence chain orphan export report."""

from __future__ import annotations

import json
from collections import defaultdict
from typing import Any, Iterable

SCHEMA_VERSION = "max.evidence_chain_orphan_report.v1"
KIND = "max.evidence_chain_orphan_report"
DEFAULT_GENERATED_AT = "2026-05-31T00:00:00+00:00"
SEVERITY_RANK = {"critical": 0, "warn": 1, "ok": 2}


def generate_evidence_chain_orphan_report(records: Iterable[dict[str, Any]], *, generated_at: str = DEFAULT_GENERATED_AT) -> dict[str, Any]:
    artifacts = [_artifact(item, index) for index, item in enumerate(records, start=1)]
    known_ids = {artifact["artifact_id"] for artifact in artifacts}
    rows = []
    for artifact in artifacts:
        missing = [upstream for upstream in artifact["upstream_ids"] if upstream not in known_ids]
        terminal = artifact["downstream_count"] == 0
        if missing or terminal:
            reason = "missing_upstream_and_no_downstream" if missing and terminal else ("missing_upstream" if missing else "no_downstream_consumer")
            severity = "critical" if missing else "warn"
            rows.append({"artifact_id": artifact["artifact_id"], "artifact_type": artifact["artifact_type"], "profile": artifact["profile"], "missing_upstream_ids": missing, "downstream_count": artifact["downstream_count"], "orphan_reason": reason, "severity": severity, "recommended_action": "Restore missing upstream references." if missing else "Attach downstream consumer or mark terminal."})
    rows.sort(key=lambda row: (SEVERITY_RANK[row["severity"]], row["artifact_type"], row["profile"], row["artifact_id"]))
    by_type = defaultdict(int)
    for row in rows:
        by_type[(row["artifact_type"], row["profile"])] += 1
    return {"schema_version": SCHEMA_VERSION, "kind": KIND, "generated_at": generated_at, "summary": {"artifact_count": len(artifacts), "orphan_count": len(rows), "missing_upstream_reference_count": sum(len(row["missing_upstream_ids"]) for row in rows), "terminal_orphan_count": sum(1 for row in rows if row["downstream_count"] == 0)}, "rows": rows, "groups": [{"artifact_type": key[0], "profile": key[1], "orphan_count": count} for key, count in sorted(by_type.items())]}


def render_evidence_chain_orphan_report_json(report: dict[str, Any]) -> str:
    return json.dumps(report, indent=2, sort_keys=True, default=str) + "\n"


def render_evidence_chain_orphan_report_markdown(report: dict[str, Any]) -> str:
    lines = ["# Evidence Chain Orphan Report", "", f"Orphans: {report.get('summary', {}).get('orphan_count', 0)}", ""]
    for row in report.get("rows") or []:
        missing = ", ".join(row["missing_upstream_ids"]) or "none"
        lines.append(f"- {row['artifact_type']} / {row['profile']} / {row['artifact_id']}: {row['orphan_reason']}; missing upstream {missing}; downstream {row['downstream_count']}")
    return "\n".join(lines).rstrip() + "\n"


def _artifact(item: dict[str, Any], index: int) -> dict[str, Any]:
    downstream = _list(item.get("downstream_ids") or item.get("consumers"))
    return {"artifact_id": _text(item.get("artifact_id") or item.get("id")) or f"artifact-{index}", "artifact_type": _text(item.get("artifact_type") or item.get("type")) or "artifact", "profile": _text(item.get("profile") or item.get("domain_profile")) or "default", "upstream_ids": [_text(value) for value in _list(item.get("upstream_ids") or item.get("upstreams")) if _text(value)], "downstream_count": len([value for value in downstream if _text(value)])}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else ([] if value in (None, "") else [value])


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
