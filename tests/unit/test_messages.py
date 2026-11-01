import json

import pytest
from pydantic import ValidationError

from system.common.enums import (
    MissionCommand,
    MissionEvent,
    ObstacleShape,
    VehicleState,
    WaypointAction,
)
from system.common.messages import (
    MapMessage,
    MapRequestMessage,
    MissionControlMessage,
    MissionMessage,
    MissionStatusMessage,
    NeighborInfo,
    ObstacleInfo,
    PositionMessage,
    VehicleStatusMessage,
    Waypoint,
    describe_error,
)


def _payload(**fields):
    return json.dumps(fields)


# -- Waypoint ----------------------------------------------------------------


@pytest.mark.parametrize(
    "data, expected",
    [
        ({"x": 1, "y": 2.5}, Waypoint(x=1.0, y=2.5)),
        (
            {"x": 1, "y": 2, "action": "stop"},
            Waypoint(x=1, y=2, action=WaypointAction.STOP),
        ),
        (
            {"x": 1, "y": 2, "action": "wait", "params": {"duration": 3}},
            Waypoint(x=1, y=2, action=WaypointAction.WAIT, params={"duration": 3}),
        ),
    ],
)
def test_valid_waypoint_is_parsed(data, expected):
    # Act
    waypoint = Waypoint.model_validate(data)

    # Assert
    assert waypoint == expected


@pytest.mark.parametrize(
    "data",
    [
        {"y": 2},  # no x
        {"x": 1},  # no y
        {"x": "1", "y": 2},  # string instead of number
        {"x": True, "y": 2},  # bool is not a number
        {"x": float("nan"), "y": 2},
        {"x": 1, "y": float("inf")},
        {"x": 1, "y": 2, "action": "jump"},
        {"x": 1, "y": 2, "action": "wait", "params": {"duration": "3"}},
        {"x": 1, "y": 2, "action": "wait", "params": {"duration": True}},
        {"x": 1, "y": 2, "action": "wait", "params": {"duration": float("inf")}},
        {"x": 1, "y": 2, "params": "3"},
    ],
)
def test_waypoint_of_wrong_shape_is_rejected(data):
    with pytest.raises(ValidationError):
        Waypoint.model_validate(data)


def test_waypoint_action_defaults_to_none():
    assert Waypoint(x=1, y=2).action is WaypointAction.NONE


# -- MissionMessage ----------------------------------------------------------


def test_mission_roundtrip_keeps_typed_waypoints():
    # Arrange
    mission = MissionMessage(
        mission_id="m-1",
        vehicle_id="vehicle_0",
        waypoints=[{"x": 1, "y": 2, "action": "wait", "params": {"duration": 3}}],
    )

    # Act
    parsed = MissionMessage.from_json(mission.to_json())

    # Assert
    assert parsed == mission
    assert parsed.waypoints == [
        Waypoint(x=1, y=2, action=WaypointAction.WAIT, params={"duration": 3})
    ]


def test_mission_without_waypoints_parses_as_empty_list():
    # Rules like "a mission needs waypoints" are checked by validation.py.
    mission = MissionMessage.from_json(_payload(mission_id="m-1", waypoints=[]))

    assert mission.waypoints == []


@pytest.mark.parametrize(
    "waypoints",
    [
        [{"x": 1, "y": 2}, {"y": 3}],
        "not a list",
    ],
)
def test_mission_with_waypoints_of_wrong_shape_is_rejected(waypoints):
    with pytest.raises(ValidationError):
        MissionMessage.from_json(_payload(mission_id="m-1", waypoints=waypoints))


def test_mission_without_waypoints_field_is_rejected():
    with pytest.raises(ValidationError):
        MissionMessage.from_json(_payload(mission_id="m-1"))


# -- MissionControlMessage ---------------------------------------------------


def test_mission_control_is_parsed():
    # Act
    ctrl = MissionControlMessage.from_json(_payload(mission_id="m-1", command="pause"))

    # Assert
    assert ctrl.command is MissionCommand.PAUSE


@pytest.mark.parametrize(
    "fields",
    [
        {"mission_id": "m-1"},
        {"mission_id": "m-1", "command": "jump"},
        {"mission_id": 1, "command": "pause"},
    ],
)
def test_invalid_mission_control_is_rejected(fields):
    with pytest.raises(ValidationError):
        MissionControlMessage.from_json(_payload(**fields))


# -- MissionStatusMessage ----------------------------------------------------


def test_mission_status_is_parsed():
    # Act
    status = MissionStatusMessage.from_json(
        _payload(mission_id="m-1", status="rejected", detail="bad waypoint")
    )

    # Assert
    assert (status.status, status.detail) == (MissionEvent.REJECTED, "bad waypoint")


@pytest.mark.parametrize(
    "fields",
    [
        {"mission_id": "m-1"},
        {"mission_id": "m-1", "status": "in_progress"},
        {"mission_id": "m-1", "status": "completed", "current_waypoint_idx": "1"},
    ],
)
def test_invalid_mission_status_is_rejected(fields):
    with pytest.raises(ValidationError):
        MissionStatusMessage.from_json(_payload(**fields))


# -- VehicleStatusMessage ----------------------------------------------------


def test_vehicle_status_is_parsed():
    # Act
    status = VehicleStatusMessage.from_json(
        _payload(vehicle_id="vehicle_0", state="executing", mission_id="m-1")
    )

    # Assert
    assert status.state is VehicleState.EXECUTING


