"""Rules about message values, checked after parsing.

``messages.py`` models describe the shape of the data; the functions here
check that the values make sense. Each returns a list of problems, empty
when the message is valid.
"""

from __future__ import annotations

from .enums import WaypointAction
from .messages import MissionMessage


def validate_mission(mission: MissionMessage) -> list[str]:
    """Check the mission's values; return the problems found, empty if valid."""
    errors = []
    if not mission.waypoints:
        errors.append("waypoints: mission has no waypoints")
    for i, wp in enumerate(mission.waypoints):
        if wp.action is WaypointAction.WAIT and not (
            wp.params.duration is not None and wp.params.duration > 0
        ):
            errors.append(f"waypoints.{i}: wait needs params.duration > 0")
    return errors
