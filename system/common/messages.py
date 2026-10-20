"""Dataclass message schemas for MQTT communication.

All messages are serialized to JSON for transport over MQTT.
"""

from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass, field, asdict


# ---------------------------------------------------------------------------
# Base
# ---------------------------------------------------------------------------


@dataclass
class BaseMessage:
    """Every message carries a timestamp."""

    timestamp: float = field(default_factory=time.time)

    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False)

    @classmethod
    def from_json(cls, payload: str | bytes) -> BaseMessage:
        if isinstance(payload, bytes):
            payload = payload.decode()
        data = json.loads(payload)
        return cls(**data)


# ---------------------------------------------------------------------------
# Position
# ---------------------------------------------------------------------------


@dataclass
class NeighborInfo:
    vehicle_id: str
    x: float
    y: float
    rotation: float


@dataclass
class PositionMessage(BaseMessage):
    """Published by Navigation Server on ``nav/{vehicle_id}/position``."""

    vehicle_id: str = ""
    x: float = 0.0
    y: float = 0.0
    rotation: float = 0.0
    neighbors: list[dict] = field(default_factory=list)

    @classmethod
    def from_json(cls, payload: str | bytes) -> PositionMessage:
        if isinstance(payload, bytes):
            payload = payload.decode()
        data = json.loads(payload)
        return cls(**data)


# ---------------------------------------------------------------------------
# Mission
# ---------------------------------------------------------------------------


@dataclass
class Waypoint:
    x: float
    y: float
    action: str = "none"  # "none" | "wait" | "stop"
    params: dict = field(default_factory=dict)


@dataclass
class MissionMessage(BaseMessage):
    """Sent by Control Center on ``vehicle/{vehicle_id}/mission/assign``."""

    mission_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    vehicle_id: str = ""
    waypoints: list[dict] = field(default_factory=list)

    @classmethod
    def from_json(cls, payload: str | bytes) -> MissionMessage:
        if isinstance(payload, bytes):
            payload = payload.decode()
        data = json.loads(payload)
        return cls(**data)

    def get_waypoints(self) -> list[Waypoint]:
        return [Waypoint(**wp) for wp in self.waypoints]


@dataclass
class MissionControlMessage(BaseMessage):
    """Sent by Control Center on ``vehicle/{vehicle_id}/mission/control``."""

    mission_id: str = ""
    command: str = ""  # "cancel" | "pause" | "resume"

    @classmethod
    def from_json(cls, payload: str | bytes) -> MissionControlMessage:
        if isinstance(payload, bytes):
            payload = payload.decode()
        data = json.loads(payload)
        return cls(**data)


@dataclass
class MissionStatusMessage(BaseMessage):
    """Published by Vehicle on ``vehicle/{vehicle_id}/mission/status``."""

    mission_id: str = ""
    vehicle_id: str = ""
    status: str = ""  # accepted | in_progress | waypoint_reached | completed | failed | cancelled | paused
    current_waypoint_idx: int = 0
    detail: str = ""

    @classmethod
    def from_json(cls, payload: str | bytes) -> MissionStatusMessage:
        if isinstance(payload, bytes):
            payload = payload.decode()
        data = json.loads(payload)
        return cls(**data)


# ---------------------------------------------------------------------------
# Vehicle heartbeat
# ---------------------------------------------------------------------------


@dataclass
class VehicleStatusMessage(BaseMessage):
    """Published by Vehicle on ``vehicle/{vehicle_id}/status``."""

    vehicle_id: str = ""
    state: str = "idle"  # idle | executing | paused | error
    current_waypoint_idx: int = 0
    mission_id: str = ""

    @classmethod
    def from_json(cls, payload: str | bytes) -> VehicleStatusMessage:
        if isinstance(payload, bytes):
            payload = payload.decode()
        data = json.loads(payload)
        return cls(**data)


# ---------------------------------------------------------------------------
# Map
# ---------------------------------------------------------------------------


@dataclass
class ObstacleInfo:
    type: str  # "rectangle" | "circle"
    x: float = 0.0
    y: float = 0.0
    width: float = 0.0
    height: float = 0.0
    radius: float = 0.0


@dataclass
class MapMessage(BaseMessage):
    """Sent by Navigation Server on ``control/map/response``."""

    width: int = 100
    height: int = 100
    reference_markers: dict = field(default_factory=dict)
    obstacles: list[dict] = field(default_factory=list)

    @classmethod
    def from_json(cls, payload: str | bytes) -> MapMessage:
        if isinstance(payload, bytes):
            payload = payload.decode()
        data = json.loads(payload)
        return cls(**data)


@dataclass
class MapRequestMessage(BaseMessage):
    """Sent by Control Center on ``control/map/request``."""

    @classmethod
    def from_json(cls, payload: str | bytes) -> MapRequestMessage:
        if isinstance(payload, bytes):
            payload = payload.decode()
        data = json.loads(payload)
        return cls(**data)
