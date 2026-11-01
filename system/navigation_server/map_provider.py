"""Provides the static map configuration as a MapMessage."""

from __future__ import annotations

from system.common.config import NavigationServerConfig
from system.common.messages import MapMessage, ObstacleInfo
from system.common.topics import Topics


class MapProvider:
    def __init__(self, cfg: NavigationServerConfig):
        self._cfg = cfg
        # Validated here, so a bad MAP_OBSTACLES fails at startup and not
        # later in the MQTT thread when the map is requested.
        self._obstacles = [ObstacleInfo.model_validate(o) for o in cfg.map_obstacles]
        self._reference_markers = {
            str(mid): list(coords)
            for mid, coords in {
                1: (0, 0),
                2: (0, cfg.map_height),
                3: (cfg.map_width, cfg.map_height),
                4: (cfg.map_width, 0),
            }.items()
        }

    def build_map_message(self) -> MapMessage:
        return MapMessage(
            width=self._cfg.map_width,
            height=self._cfg.map_height,
            reference_markers=self._reference_markers,
            obstacles=self._obstacles,
        )

    def publish_map(self, mqtt_client):
        msg = self.build_map_message()
        mqtt_client.publish(Topics.MAP_RESPONSE, msg.to_json(), qos=1)
