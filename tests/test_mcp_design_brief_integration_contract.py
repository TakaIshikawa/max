from max.analysis.design_brief_integration_contract import (
    INTEGRATION_CONTRACT_CSV_COLUMNS,
    KIND,
    SCHEMA_VERSION,
)
from max.server.mcp_tools import (
    design_brief_integration_contract_detail,
    get_design_brief_integration_contract,
)

from tests._design_brief_artifact_endpoint_helpers import assert_mcp_artifact


def test_design_brief_integration_contract_mcp(tmp_path) -> None:
    assert_mcp_artifact(
        tmp_path,
        tool=get_design_brief_integration_contract,
        resource=design_brief_integration_contract_detail,
        kind=KIND,
        schema_version=SCHEMA_VERSION,
        markdown_heading="# Integration Contract:",
        csv_header=INTEGRATION_CONTRACT_CSV_COLUMNS,
    )
