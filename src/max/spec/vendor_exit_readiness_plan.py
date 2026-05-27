"""Deterministic vendor exit readiness plan generator."""

from __future__ import annotations

from typing import Any


def generate_vendor_exit_readiness_plan(inputs: dict[str, Any]) -> str:
    vendors = inputs.get("vendors") if isinstance(inputs, dict) else []
    rows = sorted([v for v in vendors if isinstance(v, dict)], key=lambda v: str(v.get("name") or v.get("vendor") or "").lower())
    lines = ["# Vendor Exit Readiness Plan", ""]
    sections = [
        "Vendor Inventory",
        "Replacement Options",
        "Data Export and Verification",
        "Contract Notice Dates",
        "Operational Cutover",
        "Residual Risks",
        "Owner Checklist",
    ]
    for section in sections:
        lines.extend([f"## {section}", ""])
        if not rows:
            lines.extend(["- No vendors supplied.", ""])
            continue
        for vendor in rows:
            name = _text(vendor.get("name") or vendor.get("vendor"), "Unnamed vendor")
            owner = _text(vendor.get("owner"), "Unassigned")
            severity = _text(vendor.get("severity"), "standard").lower()
            replacement = _text(vendor.get("replacement") or vendor.get("replacement_path"), "No replacement path defined")
            risk = "High" if severity == "critical" or replacement == "No replacement path defined" else "Normal"
            if section == "Vendor Inventory":
                lines.append(f"- {name}: owner {owner}; severity {severity}; exit risk {risk}.")
            elif section == "Replacement Options":
                lines.append(f"- {name}: {replacement}.")
            elif section == "Data Export and Verification":
                lines.append(f"- {name}: export {_text(vendor.get('data_export'), 'all retained customer and operational data')}; verify checksums and sample restore.")
            elif section == "Contract Notice Dates":
                lines.append(f"- {name}: notice date {_text(vendor.get('notice_date'), 'TBD')}; contract owner {owner}.")
            elif section == "Operational Cutover":
                lines.append(f"- {name}: freeze writes, migrate integrations, validate replacement, then revoke production access.")
            elif section == "Residual Risks":
                lines.append(f"- {name}: {risk} risk; {_text(vendor.get('risk'), 'track data retention, support handoff, and rollback gaps')}.")
            else:
                lines.append(f"- [ ] {owner}: confirm {name} exit evidence, replacement acceptance, and credential revocation.")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def _text(value: object, fallback: str) -> str:
    text = str(value).strip() if value is not None else ""
    return text or fallback
