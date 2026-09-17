from __future__ import annotations

ALLOWED_TRANSITIONS: dict[str, tuple[str, ...]] = {
    "New": ("Triaged", "Closed"),
    "Triaged": ("In Progress", "Closed"),
    "In Progress": ("Resolved", "Closed"),
    "Resolved": ("In Progress", "Closed"),
    "Closed": ("In Progress",),
}


def allowed_transitions(status: str) -> tuple[str, ...]:
    return ALLOWED_TRANSITIONS.get(status, ())


def validate_transition(from_status: str, to_status: str) -> None:
    if to_status not in allowed_transitions(from_status):
        raise ValueError(f"Cannot move a defect from {from_status!r} to {to_status!r}.")
