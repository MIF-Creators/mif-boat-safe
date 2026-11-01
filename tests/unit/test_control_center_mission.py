import pytest
from pydantic import ValidationError

from system.common.enums import MissionEvent, MissionStatus, WaypointAction
from system.common.messages import Waypoint
from system.control_center.mission import MissionManager


def test_created_mission_is_pending():
    # Arrange
    manager = MissionManager()

    # Act
    manager.create_mission("vehicle_0", [{"x": 1, "y": 1}])

    # Assert
    assert manager.get_active("vehicle_0").status is MissionStatus.PENDING


@pytest.mark.parametrize(
    "event, expected",
    [
        (MissionEvent.ACCEPTED, MissionStatus.EXECUTING),
        (MissionEvent.WAYPOINT_REACHED, MissionStatus.EXECUTING),
        (MissionEvent.RESUMED, MissionStatus.EXECUTING),
        (MissionEvent.PAUSED, MissionStatus.PAUSED),
        (MissionEvent.COMPLETED, MissionStatus.COMPLETED),
        (MissionEvent.CANCELLED, MissionStatus.CANCELLED),
        (MissionEvent.FAILED, MissionStatus.FAILED),
        (MissionEvent.REJECTED, MissionStatus.FAILED),
    ],
)
def test_event_sets_mission_status(event, expected):
    # Arrange
    manager = MissionManager()
    mission_id = manager.create_mission(
        "vehicle_0", [{"x": 1, "y": 1}, {"x": 2, "y": 2}]
    ).mission_id

    # Act
    manager.update_status("vehicle_0", mission_id, event, 1)

    # Assert
    mission = manager.get_active("vehicle_0")
    assert (mission.status, mission.current_waypoint_idx) == (expected, 1)


def test_status_of_previous_mission_is_ignored():
    # Arrange
    manager = MissionManager()
    old_id = manager.create_mission("vehicle_0", [{"x": 1, "y": 1}]).mission_id
    manager.create_mission("vehicle_0", [{"x": 2, "y": 2}, {"x": 3, "y": 3}])

    # Act
    applied = manager.update_status("vehicle_0", old_id, MissionEvent.COMPLETED, 0)

    # Assert
    mission = manager.get_active("vehicle_0")
    assert not applied
    assert (mission.status, mission.current_waypoint_idx) == (
        MissionStatus.PENDING,
        0,
    )


def test_status_without_active_mission_is_ignored():
    # Arrange
    manager = MissionManager()

    # Act
    applied = manager.update_status(
        "vehicle_0", "some-mission", MissionEvent.ACCEPTED, 0
    )

    # Assert
    assert not applied
    assert manager.get_active("vehicle_0") is None


def test_stale_status_from_mqtt_is_ignored_and_logged(caplog):
    # Arrange
    from system.control_center import main as cc_main

    old_id = cc_main.mission_mgr.create_mission(
        "vehicle_stale", [{"x": 1, "y": 1}]
    ).mission_id
    cc_main.mission_mgr.create_mission("vehicle_stale", [{"x": 2, "y": 2}])

    # Act
    cc_main._on_mission_status(
        {
            "mission_id": old_id,
            "vehicle_id": "vehicle_stale",
            "status": "completed",
            "current_waypoint_idx": 0,
        }
    )

    # Assert
    assert cc_main.mission_mgr.get_active("vehicle_stale").status is (
        MissionStatus.PENDING
    )
    assert old_id in caplog.text


def test_unknown_event_from_mqtt_is_ignored(caplog):
    # Arrange
    from system.control_center import main as cc_main

    mission_id = cc_main.mission_mgr.create_mission(
        "vehicle_test", [{"x": 1, "y": 1}]
    ).mission_id

    # Act
    cc_main._on_mission_status(
        {
            "mission_id": mission_id,
            "vehicle_id": "vehicle_test",
            "status": "in_progress",
            "current_waypoint_idx": 0,
        }
    )

    # Assert
    assert cc_main.mission_mgr.get_active("vehicle_test").status is (
        MissionStatus.PENDING
    )
    assert "in_progress" in caplog.text


def test_created_mission_keeps_typed_waypoints():
    # Arrange
    manager = MissionManager()

    # Act
    manager.create_mission("vehicle_0", [{"x": 1, "y": 2, "action": "stop"}])

    # Assert
    assert manager.get_active("vehicle_0").waypoints == [
        Waypoint(x=1, y=2, action=WaypointAction.STOP)
    ]
    assert manager.get_all()["vehicle_0"]["waypoints"] == [
        {"x": 1.0, "y": 2.0, "action": "stop", "params": {}}
    ]


@pytest.mark.parametrize(
    "waypoints",
    [
        [{"y": 2}],
        [{"x": "1", "y": 2}],
        [{"x": 1, "y": 2, "action": "jump"}],
    ],
)
def test_waypoints_of_wrong_shape_are_not_registered(waypoints):
    # Arrange
    manager = MissionManager()

    # Act
    with pytest.raises(ValidationError):
        manager.create_mission("vehicle_0", waypoints)

    # Assert
    assert manager.get_active("vehicle_0") is None


def test_invalid_mission_status_from_mqtt_is_ignored(caplog):
    # Arrange
    from system.control_center import main as cc_main

    mission_id = cc_main.mission_mgr.create_mission(
        "vehicle_bad_status", [{"x": 1, "y": 1}]
    ).mission_id

    # Act
    cc_main._on_mission_status(
        {
            "mission_id": mission_id,
            "vehicle_id": "vehicle_bad_status",
            "status": "completed",
            "current_waypoint_idx": "last",
        }
    )

    # Assert
    assert cc_main.mission_mgr.get_active("vehicle_bad_status").status is (
        MissionStatus.PENDING
    )
    assert "current_waypoint_idx" in caplog.text


def test_valid_telemetry_from_mqtt_is_stored():
    # Arrange
    from system.control_center import main as cc_main

    # Act
    cc_main._on_position(
        {"vehicle_id": "vehicle_tm", "x": 1, "y": 2, "rotation": 0, "extra": 1}
    )
    cc_main._on_vehicle_status({"vehicle_id": "vehicle_tm", "state": "idle"})

    # Assert
    assert cc_main._vehicle_positions["vehicle_tm"]["x"] == 1.0
    assert "extra" not in cc_main._vehicle_positions["vehicle_tm"]
    assert cc_main._vehicle_statuses["vehicle_tm"]["state"] == "idle"


@pytest.mark.parametrize(
    "callback, data",
    [
        ("_on_position", {"vehicle_id": "vehicle_bad", "x": "1", "y": 2}),
        ("_on_vehicle_status", {"vehicle_id": "vehicle_bad", "state": "flying"}),
    ],
)
def test_invalid_telemetry_from_mqtt_is_ignored(callback, data):
    # Arrange
    from system.control_center import main as cc_main

    # Act
    getattr(cc_main, callback)(data)

    # Assert
    assert "vehicle_bad" not in cc_main._vehicle_positions
    assert "vehicle_bad" not in cc_main._vehicle_statuses


def test_invalid_map_from_mqtt_is_ignored(monkeypatch):
    # Arrange
    from system.control_center import main as cc_main

    monkeypatch.setattr(cc_main, "_map_data", {"width": 10})

    # Act
    cc_main._on_map_response({"obstacles": [{"type": "triangle"}]})

    # Assert
    assert cc_main._map_data == {"width": 10}
