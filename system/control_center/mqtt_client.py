"""MQTT client for the control center – subscribes to vehicle telemetry and publishes missions."""

from __future__ import annotations

import json
import logging
from collections.abc import Callable

import paho.mqtt.client as mqtt

from system.common.config import ControlCenterConfig
from system.common.topics import Topics

log = logging.getLogger(__name__)


class ControlCenterMqtt:
    def __init__(self, cfg: ControlCenterConfig):
        self._cfg = cfg
        self._client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
        self._client.on_connect = self._on_connect
        self._client.on_message = self._on_message

        self._position_cb: Callable | None = None
        self._mission_status_cb: Callable | None = None
        self._vehicle_status_cb: Callable | None = None
        self._map_response_cb: Callable | None = None

    def connect(self):
        log.info("Connecting to MQTT %s:%s", self._cfg.broker_host, self._cfg.broker_port)
        self._client.connect(self._cfg.broker_host, self._cfg.broker_port, keepalive=60)
        self._client.loop_start()

    def _on_connect(self, client, userdata, flags, rc, properties=None):
        if rc != 0:
            log.error("MQTT connection failed rc=%s", rc)
            return
        log.info("Connected to MQTT broker")
        client.subscribe(Topics.vehicle_position_wildcard())
        client.subscribe(Topics.mission_status_wildcard())
        client.subscribe(Topics.vehicle_status_wildcard())
        client.subscribe(Topics.MAP_RESPONSE)

    def _on_message(self, client, userdata, msg: mqtt.MQTTMessage):
        topic = msg.topic
        try:
            data = json.loads(msg.payload)
        except Exception:
            return

        if "/position" in topic and self._position_cb:
            self._position_cb(data)
        elif "/mission/status" in topic and self._mission_status_cb:
            self._mission_status_cb(data)
        elif "/status" in topic and "/mission" not in topic and self._vehicle_status_cb:
            self._vehicle_status_cb(data)
        elif topic == Topics.MAP_RESPONSE and self._map_response_cb:
            self._map_response_cb(data)

    def on_position(self, cb: Callable):
        self._position_cb = cb

    def on_mission_status(self, cb: Callable):
        self._mission_status_cb = cb

    def on_vehicle_status(self, cb: Callable):
        self._vehicle_status_cb = cb

    def on_map_response(self, cb: Callable):
        self._map_response_cb = cb

    def request_map(self):
        from system.common.messages import MapRequestMessage
        self._client.publish(Topics.MAP_REQUEST, MapRequestMessage().to_json(), qos=1)

    def send_mission(self, vehicle_id: str, payload: str):
        self._client.publish(Topics.mission_assign(vehicle_id), payload, qos=1)

    def send_mission_control(self, vehicle_id: str, payload: str):
        self._client.publish(Topics.mission_control(vehicle_id), payload, qos=1)

    def disconnect(self):
        self._client.loop_stop()
        self._client.disconnect()
