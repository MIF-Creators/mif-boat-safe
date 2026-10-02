"""Thread-safe shared state for vehicle services."""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
import time
from typing import Callable

@dataclass
class Position:
    x: float = 0.0
    y: float = 0.0
    rotation: float = 0.0
    valid: bool = False


@dataclass
class NeighborPosition:
    vehicle_id: str = ""
    x: float = 0.0
    y: float = 0.0
    rotation: float = 0.0


@dataclass
class MissionState:
    mission_id: str = ""
    waypoints: list[dict] = field(default_factory=list)
    current_waypoint_idx: int = 0
    status: str = "idle"          # idle | executing | paused | completed | cancelled | failed


class SharedState:
    """Centralised state shared across all vehicle service threads."""

    def __init__(self,
                 position_timeout: float = 1.0,
                 clock: Callable[[], float] = time.monotonic):
        self._clock = clock
        self._position_timeout = position_timeout
        self._lock = threading.Lock()
        self._position = Position()
        self._position_time: float | None = None
        self._neighbors: list[NeighborPosition] = []
        self._mission = MissionState()

    # -- position ----------------------------------------------------------

    def update_position(self, x: float, y: float, rotation: float):
        with self._lock:
            self._position.x = x
            self._position.y = y
            self._position.rotation = rotation
            self._position_time = self._clock()

    def get_position(self) -> Position:
        with self._lock:
            is_valid = (
                self._position_time is not None
                and self._clock() - self._position_time <= self._position_timeout
            )

            return Position(
                x=self._position.x,
                y=self._position.y,
                rotation=self._position.rotation,
                valid=is_valid,
            )

    # -- neighbors ---------------------------------------------------------

    def update_neighbors(self, neighbors: list[dict]):
        with self._lock:
            self._neighbors = [
                NeighborPosition(
                    vehicle_id=n.get("vehicle_id", ""),
                    x=n.get("x", 0),
                    y=n.get("y", 0),
                    rotation=n.get("rotation", 0),
                )
                for n in neighbors
            ]

    def get_neighbors(self) -> list[NeighborPosition]:
        with self._lock:
            return list(self._neighbors)

    # -- mission -----------------------------------------------------------

    def set_mission(self, mission_id: str, waypoints: list[dict]):
        with self._lock:
            self._mission.mission_id = mission_id
            self._mission.waypoints = list(waypoints)
            self._mission.current_waypoint_idx = 0
            self._mission.status = "executing"

    def get_mission(self) -> MissionState:
        with self._lock:
            return MissionState(
                mission_id=self._mission.mission_id,
                waypoints=list(self._mission.waypoints),
                current_waypoint_idx=self._mission.current_waypoint_idx,
                status=self._mission.status,
            )

    def advance_waypoint(self):
        with self._lock:
            self._mission.current_waypoint_idx += 1
            if self._mission.current_waypoint_idx >= len(self._mission.waypoints):
                self._mission.status = "completed"

    def set_mission_status(self, status: str):
        with self._lock:
            self._mission.status = status

    def get_current_waypoint(self) -> dict | None:
        with self._lock:
            idx = self._mission.current_waypoint_idx
            if 0 <= idx < len(self._mission.waypoints):
                return dict(self._mission.waypoints[idx])
            return None
