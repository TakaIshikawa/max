from __future__ import annotations

from max.sources.elastic_security_labs import (
    ElasticSecurityLabsAdapter,
    parse_elastic_security_labs,
)
from max.sources.registry import get_adapter, reload_registry


def test_parse_elastic_security_labs_preserves_threat_metadata() -> None:
    payload = [
        {
            "title": "Campaign analysis",
            "url": "https://www.elastic.co/security-labs/campaign-analysis",
            "threat_category": "intrusion",
            "malware_family": "exampleloader",
            "cve_ids": ["CVE-2026-0001"],
            "tactics": ["initial-access"],
            "tags": ["research"],
        }
    ]

    signal = parse_elastic_security_labs(payload)[0]

    assert signal.source_adapter == "elastic_security_labs"
    assert signal.metadata["threat_category"] == "intrusion"
    assert signal.metadata["malware_family"] == "exampleloader"
    assert signal.metadata["cve_ids"] == ["CVE-2026-0001"]
    assert signal.metadata["tactics"] == ["initial-access"]
    assert signal.id == parse_elastic_security_labs(payload)[0].id


def test_elastic_security_labs_registry_instantiates_adapter() -> None:
    reload_registry()
    assert isinstance(get_adapter("elastic_security_labs"), ElasticSecurityLabsAdapter)
