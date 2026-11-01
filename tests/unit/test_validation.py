import pytest

from system.common.messages import MissionMessage, Waypoint
from system.common.validation import validate_mission


def _mission(*waypoints):
    return MissionMessage(mission_id="m-1", waypoints=list(waypoints))


@pytest.mark.parametrize(
    "waypoints",
    [
        [Waypoint(x=1, y=2)],
        [Waypoint(x=1, y=2, action="stop")],
        [Waypoint(x=1, y=2, action="wait", params={"duration": 3})],
        [Waypoint(x=1, y=2, action="wait", params={"duration": 0.5})],
    ],
)
def test_valid_mission_has_no_errors(waypoints):
    assert validate_mission(_mission(*waypoints)) == []


def test_mission_without_waypoints_is_invalid():
    assert validate_mission(_mission()) == ["waypoints: mission has no waypoints"]


@pytest.mark.parametrize("params", [{}, {"duration": 0}, {"duration": -1}])
def test_wait_without_positive_duration_is_invalid(params):
    # Arrange
    mission = _mission(
        Waypoint(x=1, y=2),
        Waypoint(x=3, y=4, action="wait", params=params),
    )

    # Act
    errors = validate_mission(mission)

    # Assert
    assert errors == ["waypoints.1: wait needs params.duration > 0"]


def test_duration_is_not_checked_for_other_actions():
    mission = _mission(Waypoint(x=1, y=2, params={"duration": -1}))

    assert validate_mission(mission) == []
