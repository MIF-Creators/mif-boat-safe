import pytest

from system.common.enums import MissionEvent, MissionStatus
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
