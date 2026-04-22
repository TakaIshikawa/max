"""Status transition policy for buildable units."""

from __future__ import annotations

BUILDABLE_UNIT_STATUSES = frozenset(
    {
        "draft",
        "evaluated",
        "approved",
        "published",
        "rejected",
        "abandoned",
        "archived",
        "duplicate",
        "synthesized",
    }
)

BUILDABLE_UNIT_TRANSITIONS = {
    "draft": frozenset(
        {
            "draft",
            "evaluated",
            "approved",
            "published",
            "rejected",
            "abandoned",
            "archived",
            "duplicate",
            "synthesized",
        }
    ),
    "evaluated": frozenset(
        {
            "evaluated",
            "approved",
            "published",
            "rejected",
            "abandoned",
            "archived",
            "duplicate",
            "synthesized",
        }
    ),
    "approved": frozenset(
        {"approved", "published", "rejected", "abandoned", "synthesized"}
    ),
    "published": frozenset({"published", "approved", "abandoned", "synthesized"}),
    "rejected": frozenset({"rejected", "approved", "abandoned"}),
    "abandoned": frozenset({"abandoned", "approved", "rejected", "synthesized"}),
    "archived": frozenset({"archived", "evaluated"}),
    "duplicate": frozenset({"duplicate", "evaluated"}),
    "synthesized": frozenset({"synthesized", "evaluated"}),
}


class InvalidBuildableUnitStatusTransition(ValueError):
    """Raised when a buildable unit status transition violates policy."""


def can_transition_buildable_unit_status(
    current_status: str,
    next_status: str,
    *,
    force: bool = False,
) -> bool:
    """Return whether a buildable unit may move from one status to another."""
    if force:
        return True
    return next_status in BUILDABLE_UNIT_TRANSITIONS.get(current_status, frozenset())


def validate_buildable_unit_status_transition(
    current_status: str,
    next_status: str,
    *,
    force: bool = False,
) -> None:
    """Raise if a buildable unit status transition is not allowed."""
    if next_status not in BUILDABLE_UNIT_STATUSES:
        raise InvalidBuildableUnitStatusTransition(
            f"Unknown buildable unit status: {next_status}"
        )
    if current_status not in BUILDABLE_UNIT_STATUSES:
        raise InvalidBuildableUnitStatusTransition(
            f"Unknown current buildable unit status: {current_status}"
        )
    if not can_transition_buildable_unit_status(
        current_status, next_status, force=force
    ):
        raise InvalidBuildableUnitStatusTransition(
            f"Invalid buildable unit status transition: {current_status} -> {next_status}"
        )
