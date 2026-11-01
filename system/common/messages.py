"""Message schemas for MQTT communication.

All messages are serialized to JSON for transport over MQTT. The models
describe only the shape of the data: parsing a message with a missing or
wrongly typed field raises ``pydantic.ValidationError``. Rules about the
values (e.g. a mission needs waypoints) live in ``validation.py``.
Unknown fields are ignored, so a newer sender can add fields without
breaking older receivers.
"""

from __future__ import annotations

import json
import time
import uuid
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from .enums import (
    MissionCommand,
    MissionEvent,
    ObstacleShape,
    VehicleState,
    WaypointAction,
)

# A finite number; JSON strings and booleans are not accepted.
Number = Annotated[float, Field(strict=True, allow_inf_nan=False)]
# An integer; JSON strings, floats and booleans are not accepted.
Integer = Annotated[int, Field(strict=True)]


def describe_error(error: ValidationError) -> str:
    """One-line description of what is wrong, e.g. for a rejection reply."""
    return "; ".join(
        f"{'.'.join(str(p) for p in e['loc']) or 'message'}: {e['msg']}"
        for e in error.errors()
    )


# ---------------------------------------------------------------------------
# Base
# ---------------------------------------------------------------------------


class FrozenModel(BaseModel):
    """Part of a message: immutable, so it can be shared without copying."""

    model_config = ConfigDict(frozen=True)


class BaseMessage(BaseModel):
    """Every message carries a timestamp."""

    timestamp: Number = Field(default_factory=time.time)

    def to_json(self) -> str:
        # exclude_none: unset optional fields (e.g. params.duration) are omitted.
        return json.dumps(
            self.model_dump(mode="json", exclude_none=True), ensure_ascii=False
        )

    @classmethod
    def from_json(cls, payload: str | bytes):
        """Parse and validate; raises ``ValidationError``, also for invalid JSON.

        Returns an instance of the class it is called on.
        """
        return cls.model_validate_json(payload)


# ---------------------------------------------------------------------------
# Position
# ---------------------------------------------------------------------------


class NeighborInfo(FrozenModel):
    vehicle_id: str
    x: Number
    y: Number
    rotation: Number


class PositionMessage(BaseMessage):
    """Published by Navigation Server on ``nav/{vehicle_id}/position``."""

    vehicle_id: str
    x: Number
    y: Number
    rotation: Number
    neighbors: list[NeighborInfo] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Mission
# ---------------------------------------------------------------------------


class WaypointParams(FrozenModel):
    duration: Number | None = None  # seconds, for the "wait" action


class Waypoint(FrozenModel):
    """Point of a mission route."""

    x: Number
    y: Number
    action: WaypointAction = WaypointAction.NONE
    params: WaypointParams = WaypointParams()


class MissionMessage(BaseMessage):
    """Sent by Control Center on ``vehicle/{vehicle_id}/mission/assign``."""

    mission_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    vehicle_id: str = ""
    waypoints: list[Waypoint]


class MissionControlMessage(BaseMessage):
    """Sent by Control Center on ``vehicle/{vehicle_id}/mission/control``."""

    mission_id: str = ""
    command: MissionCommand


class MissionStatusMessage(BaseMessage):
    """Published by Vehicle on ``vehicle/{vehicle_id}/mission/status``."""

    mission_id: str = ""
    vehicle_id: str = ""
    status: MissionEvent
    current_waypoint_idx: Integer = 0
    detail: str = ""


# ---------------------------------------------------------------------------
# Vehicle heartbeat
# ---------------------------------------------------------------------------


class VehicleStatusMessage(BaseMessage):
    """Published by Vehicle on ``vehicle/{vehicle_id}/status``."""

    vehicle_id: str = ""
    state: VehicleState = VehicleState.IDLE
    current_waypoint_idx: Integer = 0
    mission_id: str = ""


# ---------------------------------------------------------------------------
# Map
# ---------------------------------------------------------------------------


class ObstacleInfo(FrozenModel):
    type: ObstacleShape
    x: Number = 0.0
    y: Number = 0.0
    width: Number = 0.0
    height: Number = 0.0
    radius: Number = 0.0


class MapMessage(BaseMessage):
    """Sent by Navigation Server on ``control/map/response``."""

    width: Integer = 100
    height: Integer = 100
    # Marker id -> (x, y) on the map.
    reference_markers: dict[str, tuple[Number, Number]] = Field(default_factory=dict)
    obstacles: list[ObstacleInfo] = Field(default_factory=list)


class MapRequestMessage(BaseMessage):
    """Sent by Control Center on ``control/map/request``."""
