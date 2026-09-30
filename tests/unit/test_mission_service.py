from system.common.messages import MissionControlMessage, MissionMessage
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
        waypoints=[{"x": 10, "y": 20}],
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
    shared.set_mission("m-ctrl", [{"x": 1, "y": 1}])

    service._on_mission_control(FakeMsg(MissionControlMessage(mission_id="m-ctrl", command="pause").to_json()))
    assert shared.get_mission().status == "paused"

    service._on_mission_control(FakeMsg(MissionControlMessage(mission_id="m-ctrl", command="resume").to_json()))
    assert shared.get_mission().status == "executing"

    service._on_mission_control(FakeMsg(MissionControlMessage(mission_id="m-ctrl", command="cancel").to_json()))
    assert shared.get_mission().status == "cancelled"

    statuses = [entry["payload"] for entry in mqtt.published]
    assert any('"status": "paused"' in p for p in statuses)
    assert any('"status": "in_progress"' in p for p in statuses)
    assert any('"status": "cancelled"' in p for p in statuses)


def test_control_for_other_mission_is_ignored():
    shared = SharedState()
    mqtt = FakeMqtt()
    service = MissionService("vehicle_0", shared, mqtt)
    shared.set_mission("m-current", [{"x": 1, "y": 1}])

    service._on_mission_control(FakeMsg(MissionControlMessage(mission_id="m-other", command="cancel").to_json()))

    assert shared.get_mission().status == "executing"
    assert mqtt.published == []
