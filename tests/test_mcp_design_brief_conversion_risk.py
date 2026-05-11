from max.analysis.design_brief_conversion_risk import CSV_COLUMNS, KIND, SCHEMA_VERSION
from max.server.mcp_tools import (
    design_brief_conversion_risk_detail,
    get_design_brief_conversion_risk,
)

from tests._design_brief_artifact_endpoint_helpers import assert_mcp_artifact


def test_design_brief_conversion_risk_mcp(tmp_path) -> None:
    assert_mcp_artifact(
        tmp_path,
        tool=get_design_brief_conversion_risk,
        resource=design_brief_conversion_risk_detail,
        kind=KIND,
        schema_version=SCHEMA_VERSION,
        markdown_heading="# Conversion Risk Report:",
        csv_header=CSV_COLUMNS,
    )
