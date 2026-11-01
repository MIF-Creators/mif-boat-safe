"""Mission state machine – receives missions and control commands via MQTT."""

from __future__ import annotations

import json
import logging

from pydantic import ValidationError

from system.common.enums import MissionCommand, MissionEvent, MissionStatus
from system.common.messages import (
    MissionMessage,
    MissionControlMessage,
    MissionStatusMessage,
    describe_error,
)
from system.common.topics import Topics
from system.common.validation import validate_mission
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
        except ValidationError as e:
            self._reject_mission(msg.payload, describe_error(e))
            return
        errors = validate_mission(mission)
        if errors:
            self._reject_mission(msg.payload, "; ".join(errors))
            return

        log.info(
            "Mission received: %s with %d waypoints",
            mission.mission_id,
            len(mission.waypoints),
        )
        self._shared.set_mission(mission.mission_id, mission.waypoints)
        self._publish_status(MissionEvent.ACCEPTED)

    def _reject_mission(self, payload: str | bytes, reason: str):
        """Reply ``rejected`` if the mission id is readable; keep the current mission."""
        try:
            mission_id = json.loads(payload).get("mission_id")
        except (ValueError, AttributeError):
            mission_id = None
        if not isinstance(mission_id, str) or not mission_id:
            log.warning("Dropping mission without a valid mission_id: %s", reason)
            return

        log.warning("Rejecting mission %s: %s", mission_id, reason)
        self._send_status(mission_id, MissionEvent.REJECTED, 0, detail=reason)

    def _on_mission_control(self, msg):
        try:
            ctrl = MissionControlMessage.from_json(msg.payload)
        except ValidationError as e:
            log.warning("Bad mission control payload: %s", describe_error(e))
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
        if cmd == MissionCommand.CANCEL:
            self._shared.set_mission_status(MissionStatus.CANCELLED)
            self._publish_status(MissionEvent.CANCELLED)
            log.info("Mission cancelled")
        elif cmd == MissionCommand.PAUSE:
            if mission.status == MissionStatus.EXECUTING:
                self._shared.set_mission_status(MissionStatus.PAUSED)
                self._publish_status(MissionEvent.PAUSED)
                log.info("Mission paused")
        elif cmd == MissionCommand.RESUME:
            if mission.status == MissionStatus.PAUSED:
                self._shared.set_mission_status(MissionStatus.EXECUTING)
                self._publish_status(MissionEvent.RESUMED)
                log.info("Mission resumed")
        else:
            log.warning("Unknown mission control command: %s", cmd)

    # -- notifications -----------------------------------------------------

    # Called from the navigation thread: the mission may already be replaced
    # in shared state, so the caller passes the mission it is reporting on.

    def notify_waypoint_reached(self, mission_id: str, idx: int):
        self._send_status(mission_id, MissionEvent.WAYPOINT_REACHED, idx)

    def notify_completed(self, mission_id: str, idx: int):
        self._send_status(mission_id, MissionEvent.COMPLETED, idx)

    def _publish_status(self, status: MissionEvent):
        mission = self._shared.get_mission()
        self._send_status(mission.mission_id, status, mission.current_waypoint_idx)

    def _send_status(
        self,
        mission_id: str,
        status: MissionEvent,
        waypoint_idx: int,
        detail: str = "",
    ):
        msg = MissionStatusMessage(
            mission_id=mission_id,
            vehicle_id=self._vehicle_id,
            status=status,
            current_waypoint_idx=waypoint_idx,
            detail=detail,
        )
        self._mqtt.publish(
            Topics.mission_status(self._vehicle_id), msg.to_json(), qos=1
        )
