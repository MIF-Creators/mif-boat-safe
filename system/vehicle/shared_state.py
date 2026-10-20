"""Thread-safe shared state for vehicle services."""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
import time
from collections.abc import Callable

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
    wait_until: float | None = None   # clock time when the waypoint wait ends; None = not waiting


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
            self._mission.wait_until = None

    def get_mission(self) -> MissionState:
        with self._lock:
            return MissionState(
                mission_id=self._mission.mission_id,
                waypoints=list(self._mission.waypoints),
                current_waypoint_idx=self._mission.current_waypoint_idx,
                status=self._mission.status,
                wait_until=self._mission.wait_until,
            )

    def _is_current(self, mission_id: str, idx: int) -> bool:
        return (mission_id, idx) == (self._mission.mission_id,
                                     self._mission.current_waypoint_idx)

    def advance_waypoint(self, mission_id: str, idx: int) -> bool:
        """Advance past waypoint ``idx`` of ``mission_id``.

        Does nothing and returns False if the mission or waypoint has
        changed since the caller read it.
        """
        with self._lock:
            if not self._is_current(mission_id, idx):
                return False
            self._mission.current_waypoint_idx += 1
            self._mission.wait_until = None
            if self._mission.current_waypoint_idx >= len(self._mission.waypoints):
                self._mission.status = "completed"
            return True

    def set_mission_status(self, status: str):
        with self._lock:
            self._mission.status = status
            if status != "executing":
                self._mission.wait_until = None

    def get_current_waypoint(self) -> dict | None:
        with self._lock:
            idx = self._mission.current_waypoint_idx
            if 0 <= idx < len(self._mission.waypoints):
                return dict(self._mission.waypoints[idx])
            return None

    def start_wait(self, mission_id: str, idx: int, duration: float) -> bool:
        """Start waiting at waypoint ``idx`` of ``mission_id`` for ``duration`` seconds.

        Does nothing and returns False if the mission or waypoint has
        changed since the caller read it.
        """
        with self._lock:
            if not self._is_current(mission_id, idx):
                return False
            self._mission.wait_until = self._clock() + duration
            return True

    def wait_remaining(self) -> float | None:
        """Seconds left to wait (<= 0 when over), or None if not waiting."""
        with self._lock:
            if self._mission.wait_until is None:
                return None
            return self._mission.wait_until - self._clock()
