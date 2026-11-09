import json
from unittest.mock import Mock

import pytest

from system.common.config import ControlCenterConfig
from system.common.enums import MissionEvent
from system.common.messages import MissionMessage
from system.common.validation import validate_mission
from system.control_center import main as cc_main
from system.control_center.mission import MissionManager


@pytest.fixture
def api(monkeypatch):
    manager = MissionManager()
    manager.create_mission("boat_a", [{"x": 1, "y": 2}])
    mission_id = manager.get_active("boat_a").mission_id
    manager.update_status("boat_a", mission_id, MissionEvent.WAYPOINT_REACHED, 1)
    mqtt = Mock()
    monkeypatch.setattr(cc_main, "mission_mgr", manager)
    monkeypatch.setattr(cc_main, "mqtt_client", mqtt)
    monkeypatch.setitem(cc_main.app.config, "TESTING", True)
    monkeypatch.setitem(cc_main.app.config, "VEHICLE_IDS", ["boat_a", "boat_b"])
    with cc_main.app.test_client() as client:
        yield client, manager, mqtt


@pytest.mark.parametrize(
    "body, error",
    [
        ({}, "vehicle_id"),
        ({"vehicle_id": "boat_a"}, "waypoints"),
        ({"waypoints": [{"x": 1, "y": 2}]}, "vehicle_id"),
        ({"vehicle_id": "boat_a", "waypoints": []}, "waypoints"),
        ({"vehicle_id": "boat_a", "waypoints": None}, "waypoints"),
        ({"vehicle_id": "boat_a", "waypoints": {}}, "waypoints"),
        ({"vehicle_id": "boat_a", "waypoints": "route"}, "waypoints"),
        ({"vehicle_id": "boat_a", "waypoints": [None]}, "waypoints.0"),
        ({"vehicle_id": "boat_a", "waypoints": [{"y": 2}]}, "waypoints.0.x"),
        ({"vehicle_id": "boat_a", "waypoints": [{"x": 1}]}, "waypoints.0.y"),
        (
            {"vehicle_id": "boat_a", "waypoints": [{"x": "1", "y": 2}]},
            "waypoints.0.x",
        ),
        (
            {"vehicle_id": "boat_a", "waypoints": [{"x": True, "y": 2}]},
            "waypoints.0.x",
        ),
        (
            {"vehicle_id": "boat_a", "waypoints": [{"x": float("inf"), "y": 2}]},
            "waypoints.0.x",
        ),
        (
            {"vehicle_id": "boat_a", "waypoints": [{"x": 1, "y": 2, "action": "jump"}]},
            "waypoints.0.action",
        ),
        (
            {"vehicle_id": "boat_a", "waypoints": [{"x": 1, "y": 2, "params": []}]},
            "waypoints.0.params",
        ),
    ]
    + [
        ({"vehicle_id": vehicle_id, "waypoints": [{"x": 1, "y": 2}]}, "vehicle_id")
        for vehicle_id in [None, "", "unknown", "vehicle_0", 123, True, [], {}]
    ]
    + [
        (
            {
                "vehicle_id": "boat_a",
                "waypoints": [{"x": 1, "y": 2, "action": "wait", "params": params}],
            },
            "waypoints.0",
        )
        for params in [{}, {"duration": None}, {"duration": 0}, {"duration": -1}]
    ]
    + [
        (
            {
                "vehicle_id": "boat_a",
                "waypoints": [
                    {"x": 1, "y": 2, "action": "wait", "params": {"duration": "3"}}
                ],
            },
            "waypoints.0.params.duration",
        ),
    ],
)
def test_invalid_mission_request_is_rejected_without_side_effects(api, body, error):
    client, manager, mqtt = api
    before = manager.get_all()

    response = client.post("/api/mission/send", json=body)

    assert response.status_code == 400
    assert error in response.get_json()["error"]
    assert manager.get_all() == before
    mqtt.send_mission.assert_not_called()


@pytest.mark.parametrize("payload", ["", "{", "null", "[]", '"text"', "42", "true"])
def test_invalid_json_body_returns_json_error(api, payload):
    client, manager, mqtt = api
    before = manager.get_all()

    response = client.post(
        "/api/mission/send", data=payload, content_type="application/json"
    )

    assert response.status_code == 400
    assert response.is_json
    assert response.get_json()["error"]
    assert manager.get_all() == before
    mqtt.send_mission.assert_not_called()


def test_valid_mission_is_registered_and_published(api):
    client, manager, mqtt = api
    old_id = manager.get_active("boat_a").mission_id
    body = {
        "vehicle_id": "boat_a",
        "waypoints": [
            {"x": 1, "y": 2, "extra": "ignored"},
            {"x": 3, "y": 4, "action": "wait", "params": {"duration": 2.5}},
            {"x": 5, "y": 6, "action": "stop"},
        ],
        "mission_id": "client-supplied-id",
        "extra": "ignored",
    }

    response = client.post("/api/mission/send", json=body)

    assert response.status_code == 200
    mission_id = response.get_json()["mission_id"]
    assert mission_id not in (old_id, body["mission_id"])
    mqtt.send_mission.assert_called_once()
    vehicle_id, payload = mqtt.send_mission.call_args.args
    message = MissionMessage.from_json(payload)
    assert vehicle_id == message.vehicle_id == "boat_a"
    assert message.mission_id == mission_id
    assert validate_mission(message) == []
    assert manager.get_active("boat_a").waypoints == message.waypoints
    assert len(message.waypoints) == 3
    assert message.waypoints[1].params.duration == 2.5
    assert "extra" not in json.loads(payload)
    assert "extra" not in json.loads(payload)["waypoints"][0]


def test_vehicle_allowlist_comes_from_startup_config(api, monkeypatch):
    client, manager, mqtt = api
    cfg = ControlCenterConfig(vehicle_ids=["configured_boat"])
    monkeypatch.setattr(cc_main.ControlCenterConfig, "load", lambda **kwargs: cfg)
    monkeypatch.setattr(cc_main, "ControlCenterMqtt", lambda config: mqtt)
    monkeypatch.setattr(cc_main.time, "sleep", lambda seconds: None)
    monkeypatch.setattr(cc_main.app, "run", Mock())
    cc_main.main()

    accepted = client.post(
        "/api/mission/send",
        json={"vehicle_id": "configured_boat", "waypoints": [{"x": 1, "y": 2}]},
    )
    rejected = client.post(
        "/api/mission/send",
        json={"vehicle_id": "boat_b", "waypoints": [{"x": 1, "y": 2}]},
    )

    assert accepted.status_code == 200
    assert manager.get_active("configured_boat") is not None
    assert rejected.status_code == 400
    assert "vehicle_id" in rejected.get_json()["error"]
    assert manager.get_active("boat_b") is None
    mqtt.send_mission.assert_called_once()
