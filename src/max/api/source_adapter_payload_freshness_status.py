"""JSON API renderer for source adapter payload freshness status."""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Mapping
from datetime import datetime, timezone
from typing import Any

from max.api._renderer_utils import datetime_to_string, int_or_zero, list_of_maps, parse_datetime, source_metadata

SCHEMA_VERSION = "max.api.source_adapter_payload_freshness_status.v1"
KIND = "max.api.source_adapter_payload_freshness_status"
STATUS_RANK = {"never_fetched": 0, "stale": 1, "fresh": 2}


def source_adapter_payload_freshness_status_to_json(payload: Mapping[str, Any], *, as_of: str | datetime | None = None) -> str:
    now = parse_datetime(as_of) if isinstance(as_of, str) else as_of
    adapters = [_adapter(item, index, payload, now) for index, item in enumerate(list_of_maps(payload.get("adapters") or payload.get("payloads")), start=1)]
    adapters.sort(key=lambda row: (STATUS_RANK[row["status"]], row["adapter"]))
    counts = Counter(row["status"] for row in adapters)
    status = "never_fetched" if counts["never_fetched"] else ("stale" if counts["stale"] else ("fresh" if adapters else "no_data"))
    normalized = {"schema_version": SCHEMA_VERSION, "kind": KIND, "summary": {"status": status, "adapter_count": len(adapters), "stale_payload_count": counts["stale"], "never_fetched_count": counts["never_fetched"]}, "adapters": adapters, "metadata": source_metadata(payload, as_of=datetime_to_string(now) if isinstance(now, datetime) else as_of)}
    return json.dumps(normalized, indent=2, sort_keys=True)


def _adapter(item: Mapping[str, Any], index: int, payload: Mapping[str, Any], as_of: datetime | None) -> dict[str, Any]:
    fetched = parse_datetime(item.get("last_successful_fetch_at") or item.get("last_fetched_at"))
    max_age = int_or_zero(item.get("max_age_minutes", payload.get("max_age_minutes", 60)))
    age = _age_minutes(fetched, as_of)
    status = "never_fetched" if fetched is None else ("stale" if age is not None and max_age and age > max_age else "fresh")
    return {"adapter": _text(item.get("adapter") or item.get("adapter_name")) or f"adapter-{index}", "last_successful_fetch_at": datetime_to_string(fetched), "payload_age_minutes": age, "max_age_minutes": max_age, "status": status}


def _age_minutes(value: datetime | None, as_of: datetime | None) -> int | None:
    if value is None or as_of is None:
        return None
    current = as_of if as_of.tzinfo else as_of.replace(tzinfo=timezone.utc)
    return max(int((current.astimezone(timezone.utc) - value).total_seconds() // 60), 0)


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
