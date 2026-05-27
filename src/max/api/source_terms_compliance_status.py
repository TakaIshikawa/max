"""JSON API renderer for source terms compliance status."""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Mapping
from datetime import datetime
from typing import Any

from max.api._renderer_utils import as_list, datetime_to_string, source_metadata, strings

SCHEMA_VERSION = "max.api.source_terms_compliance_status.v1"
KIND = "max.api.source_terms_compliance_status"
STATUS_RANK = {"blocked": 0, "review_required": 1, "compliant": 2}


def source_terms_compliance_status_to_json(payload: Mapping[str, Any], *, as_of: str | datetime | None = None) -> str:
    sources = _sources(payload)
    normalized = {"schema_version": SCHEMA_VERSION, "kind": KIND, "summary": _summary(sources), "sources": sources, "status_totals": _status_totals(sources), "metadata": source_metadata(payload, as_of=datetime_to_string(as_of) if isinstance(as_of, datetime) else as_of, source_count=len(sources))}
    return json.dumps(normalized, indent=2, sort_keys=True)


def _sources(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    source = payload.get("sources") if isinstance(payload.get("sources"), list) else payload.get("compliance")
    rows = [_source(item, index) for index, item in enumerate(source if isinstance(source, list) else [], start=1) if isinstance(item, Mapping)]
    return sorted(rows, key=lambda row: (STATUS_RANK[row["status"]], row["source"], row["adapter"]))


def _source(item: Mapping[str, Any], index: int) -> dict[str, Any]:
    terms = _text(item.get("terms_version"))
    accepted = _text(item.get("accepted_version"))
    blockers = strings(item.get("blockers"))
    reviewed = _text(item.get("last_reviewed_at"))
    status = _status(item.get("status"), terms, accepted, reviewed, blockers)
    return {"source": _text(item.get("source")) or f"source-{index}", "adapter": _text(item.get("adapter")) or "unknown-adapter", "terms_version": terms or None, "accepted_version": accepted or None, "last_reviewed_at": reviewed or None, "data_use_scope": strings(item.get("data_use_scope") if "data_use_scope" in item else as_list(item.get("scope"))), "blockers": blockers, "status": status}


def _status(value: Any, terms: str, accepted: str, reviewed: str, blockers: list[str]) -> str:
    explicit = _bucket(value, "")
    if explicit in STATUS_RANK:
        return explicit
    if blockers:
        return "blocked"
    if not reviewed or terms != accepted:
        return "review_required"
    return "compliant"


def _summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    counts = Counter(row["status"] for row in rows)
    return {"status": "blocked" if counts["blocked"] else ("review_required" if counts["review_required"] else "compliant"), "source_count": len(rows), "blocked_count": counts["blocked"], "review_required_count": counts["review_required"]}


def _status_totals(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    counts = Counter(row["status"] for row in rows)
    return [{"status": status, "source_count": counts[status]} for status in ("blocked", "review_required", "compliant")]


def _bucket(value: Any, default: str) -> str:
    return (_text(value) or default).lower().replace(" ", "_")


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
