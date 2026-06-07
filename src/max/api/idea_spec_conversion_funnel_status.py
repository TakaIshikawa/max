"""JSON API renderer for idea-to-spec conversion funnel status."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from max.api._renderer_utils import float_or_zero, int_or_zero, source_metadata

SCHEMA_VERSION = "max.api.idea_spec_conversion_funnel_status.v1"
KIND = "max.api.idea_spec_conversion_funnel_status"


def idea_spec_conversion_funnel_status_to_json(payload: Mapping[str, Any]) -> str:
    generated = max(0, int_or_zero(payload.get("generated_count")))
    evaluated = max(0, int_or_zero(payload.get("evaluated_count")))
    approved = max(0, int_or_zero(payload.get("approved_count")))
    spec_generated = max(0, int_or_zero(payload.get("spec_generated_count")))
    published = max(0, int_or_zero(payload.get("published_count")))
    minimum = _threshold(payload.get("minimum_conversion_rate"), 0.2)
    rate = round(published / generated, 4) if generated else 0.0
    status = "ok" if generated == 0 or rate >= minimum else "warning"
    return json.dumps(
        {
            "schema_version": SCHEMA_VERSION,
            "kind": KIND,
            "status": status,
            "generated_count": generated,
            "evaluated_count": evaluated,
            "approved_count": approved,
            "spec_generated_count": spec_generated,
            "published_count": published,
            "conversion_rate": rate,
            "minimum_conversion_rate": minimum,
            "metadata": source_metadata(payload),
        },
        indent=2,
        sort_keys=True,
    )


def _threshold(value: Any, default: float) -> float:
    parsed = float_or_zero(value if value is not None else default)
    return parsed if parsed > 0 else default
