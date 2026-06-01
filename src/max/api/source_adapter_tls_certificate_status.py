"""JSON API renderer for source adapter TLS certificate status."""

from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import datetime, timezone
from typing import Any

from max.api._renderer_utils import int_or_zero, list_of_maps, parse_datetime, source_metadata

SCHEMA_VERSION = "max.api.source_adapter_tls_certificate_status.v1"
KIND = "max.api.source_adapter_tls_certificate_status"
RANK = {"critical": 0, "warning": 1, "healthy": 2, "unknown": 3}


def source_adapter_tls_certificate_status_to_json(
    payload: Mapping[str, Any], *, as_of: datetime | str | None = None
) -> str:
    checked_at = parse_datetime(as_of) or parse_datetime(payload.get("as_of")) or datetime.now(timezone.utc)
    warning_days = max(0, int_or_zero(payload.get("warning_days") or payload.get("expiry_warning_days") or 30))
    rows = [
        _certificate(row, i, checked_at, warning_days)
        for i, row in enumerate(_certificate_rows(payload), start=1)
    ]
    rows = sorted(rows, key=lambda row: (RANK[row["status"]], row["days_until_expiry"] if row["days_until_expiry"] is not None else 10**9, row["adapter"].casefold(), row["source"].casefold()))
    expired = [row for row in rows if row["expired"]]
    expiring = [row for row in rows if row["expiring_soon"]]
    unknown = [row for row in rows if row["status"] == "unknown"]
    status = "critical" if expired else ("warning" if expiring else "healthy")
    if not rows:
        status = "unknown"
    body = {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "generated_at": checked_at.isoformat().replace("+00:00", "Z"),
        "as_of": checked_at.isoformat().replace("+00:00", "Z"),
        "status": status,
        "summary": {
            "adapter_count": len(rows),
            "expired_count": len(expired),
            "expiring_soon_count": len(expiring),
            "healthy_count": sum(1 for row in rows if row["status"] == "healthy"),
            "unknown_count": len(unknown),
            "warning_days": warning_days,
        },
        "affected_adapters": [row for row in rows if row["status"] in {"critical", "warning"}],
        "actions": _actions(expired, expiring, unknown),
        "adapters": rows,
        "metadata": source_metadata(payload),
    }
    return json.dumps(body, indent=2, sort_keys=True)


def _certificate(item: Mapping[str, Any], index: int, as_of: datetime, warning_days: int) -> dict[str, Any]:
    expires_at = parse_datetime(item.get("expires_at") or item.get("not_after") or item.get("valid_until") or item.get("certificate_expires_at"))
    days = (expires_at.date() - as_of.date()).days if expires_at else None
    expired = days is not None and days < 0
    soon = days is not None and 0 <= days <= warning_days
    status = "critical" if expired else ("warning" if soon else ("healthy" if expires_at else "unknown"))
    adapter = _text(item.get("adapter") or item.get("adapter_id") or item.get("source_adapter") or item.get("name")) or f"adapter-{index}"
    return {
        "adapter": adapter,
        "source": _text(item.get("source") or item.get("source_id")) or adapter,
        "certificate_id": _text(item.get("certificate_id") or item.get("cert_id") or item.get("fingerprint")) or "unknown",
        "subject": _text(item.get("subject") or item.get("common_name")) or None,
        "issuer": _text(item.get("issuer")) or None,
        "expires_at": expires_at.isoformat().replace("+00:00", "Z") if expires_at else None,
        "days_until_expiry": days,
        "expired": expired,
        "expiring_soon": soon,
        "status": status,
        "remediation": "replace expired TLS certificate" if expired else ("rotate certificate before expiry" if soon else ("record certificate expiry metadata" if expires_at is None else "continue monitoring")),
    }


def _certificate_rows(payload: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    direct = list_of_maps(payload.get("certificates") or payload.get("items") or payload.get("rows"))
    if direct:
        return direct
    rows: list[Mapping[str, Any]] = []
    for adapter in list_of_maps(payload.get("adapters") or payload.get("sources")):
        certificates = list_of_maps(adapter.get("certificates") or adapter.get("tls_certificates"))
        if not certificates:
            rows.append(adapter)
            continue
        for certificate in certificates:
            merged = dict(certificate)
            merged.setdefault("adapter", adapter.get("adapter") or adapter.get("adapter_id") or adapter.get("name"))
            merged.setdefault("source", adapter.get("source") or adapter.get("source_id"))
            rows.append(merged)
    return rows


def _actions(expired: list[dict[str, Any]], expiring: list[dict[str, Any]], unknown: list[dict[str, Any]]) -> list[str]:
    actions: list[str] = []
    if expired:
        actions.append("replace expired TLS certificates before adapter traffic resumes")
    if expiring:
        actions.append("schedule TLS certificate rotation inside the warning window")
    if unknown:
        actions.append("record certificate expiry metadata for adapters with unknown status")
    return actions or ["continue monitoring adapter TLS certificate expiry"]


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
