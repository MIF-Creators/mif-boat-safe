"""Control Center entry point – Flask web app + MQTT client."""

import logging
import threading
import time

from flask import Flask, jsonify, request, render_template

from system.common.config import ControlCenterConfig, component_dotenv_path
from system.control_center.mqtt_client import ControlCenterMqtt
from system.control_center.mission import MissionManager

logging.basicConfig(level=logging.INFO, format="%(asctime)s [CC] %(message)s")
log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Shared state (updated from MQTT callbacks)
# ---------------------------------------------------------------------------

_lock = threading.Lock()
_vehicle_positions: dict[str, dict] = {}  # vehicle_id -> {x, y, rotation, timestamp}
_vehicle_statuses: dict[str, dict] = {}  # vehicle_id -> latest heartbeat
_map_data: dict | None = None

mission_mgr = MissionManager()

# ---------------------------------------------------------------------------
# Flask app
# ---------------------------------------------------------------------------

import os

app = Flask(
    __name__,
    template_folder=os.path.join(os.path.dirname(__file__), "templates"),
    static_folder=os.path.join(os.path.dirname(__file__), "static"),
)

mqtt_client: ControlCenterMqtt | None = None


# -- REST API --------------------------------------------------------------


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/map")
def api_map():
    with _lock:
        if _map_data:
            return jsonify(_map_data)
    return jsonify({"error": "map not loaded yet"}), 503


@app.route("/api/positions")
def api_positions():
    with _lock:
        return jsonify(_vehicle_positions)


@app.route("/api/statuses")
def api_statuses():
    with _lock:
        return jsonify(_vehicle_statuses)


@app.route("/api/missions")
def api_missions():
    return jsonify(mission_mgr.get_all())


@app.route("/api/mission/send", methods=["POST"])
def api_send_mission():
    body = request.get_json(force=True)
    vehicle_id = body.get("vehicle_id")
    waypoints = body.get("waypoints", [])
    if not vehicle_id or not waypoints:
        return jsonify({"error": "vehicle_id and waypoints required"}), 400

    msg = mission_mgr.create_mission(vehicle_id, waypoints)
    if mqtt_client:
        mqtt_client.send_mission(vehicle_id, msg.to_json())
    log.info(
        "Mission %s sent to %s (%d waypoints)",
        msg.mission_id,
        vehicle_id,
        len(waypoints),
    )
    return jsonify({"mission_id": msg.mission_id})


@app.route("/api/mission/control", methods=["POST"])
def api_mission_control():
    body = request.get_json(force=True)
    vehicle_id = body.get("vehicle_id")
    command = body.get("command")
    if not vehicle_id or not command:
        return jsonify({"error": "vehicle_id and command required"}), 400

    ctrl = mission_mgr.build_control(vehicle_id, command)
    if ctrl is None:
        return jsonify({"error": "no active mission for this vehicle"}), 404
    if mqtt_client:
        mqtt_client.send_mission_control(vehicle_id, ctrl.to_json())
    log.info("Mission control '%s' sent to %s", command, vehicle_id)
    return jsonify({"ok": True})


@app.route("/api/map/refresh", methods=["POST"])
def api_map_refresh():
    if mqtt_client:
        mqtt_client.request_map()
    return jsonify({"ok": True})


# ---------------------------------------------------------------------------
# MQTT callbacks
# ---------------------------------------------------------------------------


def _on_position(data: dict):
    vid = data.get("vehicle_id", "")
    with _lock:
        _vehicle_positions[vid] = data


def _on_mission_status(data: dict):
    vid = data.get("vehicle_id", "")
    mission_mgr.update_status(
        vid, data.get("status", ""), data.get("current_waypoint_idx", 0)
    )


def _on_vehicle_status(data: dict):
    vid = data.get("vehicle_id", "")
    with _lock:
        _vehicle_statuses[vid] = data


def _on_map_response(data: dict):
    global _map_data
    with _lock:
        _map_data = data
    log.info("Map data received (%sx%s)", data.get("width"), data.get("height"))


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main():
    global mqtt_client
    cfg = ControlCenterConfig.load(env_path=component_dotenv_path(__file__))

    mqtt_client = ControlCenterMqtt(cfg)
    mqtt_client.on_position(_on_position)
    mqtt_client.on_mission_status(_on_mission_status)
    mqtt_client.on_vehicle_status(_on_vehicle_status)
    mqtt_client.on_map_response(_on_map_response)
    mqtt_client.connect()

    time.sleep(0.5)
    mqtt_client.request_map()

    log.info("Starting web server on %s:%s", cfg.flask_host, cfg.flask_port)
    app.run(host=cfg.flask_host, port=cfg.flask_port, debug=False)


if __name__ == "__main__":
    main()
