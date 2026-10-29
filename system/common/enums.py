"""Enumerations shared by all components.

Members are ``str`` subclasses, so they serialize to JSON as their plain
values and the wire format stays the same as with raw strings.
"""

from __future__ import annotations

from enum import Enum


class StrValueEnum(str, Enum):
    """``str`` enum whose ``str()`` and ``format()`` give the plain value."""

    def __str__(self) -> str:
        return self.value

    def __format__(self, format_spec: str) -> str:
        return format(self.value, format_spec)


class MissionStatus(StrValueEnum):
    """State of a mission, on the vehicle and in the control center.

    ``PENDING`` is used only by the control center: the mission was sent,
    but the vehicle has not answered yet.
    """

    PENDING = "pending"
    IDLE = "idle"
    EXECUTING = "executing"
    PAUSED = "paused"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    FAILED = "failed"


class MissionEvent(StrValueEnum):
    """What happened to a mission, reported in ``MissionStatusMessage``."""

    ACCEPTED = "accepted"
    REJECTED = "rejected"
    WAYPOINT_REACHED = "waypoint_reached"
    PAUSED = "paused"
    RESUMED = "resumed"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    FAILED = "failed"


class VehicleState(StrValueEnum):
    """State of the vehicle itself, reported in ``VehicleStatusMessage``."""

    IDLE = "idle"
    EXECUTING = "executing"
    PAUSED = "paused"
    ERROR = "error"


class MissionCommand(StrValueEnum):
    """Operator command in ``MissionControlMessage``."""

    CANCEL = "cancel"
    PAUSE = "pause"
    RESUME = "resume"
