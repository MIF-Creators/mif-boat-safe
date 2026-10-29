import pytest

from system.common.enums import MissionStatus, VehicleState
from system.vehicle.main import vehicle_state_for


@pytest.mark.parametrize(
    "mission_status, expected",
    [
        (MissionStatus.IDLE, VehicleState.IDLE),
        (MissionStatus.EXECUTING, VehicleState.EXECUTING),
        (MissionStatus.PAUSED, VehicleState.PAUSED),
        (MissionStatus.COMPLETED, VehicleState.IDLE),
        (MissionStatus.CANCELLED, VehicleState.IDLE),
        (MissionStatus.FAILED, VehicleState.IDLE),
    ],
)
def test_heartbeat_state_follows_mission_status(mission_status, expected):
    assert vehicle_state_for(mission_status) is expected
