from max.analysis.design_brief_integration_contract import (
    INTEGRATION_CONTRACT_CSV_COLUMNS,
    KIND,
    SCHEMA_VERSION,
)

from tests._design_brief_artifact_endpoint_helpers import assert_api_artifact


def test_design_brief_integration_contract_api(tmp_path) -> None:
    assert_api_artifact(
        tmp_path,
        path="integration-contract",
        kind=KIND,
        schema_version=SCHEMA_VERSION,
        markdown_heading="# Integration Contract:",
        csv_header=INTEGRATION_CONTRACT_CSV_COLUMNS,
    )
