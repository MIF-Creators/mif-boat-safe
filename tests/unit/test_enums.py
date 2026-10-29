import json

import pytest

from system.common.enums import (
    MissionCommand,
    MissionEvent,
    MissionStatus,
    VehicleState,
)
from system.common.messages import (
    MissionControlMessage,
    MissionStatusMessage,
    VehicleStatusMessage,
)
from system.vehicle.services.drive_service import DriveCommand

ALL_ENUMS = [MissionStatus, MissionEvent, VehicleState, MissionCommand, DriveCommand]


@pytest.mark.parametrize(
    "member", [member for enum in ALL_ENUMS for member in enum], ids=str
)
def test_enum_member_serializes_as_its_value(member):
    assert json.dumps(member) == f'"{member.value}"'
    assert str(member) == member.value
    assert f"{member}" == member.value


@pytest.mark.parametrize(
    "enum, values",
    [
        (
            MissionStatus,
            {
                "pending",
                "idle",
                "executing",
                "paused",
                "completed",
                "cancelled",
                "failed",
            },
        ),
        (
            MissionEvent,
            {
                "accepted",
                "rejected",
                "waypoint_reached",
                "paused",
                "resumed",
                "completed",
                "cancelled",
                "failed",
            },
        ),
        (VehicleState, {"idle", "executing", "paused", "error"}),
        (MissionCommand, {"cancel", "pause", "resume"}),
        (DriveCommand, {"forward", "backward", "left", "right", "stop"}),
    ],
)
def test_enum_has_agreed_wire_values(enum, values):
    assert {member.value for member in enum} == values


@pytest.mark.parametrize("event", list(MissionEvent))
def test_mission_status_message_round_trip(event):
    # Arrange
    msg = MissionStatusMessage(mission_id="m-1", vehicle_id="vehicle_0", status=event)

    # Act
    payload = msg.to_json()
    parsed = MissionStatusMessage.from_json(payload)

    # Assert
    assert json.loads(payload)["status"] == event.value
    assert parsed.status is event


@pytest.mark.parametrize("command", list(MissionCommand))
def test_mission_control_message_round_trip(command):
    # Arrange
    msg = MissionControlMessage(mission_id="m-1", command=command)

    # Act
    payload = msg.to_json()
    parsed = MissionControlMessage.from_json(payload)

    # Assert
    assert json.loads(payload)["command"] == command.value
    assert parsed.command is command


@pytest.mark.parametrize("state", list(VehicleState))
def test_vehicle_status_message_round_trip(state):
    # Arrange
    msg = VehicleStatusMessage(vehicle_id="vehicle_0", state=state)

    # Act
    payload = msg.to_json()
    parsed = VehicleStatusMessage.from_json(payload)

    # Assert
    assert json.loads(payload)["state"] == state.value
    assert parsed.state is state


def test_vehicle_status_message_defaults_to_idle():
    assert VehicleStatusMessage().state is VehicleState.IDLE


@pytest.mark.parametrize(
    "message_cls, payload",
    [
        (MissionStatusMessage, '{"mission_id": "m-1", "status": "in_progress"}'),
        (MissionControlMessage, '{"mission_id": "m-1", "command": "stop"}'),
        (VehicleStatusMessage, '{"vehicle_id": "vehicle_0", "state": "completed"}'),
    ],
)
def test_unknown_value_is_rejected_on_parse(message_cls, payload):
    with pytest.raises(ValueError):
        message_cls.from_json(payload)
