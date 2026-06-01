"""Generate deterministic embedding index snapshot restore plans."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from max.spec._planning_common import compact


SCHEMA_VERSION = "max.spec.embedding_index_snapshot_restore_plan.v1"
KIND = "max.spec.embedding_index_snapshot_restore_plan"


def generate_embedding_index_snapshot_restore_plan(
    indexes: Any,
    snapshots: Any,
    *,
    verification_queries: Any = None,
) -> dict[str, Any]:
    index_rows = _indexes(indexes)
    snapshot_rows = _snapshots(snapshots)
    selections = [_selection(index, snapshot_rows) for index in index_rows]
    blockers = _blockers(selections)
    queries = _queries(verification_queries)

    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "summary": {
            "index_count": len(index_rows),
            "snapshot_count": len(snapshot_rows),
            "selected_snapshot_count": sum(1 for item in selections if item["snapshot_id"]),
            "blocker_count": len(blockers),
            "status": "blocked" if blockers else "ready",
        },
        "indexes": index_rows,
        "snapshot_selection": selections,
        "blockers": blockers,
        "compatibility_checks": [
            _row("EISRCC", 1, "dimension compatibility", "search_platform_owner", "Confirm snapshot dimensions match the target index embedding dimension."),
            _row("EISRCC", 2, "model compatibility", "search_platform_owner", "Confirm snapshot embedding model matches the target index model when model metadata is present."),
            _row("EISRCC", 3, "schema compatibility", "data_owner", "Confirm namespace, document schema, and metadata filters are compatible with restore tooling."),
        ],
        "restore_steps": [
            _row("EISRR", 1, "freeze writes", "search_platform_owner", "Freeze writes and capture current index aliases before restore."),
            _row("EISRR", 2, "restore selected snapshots", "search_platform_owner", "Restore each selected compatible snapshot into a shadow index."),
            _row("EISRR", 3, "promote aliases", "release_manager", "Promote restored shadow indexes after compatibility and query verification pass."),
        ],
        "verification_queries": queries,
        "rollback": [
            _row("EISRX", 1, "restore previous aliases", "release_manager", "Rollback by restoring the pre-restore aliases and preserving failed restore artifacts for review."),
            _row("EISRX", 2, "resume writes", "search_platform_owner", "Resume writes only after alias, document count, and retrieval checks are back to the previous healthy state."),
        ],
    }


def _indexes(value: Any) -> list[dict[str, Any]]:
    raw = value if isinstance(value, list) else ([value] if isinstance(value, dict) else [])
    rows = []
    for index, item in enumerate(raw, start=1):
        record = item if isinstance(item, dict) else {"name": item}
        name = compact(record.get("name") or record.get("index") or record.get("namespace")) or f"index-{index}"
        rows.append(
            {
                "id": f"EISRI{index}",
                "name": name,
                "dimension": _int(record.get("dimension") or record.get("dimensions")),
                "embedding_model": compact(record.get("embedding_model") or record.get("model")),
                "namespace": compact(record.get("namespace")),
                "owner": compact(record.get("owner")) or "search_platform_owner",
            }
        )
    return sorted(rows, key=lambda row: row["name"].casefold())


def _snapshots(value: Any) -> list[dict[str, Any]]:
    raw = value if isinstance(value, list) else ([value] if isinstance(value, dict) else [])
    rows = []
    for index, item in enumerate(raw, start=1):
        record = item if isinstance(item, dict) else {"snapshot_id": item}
        snapshot_id = compact(record.get("snapshot_id") or record.get("id") or record.get("name")) or f"snapshot-{index}"
        rows.append(
            {
                "id": f"EISRS{index}",
                "snapshot_id": snapshot_id,
                "index": compact(record.get("index") or record.get("index_name") or record.get("target_index")),
                "dimension": _int(record.get("dimension") or record.get("dimensions")),
                "embedding_model": compact(record.get("embedding_model") or record.get("model")),
                "created_at": compact(record.get("created_at") or record.get("timestamp") or record.get("date")),
                "created_rank": _time_rank(record.get("created_at") or record.get("timestamp") or record.get("date")),
            }
        )
    return sorted(rows, key=lambda row: (row["index"].casefold(), -row["created_rank"], row["snapshot_id"].casefold()))


def _selection(index: dict[str, Any], snapshots: list[dict[str, Any]]) -> dict[str, Any]:
    candidates = [snapshot for snapshot in snapshots if not snapshot["index"] or snapshot["index"] == index["name"]]
    compatible = [snapshot for snapshot in candidates if _compatible(index, snapshot)]
    selected = max(compatible, key=lambda snapshot: (snapshot["created_rank"], snapshot["snapshot_id"])) if compatible else None
    return {
        "id": f"EISRSEL{index['id'].removeprefix('EISRI')}",
        "index": index["name"],
        "snapshot_id": selected["snapshot_id"] if selected else "",
        "created_at": selected["created_at"] if selected else "",
        "status": "selected" if selected else "blocked",
        "reason": "latest compatible snapshot selected" if selected else _blocker_reason(index, candidates),
    }


def _compatible(index: dict[str, Any], snapshot: dict[str, Any]) -> bool:
    if index["dimension"] and snapshot["dimension"] and index["dimension"] != snapshot["dimension"]:
        return False
    if index["embedding_model"] and snapshot["embedding_model"] and index["embedding_model"] != snapshot["embedding_model"]:
        return False
    return True


def _blockers(selections: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        _row(
            "EISRB",
            position,
            f"{selection['index']} snapshot restore blocked",
            "search_platform_owner",
            selection["reason"],
            affected_index=selection["index"],
            severity="critical",
        )
        for position, selection in enumerate((item for item in selections if item["status"] == "blocked"), start=1)
    ]


def _blocker_reason(index: dict[str, Any], candidates: list[dict[str, Any]]) -> str:
    if not candidates:
        return f"No snapshot is available for {index['name']}."
    return f"No compatible snapshot is available for {index['name']} with dimension {index['dimension']} and model {index['embedding_model']}."


def _queries(value: Any) -> list[dict[str, Any]]:
    raw = value if isinstance(value, list) else ([value] if value not in (None, "") else ["known-answer query", "empty-result guardrail query"])
    return [
        _row(
            "EISRV",
            index,
            compact(item.get("name") or item.get("query") or item.get("id")) if isinstance(item, dict) else compact(item),
            "quality_owner",
            compact(item.get("description")) if isinstance(item, dict) else f"Run verification query: {compact(item)}.",
            expected_result=compact(item.get("expected_result") or item.get("expected")) if isinstance(item, dict) else "",
        )
        for index, item in enumerate(raw, start=1)
    ]


def _row(prefix: str, index: int, name: str, owner: str, description: str, **extra: Any) -> dict[str, Any]:
    row = {"id": f"{prefix}{index}", "name": name or "unnamed item", "owner": owner, "description": description}
    row.update({key: value for key, value in extra.items() if value not in (None, "", [])})
    return row


def _int(value: Any) -> int:
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return 0


def _time_rank(value: Any) -> float:
    text = compact(value)
    if not text:
        return 0.0
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return datetime(1970, 1, 1, tzinfo=timezone.utc).timestamp()
