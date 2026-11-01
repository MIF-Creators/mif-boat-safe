import json

import pytest

from system.common.enums import MissionEvent, MissionStatus
from system.common.messages import (
    MissionControlMessage,
    MissionMessage,
    MissionStatusMessage,
    Waypoint,
)
from system.common.topics import Topics
from system.vehicle.services.mission_service import MissionService
from system.vehicle.shared_state import SharedState


class FakeMsg:
    def __init__(self, payload):
        self.payload = payload


class FakeMqtt:
    def __init__(self):
        self.subscriptions = []
        self.published = []

    def subscribe(self, topic, handler):
        self.subscriptions.append((topic, handler))

    def publish(self, topic, payload, qos=0):
        self.published.append({"topic": topic, "payload": payload, "qos": qos})


def test_start_subscribes_to_assign_and_control_topics():
    shared = SharedState()
    mqtt = FakeMqtt()
    service = MissionService("vehicle_0", shared, mqtt)

    service.start()

    topics = {topic for topic, _ in mqtt.subscriptions}
    assert Topics.mission_assign("vehicle_0") in topics
    assert Topics.mission_control("vehicle_0") in topics


def test_assign_message_updates_state_and_publishes_accepted_status():
    shared = SharedState()
    mqtt = FakeMqtt()
    service = MissionService("vehicle_0", shared, mqtt)

    mission_msg = MissionMessage(
        mission_id="m-accepted",
        vehicle_id="vehicle_0",
        waypoints=[Waypoint(x=10, y=20)],
    )
    service._on_mission_assign(FakeMsg(mission_msg.to_json()))

    mission = shared.get_mission()
    assert mission.mission_id == "m-accepted"
    assert mission.status == "executing"
    assert len(mqtt.published) == 1
    assert mqtt.published[0]["topic"] == Topics.mission_status("vehicle_0")
    assert mqtt.published[0]["qos"] == 1


def test_pause_resume_cancel_flow_for_active_mission():
    shared = SharedState()
    mqtt = FakeMqtt()
    service = MissionService("vehicle_0", shared, mqtt)
    shared.set_mission("m-ctrl", [Waypoint(x=1, y=1)])

    service._on_mission_control(
        FakeMsg(MissionControlMessage(mission_id="m-ctrl", command="pause").to_json())
    )
    assert shared.get_mission().status == "paused"

    service._on_mission_control(
        FakeMsg(MissionControlMessage(mission_id="m-ctrl", command="resume").to_json())
    )
    assert shared.get_mission().status == "executing"

    service._on_mission_control(
        FakeMsg(MissionControlMessage(mission_id="m-ctrl", command="cancel").to_json())
    )
    assert shared.get_mission().status == "cancelled"

    statuses = [entry["payload"] for entry in mqtt.published]
    assert any('"status": "paused"' in p for p in statuses)
    assert any('"status": "resumed"' in p for p in statuses)
    assert any('"status": "cancelled"' in p for p in statuses)


def test_control_for_other_mission_is_ignored():
    shared = SharedState()
    mqtt = FakeMqtt()
    service = MissionService("vehicle_0", shared, mqtt)
    shared.set_mission("m-current", [Waypoint(x=1, y=1)])

    service._on_mission_control(
        FakeMsg(MissionControlMessage(mission_id="m-other", command="cancel").to_json())
    )

    assert shared.get_mission().status == "executing"
    assert mqtt.published == []


def _published_status(mqtt):
    return MissionStatusMessage.from_json(mqtt.published[-1]["payload"])


def test_waypoint_reached_reports_given_mission_even_if_replaced():
    # Arrange
    shared = SharedState()
    mqtt = FakeMqtt()
    service = MissionService("vehicle_0", shared, mqtt)
    shared.set_mission("m-2", [Waypoint(x=1, y=1)])  # m-1 was replaced

    # Act
    service.notify_waypoint_reached("m-1", 3)

    # Assert
    status = _published_status(mqtt)
    assert (status.mission_id, status.status, status.current_waypoint_idx) == (
        "m-1",
        "waypoint_reached",
        3,
    )


