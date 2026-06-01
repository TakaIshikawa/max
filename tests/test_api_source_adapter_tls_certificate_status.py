from __future__ import annotations

import json

from max.api import source_adapter_tls_certificate_status_to_json


def test_source_adapter_tls_certificate_status_flags_expired_warning_and_healthy() -> None:
    report = json.loads(
        source_adapter_tls_certificate_status_to_json(
            {
                "warning_days": 30,
                "certificates": [
                    {"adapter": "beta", "source": "crm", "expires_at": "2026-01-01T00:00:00Z"},
                    {"adapter": "alpha", "source": "ads", "expires_at": "2026-06-20T00:00:00Z"},
                    {"adapter": "gamma", "source": "docs", "expires_at": "2026-12-01T00:00:00Z"},
                ],
            },
            as_of="2026-06-01T00:00:00Z",
        )
    )

    assert report["status"] == "critical"
    assert report["summary"]["expired_count"] == 1
    assert report["summary"]["expiring_soon_count"] == 1
    assert [row["adapter"] for row in report["affected_adapters"]] == ["beta", "alpha"]
    assert report["adapters"][0]["status"] == "critical"
    assert report["schema_version"] == "max.api.source_adapter_tls_certificate_status.v1"
    assert report["kind"] == "max.api.source_adapter_tls_certificate_status"


def test_source_adapter_tls_certificate_status_sparse_payload_is_stable() -> None:
    report = json.loads(source_adapter_tls_certificate_status_to_json({}, as_of="2026-06-01T00:00:00Z"))

    assert report["status"] == "unknown"
    assert report["summary"]["adapter_count"] == 0
    assert report["affected_adapters"] == []
    assert report["actions"] == ["continue monitoring adapter TLS certificate expiry"]


def test_source_adapter_tls_certificate_status_warning_and_healthy_statuses_and_shape() -> None:
    warning = json.loads(
        source_adapter_tls_certificate_status_to_json(
            {"certificates": [{"adapter": "alpha", "source": "ads", "expires_at": "2026-06-15T00:00:00Z"}]},
            as_of="2026-06-01T00:00:00Z",
        )
    )
    healthy = json.loads(
        source_adapter_tls_certificate_status_to_json(
            {"adapters": [{"adapter": "beta", "source": "crm", "certificates": [{"expires_at": "2026-12-01T00:00:00Z"}]}]},
            as_of="2026-06-01T00:00:00Z",
        )
    )

    assert warning["status"] == "warning"
    assert warning["summary"]["expiring_soon_count"] == 1
    assert healthy["status"] == "healthy"
    assert healthy["summary"]["healthy_count"] == 1
    assert set(warning) >= {
        "kind",
        "schema_version",
        "generated_at",
        "as_of",
        "status",
        "summary",
        "affected_adapters",
        "actions",
    }


def test_source_adapter_tls_certificate_status_orders_deterministically() -> None:
    report = json.loads(
        source_adapter_tls_certificate_status_to_json(
            {
                "certificates": [
                    {"adapter": "zeta", "source": "crm", "expires_at": "2026-06-10T00:00:00Z"},
                    {"adapter": "alpha", "source": "ads", "expires_at": "2026-05-30T00:00:00Z"},
                    {"adapter": "beta", "source": "docs", "expires_at": "2026-06-05T00:00:00Z"},
                ]
            },
            as_of="2026-06-01T00:00:00Z",
        )
    )

    assert [row["adapter"] for row in report["adapters"]] == ["alpha", "beta", "zeta"]
