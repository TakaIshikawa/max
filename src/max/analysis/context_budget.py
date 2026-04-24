"""Context budget waste report from persisted evidence links."""

from __future__ import annotations

import json
from collections import Counter
from datetime import datetime, timedelta, timezone
from typing import Any

from max import config
from max.llm.client import estimate_text_tokens, estimate_token_cost_usd
from max.store.db import Store


def _parse_dt(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        dt = value
    elif isinstance(value, str):
        try:
            dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    else:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _json_loads(value: Any, default: Any) -> Any:
    if value in (None, ""):
        return default
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return default
    return value


def _signal_timestamp(signal: dict[str, Any]) -> datetime | None:
    return _parse_dt(signal.get("published_at")) or _parse_dt(signal.get("fetched_at"))


def _signal_context_text(signal: dict[str, Any]) -> str:
    tags = _json_loads(signal.get("tags"), [])
    metadata = _json_loads(signal.get("metadata"), {})
    fields = [
        signal.get("title"),
        signal.get("content"),
        signal.get("url"),
        signal.get("author"),
        " ".join(str(tag) for tag in tags) if isinstance(tags, list) else tags,
        json.dumps(metadata, sort_keys=True) if isinstance(metadata, dict) else metadata,
    ]
    return "\n".join(str(field) for field in fields if field)


def _unit_context_text(unit: dict[str, Any]) -> str:
    fields = [
        unit.get("title"),
        unit.get("one_liner"),
        unit.get("problem"),
        unit.get("solution"),
        unit.get("value_proposition"),
        unit.get("evidence_rationale"),
        unit.get("tech_approach"),
    ]
    return "\n".join(str(field) for field in fields if field)


def _adapter_item(adapter: str) -> dict[str, Any]:
    return {
        "source_adapter": adapter,
        "signal_count": 0,
        "estimated_tokens": 0,
        "reused_signal_count": 0,
        "evidence_link_count": 0,
        "average_reuse_count": 0.0,
        "evidence_reuse_rate": 0.0,
        "low_utility_signal_count": 0,
        "low_utility_rate": 0.0,
        "stale_signal_count": 0,
        "stale_rate": 0.0,
        "projected_token_savings": 0,
        "projected_cost_savings_usd": 0.0,
        "candidate_signal_ids": [],
        "reasons": [],
    }


def _fetch_context_rows(store: Store, source_adapter: str | None) -> tuple[list[dict], list[dict], list[dict]]:
    signal_query = """SELECT id, source_adapter, source_type, title, content, url, author,
                             published_at, fetched_at, tags, metadata
                      FROM signals
                      WHERE archived_at IS NULL"""
    params: list[Any] = []
    if source_adapter:
        signal_query += " AND source_adapter = ?"
        params.append(source_adapter)
    signal_rows = [dict(row) for row in store.conn.execute(signal_query, params).fetchall()]

    insight_rows = [
        dict(row)
        for row in store.conn.execute(
            """SELECT id, title, summary, evidence, created_at
               FROM insights
               WHERE archived_at IS NULL"""
        ).fetchall()
    ]
    unit_rows = [
        dict(row)
        for row in store.conn.execute(
            """SELECT id, title, one_liner, problem, solution, value_proposition,
                      evidence_rationale, tech_approach, inspiring_insights,
                      evidence_signals, created_at, updated_at
               FROM buildable_units
               WHERE status != 'archived'"""
        ).fetchall()
    ]
    return signal_rows, insight_rows, unit_rows


def build_context_budget_waste_report(
    store: Store,
    *,
    days: int = 30,
    source_adapter: str | None = None,
    min_reuse_count: int = 1,
) -> dict[str, Any]:
    """Estimate wasted context from source ingestion and evidence packs.

    The report uses only persisted signals, insights, and buildable units. Token
    counts are deterministic approximations intended for relative budgeting.
    """
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(days=days)
    signal_rows, insight_rows, unit_rows = _fetch_context_rows(store, source_adapter)

    signals_by_id = {row["id"]: row for row in signal_rows}
    signal_tokens = {
        signal_id: estimate_text_tokens(_signal_context_text(row))
        for signal_id, row in signals_by_id.items()
    }

    insight_evidence: dict[str, list[str]] = {}
    insight_tokens: dict[str, int] = {}
    signal_reuse_counts: Counter[str] = Counter()

    for row in insight_rows:
        evidence = [
            signal_id
            for signal_id in _json_loads(row.get("evidence"), [])
            if signal_id in signals_by_id
        ]
        insight_evidence[row["id"]] = evidence
        for signal_id in evidence:
            signal_reuse_counts[signal_id] += 1
        insight_tokens[row["id"]] = estimate_text_tokens(
            "\n".join(str(row.get(field) or "") for field in ("title", "summary"))
        )

    evidence_pack_tokens = 0
    evidence_pack_signal_tokens = 0
    for row in unit_rows:
        evidence_signal_ids = [
            signal_id
            for signal_id in _json_loads(row.get("evidence_signals"), [])
            if signal_id in signals_by_id
        ]
        inspiring_insight_ids = _json_loads(row.get("inspiring_insights"), [])

        transitive_signal_ids: set[str] = set(evidence_signal_ids)
        for insight_id in inspiring_insight_ids:
            if insight_id in insight_evidence:
                evidence_pack_tokens += insight_tokens.get(insight_id, 0)
                transitive_signal_ids.update(insight_evidence[insight_id])
        for signal_id in transitive_signal_ids:
            signal_reuse_counts[signal_id] += 1
            evidence_pack_signal_tokens += signal_tokens.get(signal_id, 0)
        evidence_pack_tokens += estimate_text_tokens(_unit_context_text(row))
        evidence_pack_tokens += sum(signal_tokens.get(signal_id, 0) for signal_id in transitive_signal_ids)

    adapters: dict[str, dict[str, Any]] = {}
    for signal_id, row in signals_by_id.items():
        adapter = str(row.get("source_adapter") or "unspecified")
        item = adapters.setdefault(adapter, _adapter_item(adapter))
        tokens = signal_tokens[signal_id]
        reuse_count = signal_reuse_counts[signal_id]
        timestamp = _signal_timestamp(row)
        is_low_utility = reuse_count < min_reuse_count
        is_stale = timestamp is not None and timestamp < cutoff
        is_candidate = is_low_utility or is_stale

        item["signal_count"] += 1
        item["estimated_tokens"] += tokens
        item["evidence_link_count"] += reuse_count
        if reuse_count > 0:
            item["reused_signal_count"] += 1
        if is_low_utility:
            item["low_utility_signal_count"] += 1
        if is_stale:
            item["stale_signal_count"] += 1
        if is_candidate:
            item["projected_token_savings"] += tokens
            item["candidate_signal_ids"].append(signal_id)

    for item in adapters.values():
        signal_count = item["signal_count"]
        if signal_count:
            item["average_reuse_count"] = round(item["evidence_link_count"] / signal_count, 3)
            item["evidence_reuse_rate"] = round(item["reused_signal_count"] / signal_count, 3)
            item["low_utility_rate"] = round(item["low_utility_signal_count"] / signal_count, 3)
            item["stale_rate"] = round(item["stale_signal_count"] / signal_count, 3)
        item["projected_cost_savings_usd"] = estimate_token_cost_usd(
            item["projected_token_savings"],
            0,
            model=config.MODEL,
        )
        if item["low_utility_signal_count"]:
            item["reasons"].append(
                f"{item['low_utility_signal_count']} signal(s) below min_reuse_count={min_reuse_count}"
            )
        if item["stale_signal_count"]:
            item["reasons"].append(f"{item['stale_signal_count']} signal(s) older than {days} days")
        item["candidate_signal_ids"] = sorted(item["candidate_signal_ids"])

    total_signals = len(signals_by_id)
    total_tokens = sum(signal_tokens.values())
    reused_signal_count = sum(1 for signal_id in signals_by_id if signal_reuse_counts[signal_id] > 0)
    low_utility_count = sum(1 for signal_id in signals_by_id if signal_reuse_counts[signal_id] < min_reuse_count)
    stale_count = sum(
        1
        for row in signals_by_id.values()
        if (timestamp := _signal_timestamp(row)) is not None and timestamp < cutoff
    )
    projected_token_savings = sum(item["projected_token_savings"] for item in adapters.values())

    return {
        "generated_at": now.isoformat(),
        "days": days,
        "source_adapter_filter": source_adapter,
        "min_reuse_count": min_reuse_count,
        "cutoff_timestamp": cutoff.isoformat(),
        "total_signals": total_signals,
        "total_estimated_tokens": total_tokens,
        "estimated_context_cost_usd": estimate_token_cost_usd(total_tokens, 0, model=config.MODEL),
        "insight_count": len(insight_rows),
        "idea_count": len(unit_rows),
        "evidence_pack_estimated_tokens": evidence_pack_tokens,
        "evidence_pack_signal_tokens": evidence_pack_signal_tokens,
        "reused_signal_count": reused_signal_count,
        "evidence_link_count": sum(signal_reuse_counts.values()),
        "evidence_reuse_rate": round(reused_signal_count / total_signals, 3) if total_signals else 0.0,
        "low_utility_signal_count": low_utility_count,
        "low_utility_signal_rate": round(low_utility_count / total_signals, 3) if total_signals else 0.0,
        "stale_signal_count": stale_count,
        "stale_signal_rate": round(stale_count / total_signals, 3) if total_signals else 0.0,
        "projected_token_savings": projected_token_savings,
        "projected_cost_savings_usd": estimate_token_cost_usd(
            projected_token_savings,
            0,
            model=config.MODEL,
        ),
        "adapters": sorted(
            adapters.values(),
            key=lambda item: (-int(item["projected_token_savings"]), str(item["source_adapter"])),
        ),
    }
