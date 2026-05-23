from types import SimpleNamespace
from unittest.mock import Mock

from max.exports import (
    build_buildable_unit_stack_diversity_report_export,
    render_buildable_unit_stack_diversity_report_markdown,
)


def test_stack_diversity_report_counts_concentration_and_alternatives():
    store = Mock()
    store.get_buildable_units.return_value = [
        SimpleNamespace(id="u1", title="A", metadata={"language": "Python", "framework": "Django"}),
        SimpleNamespace(id="u2", title="B", metadata={"language": "Python", "framework": "FastAPI"}),
        SimpleNamespace(id="u3", title="C", metadata={"language": "Python", "database": "Postgres"}),
    ]

    report = build_buildable_unit_stack_diversity_report_export(store)

    assert report["summary"]["unit_count"] == 3
    python = report["technology_rows"][0]
    assert python["technology"] == "Python"
    assert python["usage_count"] == 3
    assert python["percentage"] == 100.0
    assert python["categories"] == ["language"]
    assert python["concentration_warning"] == "overused stack"
    assert {row["technology"] for row in report["underrepresented_alternatives"]} >= {"Django", "FastAPI", "Postgres"}


def test_stack_diversity_markdown_shows_most_concentrated_first():
    store = Mock()
    store.get_buildable_units.return_value = [
        SimpleNamespace(id="u1", title="A", metadata={"language": "Python", "framework": "Django"}),
        SimpleNamespace(id="u2", title="B", metadata={"language": "Python", "framework": "Rails"}),
    ]

    markdown = render_buildable_unit_stack_diversity_report_markdown(build_buildable_unit_stack_diversity_report_export(store))

    assert markdown.index("Python") < markdown.index("Django")
