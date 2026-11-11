"""Provides the map (field size, reference markers, obstacles) as a MapMessage."""

from __future__ import annotations

import logging

from system.common.config import NavigationServerConfig
from system.common.messages import MapMessage, ObstacleInfo
from system.common.topics import Topics
from system.navigation_server.coordinate_system import field_targets

log = logging.getLogger(__name__)


class MapProvider:
    def __init__(self, cfg: NavigationServerConfig):
        # Validated here, so a bad MAP_OBSTACLES fails at startup and not
        # later in the MQTT thread when the map is requested.
        self._obstacles = [ObstacleInfo.model_validate(o) for o in cfg.map_obstacles]
        # Set by the field calibration; None until it finishes.
        self._field: tuple[int, int] | None = None

    def set_field(self, width: int, height: int) -> None:
        self._field = (width, height)

    def build_map_message(self) -> MapMessage | None:
        """The map, or None while the field is not calibrated yet."""
        if self._field is None:
            return None
        width, height = self._field
        return MapMessage(
            width=width,
            height=height,
            reference_markers={
                str(mid): xy for mid, xy in field_targets(width, height).items()
            },
            obstacles=self._obstacles,
        )

    def publish_map(self, mqtt_client):
        msg = self.build_map_message()
        if msg is None:
            # The map is published anyway when the calibration finishes.
            log.info("Map requested before field calibration finished: not sent yet")
            return
        mqtt_client.publish(Topics.MAP_RESPONSE, msg.to_json(), qos=1)
