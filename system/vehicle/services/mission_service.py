"""Mission state machine – receives missions and control commands via MQTT."""

from __future__ import annotations

import logging

from system.common.messages import (
    MissionMessage,
    MissionControlMessage,
    MissionStatusMessage,
)
from system.common.topics import Topics
from system.vehicle.shared_state import SharedState

log = logging.getLogger(__name__)


class MissionService:
    """Manages the mission lifecycle.

    States: idle -> executing <-> paused -> completed / cancelled / failed
    """

    def __init__(self, vehicle_id: str, shared: SharedState, mqtt_client):
        self._vehicle_id = vehicle_id
        self._shared = shared
        self._mqtt = mqtt_client

    def start(self):
        self._mqtt.subscribe(
            Topics.mission_assign(self._vehicle_id),
            self._on_mission_assign,
        )
        self._mqtt.subscribe(
            Topics.mission_control(self._vehicle_id),
            self._on_mission_control,
        )
        log.info(
            "MissionService listening for missions on vehicle=%s", self._vehicle_id
        )

    # -- handlers ----------------------------------------------------------

    def _on_mission_assign(self, msg):
        try:
            mission = MissionMessage.from_json(msg.payload)
        except Exception:
            log.exception("Bad mission payload")
            return

        log.info(
            "Mission received: %s with %d waypoints",
            mission.mission_id,
            len(mission.waypoints),
        )
        self._shared.set_mission(mission.mission_id, mission.waypoints)
        self._publish_status("accepted")

    def _on_mission_control(self, msg):
        try:
            ctrl = MissionControlMessage.from_json(msg.payload)
        except Exception:
            log.exception("Bad mission control payload")
            return

        mission = self._shared.get_mission()
        if ctrl.mission_id and ctrl.mission_id != mission.mission_id:
            log.warning(
                "Control for unknown mission %s (current=%s)",
                ctrl.mission_id,
                mission.mission_id,
            )
            return

        cmd = ctrl.command
        if cmd == "cancel":
            self._shared.set_mission_status("cancelled")
            self._publish_status("cancelled")
            log.info("Mission cancelled")
        elif cmd == "pause":
            if mission.status == "executing":
                self._shared.set_mission_status("paused")
                self._publish_status("paused")
                log.info("Mission paused")
        elif cmd == "resume":
            if mission.status == "paused":
                self._shared.set_mission_status("executing")
                self._publish_status("in_progress")
                log.info("Mission resumed")
        else:
            log.warning("Unknown mission control command: %s", cmd)

    # -- notifications -----------------------------------------------------

    # Called from the navigation thread: the mission may already be replaced
    # in shared state, so the caller passes the mission it is reporting on.

    def notify_waypoint_reached(self, mission_id: str, idx: int):
        self._send_status(mission_id, "waypoint_reached", idx)

    def notify_completed(self, mission_id: str, idx: int):
        self._send_status(mission_id, "completed", idx)

    def _publish_status(self, status: str):
        mission = self._shared.get_mission()
        self._send_status(mission.mission_id, status, mission.current_waypoint_idx)

    def _send_status(self, mission_id: str, status: str, waypoint_idx: int):
        msg = MissionStatusMessage(
            mission_id=mission_id,
            vehicle_id=self._vehicle_id,
            status=status,
            current_waypoint_idx=waypoint_idx,
        )
        self._mqtt.publish(
            Topics.mission_status(self._vehicle_id), msg.to_json(), qos=1
        )
