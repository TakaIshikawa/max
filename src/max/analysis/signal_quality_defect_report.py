"""Signal quality defect report over persisted raw signal rows."""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime
from typing import TYPE_CHECKING, Any

from max.sources.registry import list_adapters

if TYPE_CHECKING:
    from max.store.db import Store


SCHEMA_VERSION = "max.signal_quality_defect.v1"
KIND = "max.signal_quality_defect"

_SEVERITY = {
    "missing_url": "critical",
    "duplicate_url": "critical",
    "invalid_timestamp": "critical",
    "missing_title": "warning",
    "empty_content": "warning",
    "unknown_adapter": "warning",
}
_SEVERITY_RANK = {"critical": 0, "warning": 1, "clean": 2}


def build_signal_quality_defect_report(store: "Store", *, limit: int = 500) -> dict[str, Any]:
    """Inspect persisted signals and summarize quality defects by adapter."""
    if limit < 1:
        raise ValueError("limit must be at least 1")

    rows = _signal_rows(store, limit)
    defects = _defects(rows)
    adapters = _adapter_rows(rows, defects)
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "filters": {"limit": limit},
        "summary": _summary(rows, defects, adapters),
        "adapters": adapters,
        "defects": defects,
        "defect_bands": {
            "critical": [row["adapter"] for row in adapters if row["highest_severity"] == "critical"],
            "warning": [row["adapter"] for row in adapters if row["highest_severity"] == "warning"],
            "clean": [row["adapter"] for row in adapters if row["highest_severity"] == "clean"],
        },
        "next_actions": _next_actions(adapters),
    }


def _signal_rows(store: "Store", limit: int) -> list[dict[str, Any]]:
    rows = store.conn.execute(
        """SELECT id, source_adapter, title, content, url, published_at, fetched_at
           FROM signals
           WHERE archived_at IS NULL
           ORDER BY fetched_at DESC, id DESC
           LIMIT ?""",
        (limit,),
    ).fetchall()
    return [dict(row) for row in rows]


def _defects(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    known_adapters = set(list_adapters())
    url_counts = Counter(_clean(row.get("url")) for row in rows if _clean(row.get("url")))
    defects: list[dict[str, Any]] = []
    for row in rows:
        adapter = _adapter(row)
        signal_id = str(row.get("id") or "")
        checks = {
            "missing_url": not _clean(row.get("url")),
            "missing_title": not _clean(row.get("title")),
            "empty_content": not _clean(row.get("content")),
            "invalid_timestamp": not _valid_optional_timestamp(row.get("published_at")) or not _valid_optional_timestamp(row.get("fetched_at")),
            "unknown_adapter": adapter not in known_adapters,
            "duplicate_url": bool(_clean(row.get("url")) and url_counts[_clean(row.get("url"))] > 1),
        }
        for defect_type, failed in checks.items():
            if failed:
                defects.append(
                    {
                        "signal_id": signal_id,
                        "adapter": adapter,
                        "defect_type": defect_type,
                        "severity": _SEVERITY[defect_type],
                        "url": row.get("url") or "",
                    }
                )
    return sorted(defects, key=_defect_sort_key)


def _adapter_rows(rows: list[dict[str, Any]], defects: list[dict[str, Any]]) -> list[dict[str, Any]]:
    signal_counts = Counter(_adapter(row) for row in rows)
    defects_by_adapter: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for defect in defects:
        defects_by_adapter[str(defect["adapter"])].append(defect)

    adapters = set(signal_counts) | set(defects_by_adapter)
    result: list[dict[str, Any]] = []
    for adapter in adapters:
        adapter_defects = defects_by_adapter.get(adapter, [])
        by_type = Counter(str(defect["defect_type"]) for defect in adapter_defects)
        critical = sum(1 for defect in adapter_defects if defect["severity"] == "critical")
        warning = sum(1 for defect in adapter_defects if defect["severity"] == "warning")
        result.append(
            {
                "adapter": adapter,
                "signal_count": signal_counts.get(adapter, 0),
                "defect_count": len(adapter_defects),
                "critical_count": critical,
                "warning_count": warning,
                "defects_by_type": dict(sorted(by_type.items())),
                "highest_severity": "critical" if critical else "warning" if warning else "clean",
            }
        )
    return sorted(result, key=_adapter_sort_key)


def _summary(rows: list[dict[str, Any]], defects: list[dict[str, Any]], adapters: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "signal_count": len(rows),
        "adapter_count": len(adapters),
        "defect_count": len(defects),
        "critical_defect_count": sum(1 for defect in defects if defect["severity"] == "critical"),
        "warning_defect_count": sum(1 for defect in defects if defect["severity"] == "warning"),
        "affected_adapter_count": sum(1 for adapter in adapters if adapter["defect_count"] > 0),
    }


def _next_actions(adapters: list[dict[str, Any]]) -> list[str]:
    if not adapters:
        return ["Fetch signals before reviewing signal quality defects."]
    critical = [adapter for adapter in adapters if adapter["highest_severity"] == "critical"]
    warning = [adapter for adapter in adapters if adapter["highest_severity"] == "warning"]
    if critical:
        return ["Fix critical signal persistence defects for adapters: " + ", ".join(row["adapter"] for row in critical[:3]) + "."]
    if warning:
        return ["Clean warning-level signal metadata defects for adapters: " + ", ".join(row["adapter"] for row in warning[:3]) + "."]
    return ["No signal quality defects found in the sampled rows."]


def _adapter(row: dict[str, Any]) -> str:
    return _clean(row.get("source_adapter")) or "unknown"


def _clean(value: object) -> str:
    return str(value or "").strip()


def _valid_optional_timestamp(value: object) -> bool:
    text = _clean(value)
    if not text:
        return True
    try:
        datetime.fromisoformat(text.replace("Z", "+00:00"))
        return True
    except ValueError:
        return False


def _defect_sort_key(row: dict[str, Any]) -> tuple[Any, ...]:
    return (_SEVERITY_RANK.get(str(row.get("severity")), 99), str(row.get("adapter")), str(row.get("defect_type")), str(row.get("signal_id")))


def _adapter_sort_key(row: dict[str, Any]) -> tuple[Any, ...]:
    return (
        _SEVERITY_RANK.get(str(row.get("highest_severity")), 99),
        -int(row.get("critical_count") or 0),
        -int(row.get("warning_count") or 0),
        -int(row.get("defect_count") or 0),
        str(row.get("adapter") or ""),
    )
