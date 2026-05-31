"""JSON API renderer for insight synthesis failure rate status."""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Mapping
from typing import Any

from max.api._renderer_utils import int_or_zero, list_of_maps, source_metadata

SCHEMA_VERSION = "max.api.insight_synthesis_failure_rate_status.v1"
KIND = "max.api.insight_synthesis_failure_rate_status"


def insight_synthesis_failure_rate_status_to_json(payload: Mapping[str, Any]) -> str:
    attempts = max(0, int_or_zero(payload.get("attempt_count", payload.get("attempts"))))
    failures = _failures(payload)
    failure_count = sum(row["count"] for row in failures)
    retryable = sum(row["count"] for row in failures if row["retryable"])
    rate = round(failure_count / attempts, 4) if attempts else 0.0
    warn = float(payload.get("warning_rate", 0.05))
    crit = float(payload.get("critical_rate", 0.15))
    status = "critical" if attempts and rate >= crit else ("warning" if attempts and rate >= warn else "healthy")
    normalized = {"schema_version": SCHEMA_VERSION, "kind": KIND, "summary": {"status": status, "attempt_count": attempts, "failure_count": failure_count, "failure_rate": rate, "retryable_failure_count": retryable, "terminal_failure_count": failure_count - retryable}, "failure_reasons": failures, "metadata": source_metadata(payload)}
    return json.dumps(normalized, indent=2, sort_keys=True)


def _failures(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    counts: Counter[tuple[str, bool]] = Counter()
    for item in list_of_maps(payload.get("failures") or payload.get("failure_reasons")):
        counts[(_text(item.get("reason") or item.get("code")) or "unknown", bool(item.get("retryable")))] += max(1, int_or_zero(item.get("count", 1)))
    rows = [{"reason": reason, "retryable": retryable, "count": count} for (reason, retryable), count in counts.items()]
    rows.sort(key=lambda row: (-row["count"], row["reason"], row["retryable"]))
    return rows


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()).lower().replace(" ", "_") if value is not None else ""
