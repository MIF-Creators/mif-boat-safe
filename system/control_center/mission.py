"""Mission management – builds and tracks missions."""

from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass, field

from system.common.enums import MissionCommand, MissionEvent, MissionStatus
from system.common.messages import MissionMessage, MissionControlMessage

# Mission status after an event from the vehicle.
STATUS_AFTER_EVENT = {
    MissionEvent.ACCEPTED: MissionStatus.EXECUTING,
    MissionEvent.REJECTED: MissionStatus.FAILED,
    MissionEvent.WAYPOINT_REACHED: MissionStatus.EXECUTING,
    MissionEvent.PAUSED: MissionStatus.PAUSED,
    MissionEvent.RESUMED: MissionStatus.EXECUTING,
    MissionEvent.COMPLETED: MissionStatus.COMPLETED,
    MissionEvent.CANCELLED: MissionStatus.CANCELLED,
    MissionEvent.FAILED: MissionStatus.FAILED,
}


@dataclass
class ActiveMission:
    mission_id: str = ""
    vehicle_id: str = ""
    waypoints: list[dict] = field(default_factory=list)
    status: MissionStatus = MissionStatus.PENDING
    current_waypoint_idx: int = 0


class MissionManager:
    """Keeps track of active missions per vehicle."""

    def __init__(self):
        self._lock = threading.Lock()
        self._missions: dict[str, ActiveMission] = {}  # vehicle_id -> ActiveMission

    def create_mission(self, vehicle_id: str, waypoints: list[dict]) -> MissionMessage:
        """Build a MissionMessage and register it internally."""
        mid = str(uuid.uuid4())
        msg = MissionMessage(
            mission_id=mid,
            vehicle_id=vehicle_id,
            waypoints=waypoints,
        )
        with self._lock:
            self._missions[vehicle_id] = ActiveMission(
                mission_id=mid,
                vehicle_id=vehicle_id,
                waypoints=waypoints,
                status=MissionStatus.PENDING,
            )
        return msg

    def build_control(
        self, vehicle_id: str, command: MissionCommand
    ) -> MissionControlMessage | None:
        with self._lock:
            am = self._missions.get(vehicle_id)
            if am is None:
                return None
            return MissionControlMessage(mission_id=am.mission_id, command=command)

    def update_status(
        self, vehicle_id: str, event: MissionEvent, waypoint_idx: int = 0
    ):
        with self._lock:
            am = self._missions.get(vehicle_id)
            if am:
                am.status = STATUS_AFTER_EVENT[event]
                am.current_waypoint_idx = waypoint_idx

    def get_active(self, vehicle_id: str) -> ActiveMission | None:
        with self._lock:
            am = self._missions.get(vehicle_id)
            if am:
                return ActiveMission(
                    mission_id=am.mission_id,
                    vehicle_id=am.vehicle_id,
                    waypoints=list(am.waypoints),
                    status=am.status,
                    current_waypoint_idx=am.current_waypoint_idx,
                )
            return None

    def get_all(self) -> dict[str, dict]:
        with self._lock:
            return {
                vid: {
                    "mission_id": am.mission_id,
                    "vehicle_id": am.vehicle_id,
                    "status": am.status,
                    "current_waypoint_idx": am.current_waypoint_idx,
                    "waypoints": am.waypoints,
                }
                for vid, am in self._missions.items()
            }
