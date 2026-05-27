from __future__ import annotations

from max.spec.data_retention_legal_hold_plan import (
    generate_data_retention_legal_hold_plan,
    render_data_retention_legal_hold_plan_markdown,
)


def test_expired_holds_and_unknown_custodians_are_findings() -> None:
    plan = generate_data_retention_legal_hold_plan(
        {
            "metadata": {
                "data_retention_legal_hold": {
                    "data_domains": [{"domain": "billing exports", "hold_until": "2020-01-01"}],
                    "custodians": [{"name": "unknown"}],
                }
            }
        }
    )

    assert plan["data_domains"][0]["review_status"] == "expired"
    assert plan["custodians"][0]["review_status"] == "unknown"
    assert [item["status"] for item in plan["findings"]] == ["expired", "unknown"]


def test_deletion_policy_conflicts_include_remediation_steps() -> None:
    plan = generate_data_retention_legal_hold_plan(
        {
            "metadata": {
                "data_retention_legal_hold": {
                    "retention_conflicts": [{"policy": "delete support logs after 30 days", "dataset": "support_logs"}]
                }
            }
        }
    )

    assert plan["retention_conflicts"][0]["review_status"] == "conflict"
    assert "pause deletion policy" in plan["retention_conflicts"][0]["remediation"]
    assert plan["findings"][0]["name"] == "delete support logs after 30 days"


def test_legal_hold_domain_ordering_is_deterministic() -> None:
    payload = {
        "metadata": {
            "data_retention_legal_hold": {
                "data_domains": [{"domain": "Zendesk tickets"}, {"domain": "audit logs"}],
            }
        }
    }

    first = generate_data_retention_legal_hold_plan(payload)
    second = generate_data_retention_legal_hold_plan(payload)

    assert [item["name"] for item in first["data_domains"]] == ["audit logs", "Zendesk tickets"]
    assert first == second


def test_legal_hold_markdown_includes_audit_evidence_and_release_criteria() -> None:
    plan = generate_data_retention_legal_hold_plan(
        {
            "project": {"title": "Matter hold"},
            "metadata": {
                "data_retention_legal_hold": {
                    "release_criteria": ["written legal release"],
                    "audit_evidence": ["custodian notice archive"],
                }
            },
        }
    )

    markdown = render_data_retention_legal_hold_plan_markdown(plan)

    assert markdown.startswith("# Matter hold Data Retention Legal Hold Plan")
    assert "## Audit Evidence" in markdown
    assert "custodian notice archive" in markdown
    assert "## Release Criteria" in markdown
    assert "written legal release" in markdown
