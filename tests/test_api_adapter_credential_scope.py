from __future__ import annotations

import json

from max.api.adapter_credential_scope import adapter_credential_scope_to_json


def test_adapter_credential_scope_reports_missing_and_excessive_separately() -> None:
    parsed = json.loads(
        adapter_credential_scope_to_json(
            {
                "adapters": [
                    {"adapter": "ok", "required_scopes": ["read"], "granted_scopes": ["read"]},
                    {"adapter": "gap", "required_scopes": ["read", "write"], "granted_scopes": ["read"]},
                    {"adapter": "wide", "required_scopes": ["read"], "granted_scopes": ["read", "admin"]},
                ]
            }
        )
    )

    assert parsed["summary"]["status"] == "excessive_privileged_scope"
    assert parsed["missing_scope_adapters"][0]["missing_scopes"] == ["write"]
    assert parsed["excessive_scope_adapters"][0]["excessive_scopes"] == ["admin"]
    assert parsed["rotation_review_adapters"][0]["adapter"] == "wide"


def test_adapter_credential_scope_marks_least_privilege() -> None:
    parsed = json.loads(adapter_credential_scope_to_json({"credentials": [{"adapter_name": "a", "source_name": "s", "expected_scopes": ["read"], "scopes": ["read"]}]}))

    assert parsed["summary"]["status"] == "least_privilege"
    assert parsed["adapters"][0]["least_privilege"] is True
