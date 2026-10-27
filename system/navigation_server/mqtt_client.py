"""MQTT publisher for the navigation server."""

from __future__ import annotations

import logging
import paho.mqtt.client as mqtt

from system.common.config import MqttConfig

log = logging.getLogger(__name__)


class NavMqttClient:
    """Thin wrapper around paho-mqtt for publishing positions and serving map."""

    def __init__(self, cfg: MqttConfig, on_map_request=None):
        self._cfg = cfg
        self._on_map_request = on_map_request

        self._client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
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

    def _on_connect(self, client, userdata, flags, rc, properties=None):
        if rc == 0:
            log.info("Connected to MQTT broker")
            from system.common.topics import Topics

            client.subscribe(Topics.MAP_REQUEST)
        else:
            log.error("MQTT connection failed: rc=%s", rc)

    def _on_message(self, client, userdata, msg: mqtt.MQTTMessage):
        from system.common.topics import Topics

        if msg.topic == Topics.MAP_REQUEST and self._on_map_request:
            self._on_map_request()

    def publish(self, topic: str, payload: str, qos: int = 0):
        self._client.publish(topic, payload, qos=qos)

    def disconnect(self):
        self._client.loop_stop()
        self._client.disconnect()
