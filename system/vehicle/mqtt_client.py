"""Shared MQTT connection for the vehicle process."""

from __future__ import annotations

import logging
from collections.abc import Callable

import paho.mqtt.client as mqtt

from system.common.config import VehicleConfig

log = logging.getLogger(__name__)


class VehicleMqttClient:
    """Single paho-mqtt client shared by all vehicle services."""

    def __init__(self, cfg: VehicleConfig):
        self._cfg = cfg
        self._client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
        self._handlers: dict[str, list[Callable]] = {}
        self._client.on_connect = self._on_connect
        self._client.on_message = self._on_message

    def connect(self):
        log.info(
            "Connecting to MQTT broker %s:%s",
            self._cfg.broker_host,
            self._cfg.broker_port,
        )
        self._client.connect(self._cfg.broker_host, self._cfg.broker_port, keepalive=60)
        self._client.loop_start()

    def subscribe(self, topic: str, handler: Callable):
        self._handlers.setdefault(topic, []).append(handler)
        self._client.subscribe(topic)

    def publish(self, topic: str, payload: str, qos: int = 0):
        self._client.publish(topic, payload, qos=qos)

    def _on_connect(self, client, userdata, flags, rc, properties=None):
        if rc == 0:
            log.info("Connected to MQTT broker")
            for topic in self._handlers:
                client.subscribe(topic)
        else:
            log.error("MQTT connection failed: rc=%s", rc)

    def _on_message(self, client, userdata, msg: mqtt.MQTTMessage):
        handlers = self._handlers.get(msg.topic, [])
        for h in handlers:
            try:
                h(msg)
            except Exception:
                log.exception("Error in handler for topic %s", msg.topic)

    def disconnect(self):
        self._client.loop_stop()
        self._client.disconnect()
