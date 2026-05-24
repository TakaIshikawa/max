"""JSON API renderer for adapter credential scope coverage."""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Mapping
from datetime import datetime, timezone
from typing import Any

SCHEMA_VERSION = "max.api.adapter_credential_scope.v1"
KIND = "max.api.adapter_credential_scope"
PRIVILEGED_SCOPES = {"admin", "owner", "write", "delete", "repo", "full_access", "*"}


def adapter_credential_scope_to_json(payload: Mapping[str, Any], *, as_of: str | datetime | None = None) -> str:
    adapters = _adapters(payload)
    normalized = {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "summary": _summary(adapters),
        "adapters": adapters,
        "missing_scope_adapters": [row for row in adapters if row["missing_scopes"]],
        "excessive_scope_adapters": [row for row in adapters if row["excessive_scopes"]],
        "rotation_review_adapters": [row for row in adapters if row["requires_rotation_review"]],
        "metadata": _metadata(payload, adapters, as_of),
    }
    return json.dumps(normalized, indent=2, sort_keys=True)


def _adapters(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    source = payload.get("adapters") if isinstance(payload.get("adapters"), list) else payload.get("credentials")
    rows = [_adapter(item, index) for index, item in enumerate(source if isinstance(source, list) else [], start=1) if isinstance(item, Mapping)]
    rows.sort(key=lambda row: (row["least_privilege"], row["adapter"], row["source"]))
    return rows


def _adapter(item: Mapping[str, Any], index: int) -> dict[str, Any]:
    required = set(_scopes(item.get("required_scopes", item.get("expected_scopes"))))
    granted = set(_scopes(item.get("granted_scopes", item.get("scopes"))))
    missing = sorted(required - granted)
    excessive = sorted(granted - required)
    privileged = sorted(scope for scope in excessive if scope in PRIVILEGED_SCOPES or scope.endswith(":write") or scope.endswith(":admin"))
    rotation = _bool(item.get("requires_rotation_review", item.get("rotation_review"))) or bool(privileged)
    return {
        "adapter": _text(item.get("adapter") or item.get("adapter_name")) or f"adapter-{index}",
        "source": _text(item.get("source") or item.get("source_name")) or "unknown-source",
        "required_scopes": sorted(required),
        "granted_scopes": sorted(granted),
        "missing_scopes": missing,
        "excessive_scopes": excessive,
        "privileged_excessive_scopes": privileged,
        "least_privilege": not missing and not excessive,
        "requires_rotation_review": rotation,
    }


def _summary(adapters: list[dict[str, Any]]) -> dict[str, Any]:
    missing = sum(1 for row in adapters if row["missing_scopes"])
    excessive = sum(1 for row in adapters if row["excessive_scopes"])
    privileged = sum(1 for row in adapters if row["privileged_excessive_scopes"])
    status = "excessive_privileged_scope" if privileged else ("scope_gap" if missing or excessive else "least_privilege")
    return {"status": status, "adapter_count": len(adapters), "least_privilege_count": sum(1 for row in adapters if row["least_privilege"]), "missing_scope_count": missing, "excessive_scope_count": excessive, "privileged_excessive_scope_count": privileged}


def _metadata(payload: Mapping[str, Any], adapters: list[dict[str, Any]], as_of: str | datetime | None) -> dict[str, Any]:
    metadata = dict(payload.get("metadata") if isinstance(payload.get("metadata"), Mapping) else {})
    return {**metadata, "source_schema_version": payload.get("schema_version"), "source_kind": payload.get("kind"), "as_of": _as_of(as_of), "adapter_count": len(adapters)}


def _scopes(value: Any) -> list[str]:
    return sorted({_text(item).lower() for item in value if _text(item)}) if isinstance(value, list) else []


def _bool(value: Any) -> bool:
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y"}
    return bool(value)


def _as_of(value: str | datetime | None) -> str | None:
    if isinstance(value, datetime):
        parsed = value if value.tzinfo else value.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    return value


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
