import pytest

from system.vehicle.services.navigation_service import NavigationService
from system.vehicle.shared_state import SharedState
from tests.unit.fakes import FakeClock

class FakeDrive:
    def __init__(self):
        self.commands = []

    def send_command(self, cmd):
        self.commands.append(cmd)


class FakeAvoidance:
    def __init__(self, suffix=""):
        self.suffix = suffix
        self.raw_commands = []

    def filter_command(self, cmd):
        self.raw_commands.append(cmd)
        return f"{cmd}{self.suffix}"


class FakeMissionService:
    def __init__(self):
        self.reached = []
        self.completed_count = 0

    def notify_waypoint_reached(self, idx):
        self.reached.append(idx)

    def notify_completed(self):
        self.completed_count += 1


def _create_service(shared, drive=None, avoidance=None, mission_svc=None):
    return NavigationService(
        shared=shared,
        drive=drive or FakeDrive(),
        avoidance=avoidance or FakeAvoidance(),
        mission_service=mission_svc,
        position_tolerance=1.0,
        angle_tolerance=0.1,
        loop_rate_hz=20,
    )

@pytest.mark.parametrize(
        "status", ["idle", "paused", "completed", "cancelled", "failed"]
)
def test_tick_sends_stop_when_mission_not_executing(status):
    # Arrange
    shared_state = SharedState()
    shared_state.set_mission("m-1", [{"x": 10, "y": 10}])
    shared_state.set_mission_status(status)
    shared_state.update_position(0, 0, 0)
    drive = FakeDrive()
    nav_service = _create_service(shared_state, drive=drive)

    # Act
    nav_service._tick()

    # Assert
    assert drive.commands == ["stop"]

@pytest.mark.parametrize(
        "status", ["paused", "cancelled"]
)
def test_moving_vehicle_stops_after_pause_or_cancel(status):
    # Arrange
    shared_state = SharedState()
    shared_state.set_mission("m-1", [{"x": 10, "y": 0}])
    shared_state.update_position(0, 0, 0)
    drive = FakeDrive()
    nav_service = _create_service(shared_state, drive=drive)
    nav_service._tick()
    assert drive.commands[-1] == "forward"

    # Act
    shared_state.set_mission_status(status)
    nav_service._tick()

    # Assert
    assert drive.commands[-1] == "stop"

def test_tick_advances_waypoint_and_notifies_completion():
    shared = SharedState()
    shared.set_mission("m-done", [{"x": 0.1, "y": 0.1, "action": "stop"}])
    shared.update_position(0.0, 0.0, 0.0)

    drive = FakeDrive()
    mission_svc = FakeMissionService()
    svc = _create_service(shared, drive=drive, mission_svc=mission_svc)
    svc._tick()

    assert shared.get_mission().status == "completed"
    assert mission_svc.completed_count == 1
    # "action=stop" and completion branch both request stop
    assert drive.commands.count("stop") >= 1

def test_tick_sends_stop_when_position_never_received():
    # Arrange
    state = SharedState()
    state.set_mission("m-1", [{"x": 5, "y": 5}])
    drive = FakeDrive()
    service = _create_service(state, drive=drive)

    # Act
    service._tick()

    # Assert
    assert drive.commands == ["stop"]

def test_moving_vehicle_stops_when_position_becomes_stale():
    # Arrange
    clock = FakeClock()
    state = SharedState(position_timeout=1.0, clock=clock)
    state.set_mission("m-1", [{"x": 10, "y": 0}])
    state.update_position(0, 0, 0)
    drive = FakeDrive()
    service = _create_service(state, drive=drive)
    service._tick()
    assert drive.commands[-1] == "forward"

    # Act
    clock.advance(1.5)
    service._tick()

    # Assert
    assert drive.commands[-1] == "stop"
