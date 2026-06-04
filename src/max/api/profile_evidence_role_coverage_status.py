"""JSON API renderer for profile evidence role coverage status."""

from __future__ import annotations

import json
from collections import defaultdict
from collections.abc import Mapping
from typing import Any

from max.api._renderer_utils import list_of_maps, mapping, source_metadata

SCHEMA_VERSION = "max.api.profile_evidence_role_coverage_status.v1"
KIND = "max.api.profile_evidence_role_coverage_status"
REQUIRED_ROLES = ("problem", "solution", "market")
STATUS_RANK = {"critical": 0, "warning": 1, "ok": 2}


def profile_evidence_role_coverage_status_to_json(records: Any) -> str:
    payload = mapping(records)
    source = payload.get("evidence") or payload.get("records") or payload.get("items") or (records if isinstance(records, list) else [])
    groups: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for item in list_of_maps(source):
        groups[_text(item.get("profile_id") or item.get("profile")) or "unknown"].append(item)
    rows = [_row(profile, evidence) for profile, evidence in groups.items()]
    rows.sort(key=lambda row: (STATUS_RANK[row["status"]], row["coverage_ratio"], row["profile_id"]))
    status = _overall(rows)
    return json.dumps({"schema_version": SCHEMA_VERSION, "kind": KIND, "status": status, "summary": {"profile_count": len(rows), "incomplete_profiles": sum(1 for row in rows if row["status"] != "ok"), "status": status}, "profiles": rows, "metadata": source_metadata(payload, profile_count=len(rows))}, indent=2, sort_keys=True)


def _row(profile: str, evidence: list[Mapping[str, Any]]) -> dict[str, Any]:
    seen: set[tuple[str, str]] = set()
    counts = {role: 0 for role in REQUIRED_ROLES}
    for item in evidence:
        role = _role(item.get("role") or item.get("evidence_role") or item.get("type"))
        if role not in counts:
            continue
        evidence_id = _text(item.get("evidence_id") or item.get("id")) or f"{role}:{len(seen)}"
        key = (role, evidence_id)
        if key not in seen:
            seen.add(key)
            counts[role] += 1
    missing = [role for role in REQUIRED_ROLES if counts[role] == 0]
    ratio = round((len(REQUIRED_ROLES) - len(missing)) / len(REQUIRED_ROLES), 4)
    status = "critical" if len(missing) >= 2 else ("warning" if missing else "ok")
    return {"profile_id": profile, "role_counts": counts, "missing_roles": missing, "coverage_ratio": ratio, "status": status}


def _role(value: Any) -> str:
    return _text(value).casefold().replace("_evidence", "")


def _overall(rows: list[dict[str, Any]]) -> str:
    if any(row["status"] == "critical" for row in rows):
        return "critical"
    if any(row["status"] == "warning" for row in rows):
        return "warning"
    return "ok"


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