def test_completed_reports_given_mission_even_if_replaced():
    # Arrange
    shared = SharedState()
    mqtt = FakeMqtt()
    service = MissionService("vehicle_0", shared, mqtt)
    shared.set_mission("m-2", [Waypoint(x=1, y=1)])  # m-1 was replaced

    # Act
    service.notify_completed("m-1", 4)

    # Assert
    status = _published_status(mqtt)
    assert (status.mission_id, status.status, status.current_waypoint_idx) == (
        "m-1",
        "completed",
        4,
    )


def _service_with_current_mission():
    shared = SharedState()
    mqtt = FakeMqtt()
    service = MissionService("vehicle_0", shared, mqtt)
    shared.set_mission("m-current", [Waypoint(x=1, y=1), Waypoint(x=2, y=2)])
    shared.advance_waypoint("m-current", 0)
    return shared, mqtt, service


@pytest.mark.parametrize(
    "waypoints",
    [
        [],
        [{"x": 1, "y": 1}, {"y": 2}],
        [{"x": "1", "y": 1}],
        [{"x": 1, "y": 1, "action": "wait", "params": {"duration": 0}}],
        [{"x": 1, "y": 1, "action": "jump"}],
    ],
)
def test_invalid_mission_is_rejected_and_current_mission_kept(waypoints):
    # Arrange
    shared, mqtt, service = _service_with_current_mission()
    payload = json.dumps(
        {"mission_id": "m-bad", "vehicle_id": "vehicle_0", "waypoints": waypoints}
    )

    # Act
    service._on_mission_assign(FakeMsg(payload))

    # Assert
    status = _published_status(mqtt)
    assert (status.mission_id, status.status) == ("m-bad", MissionEvent.REJECTED)
    assert "waypoints" in status.detail
    mission = shared.get_mission()
    assert (mission.mission_id, mission.current_waypoint_idx, mission.status) == (
        "m-current",
        1,
        MissionStatus.EXECUTING,
    )


@pytest.mark.parametrize(
    "payload",
    [
        "{not json",
        "[]",
        json.dumps({"waypoints": [{"x": 1, "y": 1}], "mission_id": 5}),
        json.dumps({"waypoints": []}),
    ],
)
def test_mission_without_usable_id_is_dropped_without_reply(payload):
    # Arrange
    shared, mqtt, service = _service_with_current_mission()

    # Act
    service._on_mission_assign(FakeMsg(payload))

    # Assert
    assert mqtt.published == []
    assert shared.get_mission().mission_id == "m-current"


def test_valid_mission_stores_typed_waypoints():
    # Arrange
    shared = SharedState()
    mqtt = FakeMqtt()
    service = MissionService("vehicle_0", shared, mqtt)
    payload = json.dumps(
        {
            "mission_id": "m-1",
            "waypoints": [
                {"x": 1, "y": 2, "action": "wait", "params": {"duration": 3}}
            ],
        }
    )

    # Act
    service._on_mission_assign(FakeMsg(payload))

    # Assert
    assert shared.get_current_waypoint() == Waypoint(
        x=1, y=2, action="wait", params={"duration": 3}
    )
    assert _published_status(mqtt).status is MissionEvent.ACCEPTED


@pytest.mark.parametrize(
    "payload",
    [
        json.dumps({"mission_id": "m-current", "command": "jump"}),
        json.dumps({"mission_id": "m-current"}),
        "{not json",
    ],
)
def test_invalid_mission_control_is_ignored(payload):
    # Arrange
    shared, mqtt, service = _service_with_current_mission()

    # Act
    service._on_mission_control(FakeMsg(payload))

    # Assert
    assert mqtt.published == []
    assert shared.get_mission().status is MissionStatus.EXECUTING