@pytest.mark.parametrize("state", ["flying", None, 1])
def test_vehicle_status_with_unknown_state_is_rejected(state):
    with pytest.raises(ValidationError):
        VehicleStatusMessage.from_json(_payload(vehicle_id="vehicle_0", state=state))


# -- PositionMessage ---------------------------------------------------------


def test_position_is_parsed_with_typed_neighbors():
    # Act
    pos = PositionMessage.from_json(
        _payload(
            vehicle_id="vehicle_0",
            x=1,
            y=2,
            rotation=0.5,
            neighbors=[{"vehicle_id": "vehicle_1", "x": 3, "y": 4, "rotation": 0}],
        )
    )

    # Assert
    assert (pos.x, pos.y, pos.rotation) == (1.0, 2.0, 0.5)
    assert pos.neighbors == [NeighborInfo(vehicle_id="vehicle_1", x=3, y=4, rotation=0)]


@pytest.mark.parametrize(
    "fields",
    [
        {"vehicle_id": "vehicle_0", "y": 2, "rotation": 0},  # no x
        {"vehicle_id": "vehicle_0", "x": "1", "y": 2, "rotation": 0},
        {"vehicle_id": "vehicle_0", "x": 1, "y": 2},  # no rotation
        {
            "vehicle_id": "vehicle_0",
            "x": 1,
            "y": 2,
            "rotation": 0,
            "neighbors": [{"vehicle_id": "vehicle_1", "y": 4, "rotation": 0}],
        },
    ],
)
def test_invalid_position_is_rejected(fields):
    with pytest.raises(ValidationError):
        PositionMessage.from_json(_payload(**fields))


# -- MapMessage --------------------------------------------------------------


def test_map_is_parsed_with_typed_obstacles():
    # Act
    map_msg = MapMessage.from_json(
        _payload(
            width=100,
            height=50,
            reference_markers={"1": [0, 0]},
            obstacles=[{"type": "circle", "x": 10, "y": 10, "radius": 5}],
        )
    )

    # Assert
    assert map_msg.obstacles == [
        ObstacleInfo(type=ObstacleShape.CIRCLE, x=10, y=10, radius=5)
    ]
    assert map_msg.reference_markers == {"1": (0.0, 0.0)}


@pytest.mark.parametrize(
    "fields",
    [
        {"obstacles": [{"type": "triangle"}]},
        {"obstacles": [{"x": 1}]},  # no type
        {"obstacles": [{"type": "circle", "radius": "5"}]},
        {"reference_markers": {"1": [0]}},
        {"width": "100"},
    ],
)
def test_invalid_map_is_rejected(fields):
    with pytest.raises(ValidationError):
        MapMessage.from_json(_payload(**fields))


def test_map_request_roundtrip():
    # Arrange
    request = MapRequestMessage(timestamp=123.0)

    # Act
    parsed = MapRequestMessage.from_json(request.to_json())

    # Assert
    assert parsed == request


# -- Common behavior ---------------------------------------------------------


@pytest.mark.parametrize(
    "message_cls",
    [
        PositionMessage,
        MissionMessage,
        MissionControlMessage,
        MissionStatusMessage,
        VehicleStatusMessage,
        MapMessage,
        MapRequestMessage,
    ],
)
@pytest.mark.parametrize("payload", ["{not json", b"\xff", "[]", "null"])
def test_payload_that_is_not_a_json_object_is_rejected(message_cls, payload):
    with pytest.raises(ValidationError):
        message_cls.from_json(payload)


def test_unknown_fields_are_ignored():
    # Arrange
    payload = _payload(
        mission_id="m-1",
        command="pause",
        priority="high",  # field from a newer sender
    )

    # Act
    ctrl = MissionControlMessage.from_json(payload)

    # Assert
    assert ctrl.command is MissionCommand.PAUSE
    assert not hasattr(ctrl, "priority")


def test_unknown_fields_of_nested_models_are_ignored():
    # Act
    mission = MissionMessage.from_json(
        _payload(mission_id="m-1", waypoints=[{"x": 1, "y": 2, "speed": 3}])
    )

    # Assert
    assert mission.waypoints == [Waypoint(x=1, y=2)]


def test_from_json_accepts_bytes():
    # Act
    ctrl = MissionControlMessage.from_json(
        b'{"mission_id": "m-1", "command": "cancel"}'
    )

    # Assert
    assert ctrl.command is MissionCommand.CANCEL


def test_to_json_writes_enums_as_plain_values():
    # Arrange
    status = MissionStatusMessage(
        timestamp=1.0, mission_id="m-1", status=MissionEvent.ACCEPTED
    )

    # Act
    data = json.loads(status.to_json())

    # Assert
    assert data == {
        "timestamp": 1.0,
        "mission_id": "m-1",
        "vehicle_id": "",
        "status": "accepted",
        "current_waypoint_idx": 0,
        "detail": "",
    }


def test_describe_error_names_field_and_problem():
    # Arrange
    with pytest.raises(ValidationError) as exc_info:
        MissionMessage.from_json(_payload(mission_id="m-1", waypoints=[{"y": 1}]))

    # Act
    text = describe_error(exc_info.value)

    # Assert
    assert "waypoints.0.x" in text
    assert "required" in text.lower()
