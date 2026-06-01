"""JSON API renderer for profile secret reference status."""

from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import datetime, timezone
from typing import Any

from max.api._renderer_utils import int_or_zero, list_of_maps, parse_datetime, source_metadata

SCHEMA_VERSION = "max.api.profile_secret_reference_status.v1"
KIND = "max.api.profile_secret_reference_status"
RANK = {"blocked": 0, "missing": 1, "plaintext": 2, "stale": 3, "resolved": 4}


def profile_secret_reference_status_to_json(payload: Mapping[str, Any], *, as_of: datetime | str | None = None) -> str:
    checked_at = parse_datetime(as_of) or parse_datetime(payload.get("as_of")) or datetime.now(timezone.utc)
    stale_days = max(0, int_or_zero(payload.get("stale_secret_days") or payload.get("stale_days") or 90))
    rows = [_secret(row, i, checked_at, stale_days) for i, row in enumerate(_secret_rows(payload), start=1)]
    rows = sorted(rows, key=lambda row: (RANK[row["status"]], row["profile"].casefold(), row["secret_name"].casefold()))
    counts = {name + "_count": sum(1 for row in rows if row["status"] == name) for name in RANK}
    status = "critical" if counts["blocked_count"] or counts["missing_count"] or counts["plaintext_count"] else ("warning" if counts["stale_count"] else "healthy")
    return json.dumps({"schema_version": SCHEMA_VERSION, "kind": KIND, "as_of": _stamp(checked_at), "status": status, "summary": {"secret_reference_count": len(rows), **counts}, "affected_profiles": [row for row in rows if row["status"] != "resolved"], "secret_references": rows, "metadata": source_metadata(payload)}, indent=2, sort_keys=True)


def _secret(item: Mapping[str, Any], index: int, as_of: datetime, stale_days: int) -> dict[str, Any]:
    resolved = bool(item.get("resolved", True))
    required = bool(item.get("required", True))
    plaintext = bool(item.get("plaintext")) or _text(item.get("value_type")).casefold() == "plaintext"
    version_at = parse_datetime(item.get("version_created_at") or item.get("rotated_at") or item.get("updated_at"))
    age = (as_of.date() - version_at.date()).days if version_at else None
    stale = age is not None and age > stale_days
    missing = not resolved or bool(item.get("missing")) or not _text(item.get("env_var") or item.get("reference"))
    status = "blocked" if missing and required else ("missing" if missing else ("plaintext" if plaintext else ("stale" if stale else "resolved")))
    return {"profile": _text(item.get("profile") or item.get("profile_id")) or f"profile-{index}", "secret_name": _text(item.get("secret_name") or item.get("name") or item.get("env_var")) or "unknown", "env_var": _text(item.get("env_var") or item.get("reference")) or None, "required": required, "resolved": resolved and not missing, "plaintext": plaintext, "secret_version": _text(item.get("secret_version") or item.get("version")) or None, "secret_age_days": age, "status": status, "remediation": "create required secret reference" if missing else ("move plaintext value to secret store" if plaintext else ("rotate stale secret version" if stale else "continue monitoring"))}


def _secret_rows(payload: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    direct = list_of_maps(payload.get("secrets") or payload.get("items") or payload.get("rows"))
    if direct:
        return direct
    rows: list[Mapping[str, Any]] = []
    for profile in list_of_maps(payload.get("profiles")):
        secrets = list_of_maps(profile.get("secrets") or profile.get("secret_references"))
        if not secrets:
            rows.append(profile)
            continue
        for secret in secrets:
            merged = dict(secret)
            merged.setdefault("profile", profile.get("profile") or profile.get("profile_id") or profile.get("name"))
            rows.append(merged)
    return rows


def _stamp(value: datetime) -> str:
    return value.isoformat().replace("+00:00", "Z")


def _text(value: Any) -> str:
    text = " ".join(str(value).strip().split()) if value is not None else ""
    return "[redacted]" if text and any(key in text.casefold() for key in ("secret=", "token=", "password=")) else text
