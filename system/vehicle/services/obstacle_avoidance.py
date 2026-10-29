"""Obstacle avoidance service – STUB.

Future implementation will modify navigation commands to avoid obstacles.
"""

from __future__ import annotations

import logging

from system.vehicle.services.drive_service import DriveCommand
from system.vehicle.services.obstacle_detection import ObstacleDetectionService

log = logging.getLogger(__name__)


class ObstacleAvoidanceService:
    """Stub: passes commands through unchanged."""

    def __init__(self, detection: ObstacleDetectionService):
        self._detection = detection

    def start(self):
        log.info("ObstacleAvoidanceService started (STUB – passthrough)")

    def stop(self):
        pass

    def filter_command(self, command: DriveCommand) -> DriveCommand:
        """Potentially modify a drive command to avoid obstacles.

        In the stub implementation the command is returned as-is.
        """
        # TODO: check self._detection.get_obstacles() and alter command if needed
        return command
