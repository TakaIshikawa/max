"""Feedback reviewer agreement export report."""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from itertools import combinations
from typing import Any, Iterable

SCHEMA_VERSION = "max.feedback_reviewer_agreement_report.v1"
KIND = "max.feedback_reviewer_agreement_report"
DEFAULT_GENERATED_AT = "2026-05-31T00:00:00+00:00"


def generate_feedback_reviewer_agreement_report(records: Iterable[dict[str, Any]], *, generated_at: str = DEFAULT_GENERATED_AT) -> dict[str, Any]:
    items: dict[tuple[str, str], list[dict[str, str]]] = defaultdict(list)
    for index, item in enumerate(records, start=1):
        profile = _text(item.get("profile")) or "default"
        entity = _text(item.get("reviewed_entity_id") or item.get("entity_id") or item.get("spec_id") or item.get("idea_id")) or f"item-{index}"
        items[(profile, entity)].append({"reviewer": _text(item.get("reviewer") or item.get("reviewer_id")) or f"reviewer-{index}", "label": _text(item.get("label") or item.get("decision") or item.get("rating")).lower() or "unlabeled"})
    pair_stats: dict[tuple[str, str, str], list[bool]] = defaultdict(list)
    disputed = []
    insufficient = []
    for (profile, entity), labels in items.items():
        if len(labels) < 2:
            insufficient.append({"profile": profile, "item_id": entity})
            continue
        label_set = {label["label"] for label in labels}
        if len(label_set) > 1:
            disputed.append({"profile": profile, "item_id": entity, "labels": sorted(label_set)})
        for left, right in combinations(sorted(labels, key=lambda value: value["reviewer"]), 2):
            pair = tuple(sorted((left["reviewer"], right["reviewer"])))
            pair_stats[(profile, pair[0], pair[1])].append(left["label"] == right["label"])
    rows = [{"profile": profile, "reviewer_a": a, "reviewer_b": b, "review_count": len(values), "agreement_count": sum(values), "agreement_percent": round(sum(values) / len(values) * 100, 2), "disputed_count": len(values) - sum(values)} for (profile, a, b), values in pair_stats.items()]
    rows.sort(key=lambda row: (row["agreement_percent"], row["profile"], row["reviewer_a"], row["reviewer_b"]))
    disagreements = Counter(label for item in disputed for label in item["labels"])
    return {"schema_version": SCHEMA_VERSION, "kind": KIND, "generated_at": generated_at, "summary": {"reviewed_item_count": len(items), "disputed_count": len(disputed), "insufficient_coverage_count": len(insufficient), "most_common_disagreement_labels": [label for label, _ in disagreements.most_common(5)]}, "rows": rows, "disputed_items": sorted(disputed, key=lambda item: (item["profile"], item["item_id"])), "insufficient_coverage_items": sorted(insufficient, key=lambda item: (item["profile"], item["item_id"]))}


def render_feedback_reviewer_agreement_report_json(report: dict[str, Any]) -> str:
    return json.dumps(report, indent=2, sort_keys=True, default=str) + "\n"


def render_feedback_reviewer_agreement_report_markdown(report: dict[str, Any]) -> str:
    lines = ["# Feedback Reviewer Agreement Report", "", f"Disputed items: {report.get('summary', {}).get('disputed_count', 0)}", ""]
    for row in report.get("rows") or []:
        lines.append(f"- {row['profile']} / {row['reviewer_a']} vs {row['reviewer_b']}: {row['agreement_percent']}% agreement, {row['disputed_count']} disputes")
    for item in report.get("insufficient_coverage_items") or []:
        lines.append(f"- {item['profile']} / {item['item_id']}: insufficient coverage")
    return "\n".join(lines).rstrip() + "\n"


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
