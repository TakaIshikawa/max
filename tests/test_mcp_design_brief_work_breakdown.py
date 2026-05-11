from max.analysis.design_brief_work_breakdown import CSV_COLUMNS, KIND, SCHEMA_VERSION
from max.server.mcp_tools import (
    design_brief_work_breakdown_detail,
    get_design_brief_work_breakdown,
)

from tests._design_brief_artifact_endpoint_helpers import assert_mcp_artifact


def test_design_brief_work_breakdown_mcp(tmp_path) -> None:
    assert_mcp_artifact(
        tmp_path,
        tool=get_design_brief_work_breakdown,
        resource=design_brief_work_breakdown_detail,
        kind=KIND,
        schema_version=SCHEMA_VERSION,
        markdown_heading="# Work Breakdown:",
        csv_header=CSV_COLUMNS,
    )
