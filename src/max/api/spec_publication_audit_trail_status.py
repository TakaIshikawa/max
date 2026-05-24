"""JSON API renderer for spec publication audit trail status."""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from collections.abc import Mapping
from datetime import datetime
from typing import Any

from max.api._renderer_utils import as_list, datetime_to_string, source_metadata

SCHEMA_VERSION = "max.api.spec_publication_audit_trail_status.v1"
KIND = "max.api.spec_publication_audit_trail_status"
STATUS_RANK = {"unpublished": 0, "gapped": 1, "complete": 2}


def spec_publication_audit_trail_status_to_json(payload: Mapping[str, Any], *, as_of: str | datetime | None = None) -> str:
    specs = _specs(payload)
    normalized = {"schema_version": SCHEMA_VERSION, "kind": KIND, "summary": _summary(specs), "specs": specs, "destination_totals": _destination_totals(specs), "missing_event_summaries": [row for row in specs if row["missing_events"]], "metadata": source_metadata(payload, as_of=datetime_to_string(as_of) if isinstance(as_of, datetime) else as_of, spec_count=len(specs))}
    return json.dumps(normalized, indent=2, sort_keys=True)


def _specs(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    source = payload.get("specs") if isinstance(payload.get("specs"), list) else payload.get("generated_specs")
    rows = [_spec(item, index) for index, item in enumerate(source if isinstance(source, list) else [], start=1) if isinstance(item, Mapping)]
    return sorted(rows, key=lambda row: (STATUS_RANK[row["status"]], row["spec_id"]))


def _spec(item: Mapping[str, Any], index: int) -> dict[str, Any]:
    events = {_text(value).lower() for value in as_list(item.get("audit_events", item.get("events"))) if _text(value)}
    generated = _bool(item.get("generated", item.get("generation_event"))) or "generated" in events or "generation" in events
    published = _bool(item.get("published", item.get("publication_event"))) or "published" in events or "publication" in events
    destinations = _strings(item.get("destination_ids", item.get("destinations")))
    missing = [name for name, present in (("generation", generated), ("publication", published)) if not present]
    status = "unpublished" if generated and not published else ("gapped" if missing else "complete")
    if not generated and not published:
        status = "unpublished"
    return {"spec_id": _text(item.get("spec_id") or item.get("id")) or f"spec-{index}", "actor": _text(item.get("actor") or item.get("actor_id")) or "unknown-actor", "destination_ids": destinations, "audit_events": sorted(events), "missing_events": missing, "status": status}


def _summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    counts = Counter(row["status"] for row in rows)
    return {"spec_count": len(rows), "complete_count": counts["complete"], "gapped_count": counts["gapped"], "unpublished_count": counts["unpublished"]}


def _destination_totals(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        for destination in row["destination_ids"] or ["unknown-destination"]:
            grouped[destination].append(row)
    return [{"destination_id": key, "spec_count": len(items), "complete_count": sum(1 for item in items if item["status"] == "complete")} for key, items in sorted(grouped.items())]


def _bool(value: Any) -> bool:
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y"}
    return bool(value)


def _strings(value: Any) -> list[str]:
    return sorted({_text(item) for item in as_list(value) if _text(item)})


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""

