import logging
import time
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
        self.completed = []

    def notify_waypoint_reached(self, mission_id, idx):
        self.reached.append((mission_id, idx))

    def notify_completed(self, mission_id, idx):
        self.completed.append((mission_id, idx))


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
    assert mission_svc.completed == [("m-done", 1)]
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

def test_safe_tick_stops_motors_on_error():
    # Arrange
    state = SharedState()
    state.set_mission("m-1", [{"y": 10}])  # broken waypoint: no "x"
    state.update_position(0, 0, 0)
    drive = FakeDrive()
    service = _create_service(state, drive=drive)

    # Act
    service._safe_tick()

    # Assert
    assert drive.commands == ["stop"]

def test_repeated_error_is_longer_once(caplog):
    # Arrange
    state = SharedState()
    state.set_mission("m-1", [{"y": 10}])
    state.update_position(0, 0, 0)
    service = _create_service(state)

    # Act
    with caplog.at_level(logging.ERROR):
        for _ in range(3):
            service._safe_tick()
    errors = [r for r in caplog.records if r.levelno == logging.ERROR]

    # Assert
    assert len(errors) == 1

def test_navigation_works_again_after_error():
    # Arrange
    state = SharedState()
    state.set_mission("m-1", [{"y": 5}])
    state.update_position(0, 0, 0)
    drive = FakeDrive()
    service = _create_service(state, drive=drive)
    service._safe_tick()
    assert drive.commands[-1] == "stop"  # precondition

    # Act
    state.set_mission("m-2", [{"x": 10, "y": 0}])
    service._safe_tick()

    # Assert
    assert drive.commands[-1] == "forward"

def test_navigation_thread_survives_errors():
    # Arrange
    state = SharedState()
    state.set_mission("m-1", [{"y": 5}])
    state.update_position(0, 0, 0)
    service = _create_service(state)

    # Act
    service.start()
    time.sleep(0.2)  # several ticks at 20 Hz
    alive = service._thread.is_alive()
    service.stop()

    # Assert
    assert alive

@pytest.fixture
def no_sleep(monkeypatch):
    """Fail the test if the code under test blocks in time.sleep."""
    def fail_sleep(seconds):
        raise AssertionError(f"tick blocked in time.sleep({seconds})")
    monkeypatch.setattr(time, "sleep", fail_sleep)

def _waiting_vehicle(clock, duration=5.0, mission_svc=None):
    """Vehicle standing at a waypoint with a wait action, next waypoint far away."""
    state = SharedState(clock=clock)
    state.set_mission("m-1", [
        {"x": 0, "y": 0, "action": "wait", "params": {"duration": duration}},
        {"x": 10, "y": 0},
    ])
    state.update_position(0, 0, 0)
    drive = FakeDrive()
    service = _create_service(state, drive=drive, mission_svc=mission_svc)
    return state, drive, service

def _tick_with_fresh_position(state, service, x=0, y=0):
    state.update_position(x, y, 0)
    service._tick()

def test_wait_does_not_finish_early(no_sleep):
    # Arrange
    clock = FakeClock()
    mission_svc = FakeMissionService()
    state, drive, service = _waiting_vehicle(clock, duration=5.0, mission_svc=mission_svc)

    # Act
    service._tick()
    for _ in range(4):
        clock.advance(1.0)
        _tick_with_fresh_position(state, service)
    clock.advance(0.9)
    _tick_with_fresh_position(state, service)

    # Assert
    assert state.get_mission().current_waypoint_idx == 0
    assert mission_svc.reached == []
    assert drive.commands == ["stop"] * 6

def test_wait_finishes_after_duration(no_sleep):
    # Arrange
    clock = FakeClock()
    mission_svc = FakeMissionService()
    state, drive, service = _waiting_vehicle(clock, duration=5.0, mission_svc=mission_svc)
    service._tick()

    # Act
    clock.advance(5.0)
    _tick_with_fresh_position(state, service)
    _tick_with_fresh_position(state, service)

    # Assert
    assert state.get_mission().current_waypoint_idx == 1
    assert mission_svc.reached == [("m-1", 0)]
    assert drive.commands[-1] == "forward"

def test_wait_continues_when_vehicle_drifts_or_position_is_stale(no_sleep):
    # Arrange
    clock = FakeClock()
    state, drive, service = _waiting_vehicle(clock, duration=5.0)
    service._tick()

    # Act
    clock.advance(1.0)
    _tick_with_fresh_position(state, service, x=3, y=3)  # outside tolerance
    clock.advance(2.0)
    service._tick()  # position is stale
    stopped_while_waiting = drive.commands[-1] == "stop"
    clock.advance(2.0)
    _tick_with_fresh_position(state, service, x=3, y=3)

    # Assert
    assert stopped_while_waiting
    assert state.get_mission().current_waypoint_idx == 1

@pytest.mark.parametrize(
        "status", ["paused", "cancelled"]
)
def test_pause_or_cancel_during_wait_stops_immediately(no_sleep, status):
    # Arrange
    clock = FakeClock()
    state, drive, service = _waiting_vehicle(clock, duration=5.0)
    service._tick()

    # Act
    state.set_mission_status(status)
    clock.advance(10.0)
    _tick_with_fresh_position(state, service)

    # Assert
    assert drive.commands[-1] == "stop"
    assert state.get_mission().current_waypoint_idx == 0

def test_wait_restarts_after_resume(no_sleep):
    # Arrange
    clock = FakeClock()
    state, drive, service = _waiting_vehicle(clock, duration=5.0)
    service._tick()
    clock.advance(4.0)
    state.set_mission_status("paused")
    _tick_with_fresh_position(state, service)

    # Act
    state.set_mission_status("executing")
    _tick_with_fresh_position(state, service)
    clock.advance(4.0)
    _tick_with_fresh_position(state, service)

    # Assert
    assert state.get_mission().current_waypoint_idx == 0
    assert drive.commands[-1] == "stop"

def test_new_mission_resets_wait(no_sleep):
    # Arrange
    clock = FakeClock()
    mission_svc = FakeMissionService()
    state, drive, service = _waiting_vehicle(clock, duration=5.0, mission_svc=mission_svc)
    service._tick()

    # Act
    state.set_mission("m-2", [{"x": 10, "y": 0}])
    _tick_with_fresh_position(state, service)

    # Assert
    assert drive.commands[-1] == "forward"
    clock.advance(10.0)
    _tick_with_fresh_position(state, service)
    assert state.get_mission().current_waypoint_idx == 0
    assert mission_svc.reached == []

def test_wait_after_cancel_does_not_carry_over_to_new_mission(no_sleep):
    # Arrange
    clock = FakeClock()
    state, drive, service = _waiting_vehicle(clock, duration=5.0)
    service._tick()
    state.set_mission_status("cancelled")
    service._tick()

    # Act
    state.set_mission("m-2", [{"x": 10, "y": 0}])
    _tick_with_fresh_position(state, service)

    # Assert
    assert drive.commands[-1] == "forward"


class MissionReplacingState(SharedState):
    """SharedState that swaps the mission at a chosen moment of a tick.

    Simulates the MQTT thread assigning a new mission while the navigation
    thread is between reading the mission and acting on it.
    """

    def __init__(self, replace_on, new_waypoints, **kwargs):
        super().__init__(**kwargs)
        self._replace_on = replace_on
        self._new_waypoints = new_waypoints
        self.replaced = False

    def _replace(self, method):
        if method == self._replace_on and not self.replaced:
            self.replaced = True
            self.set_mission("m-2", self._new_waypoints)

    def get_position(self):
        self._replace("get_position")
        return super().get_position()

    def advance_waypoint(self, mission_id, idx):
        advanced = super().advance_waypoint(mission_id, idx)
        self._replace("advance_waypoint")
        return advanced

def test_new_mission_waypoint_not_skipped_when_replaced_mid_tick():
    # Arrange
    state = MissionReplacingState(
        replace_on="get_position", new_waypoints=[{"x": 10, "y": 0}],
    )
    state.set_mission("m-1", [{"x": 0, "y": 0}, {"x": 5, "y": 5}])
    state.update_position(0, 0, 0)  # vehicle at m-1 waypoint 0
    mission_svc = FakeMissionService()
    service = _create_service(state, mission_svc=mission_svc)

    # Act
    service._tick()

    # Assert
    assert state.replaced
    mission = state.get_mission()
    assert (mission.mission_id, mission.current_waypoint_idx) == ("m-2", 0)
    assert mission_svc.reached == []
    assert mission_svc.completed == []

def test_old_wait_not_started_on_new_mission_when_replaced_mid_tick():
    # Arrange
    state = MissionReplacingState(
        replace_on="get_position", new_waypoints=[{"x": 10, "y": 0}],
        clock=FakeClock(),
    )
    state.set_mission("m-1", [{"x": 0, "y": 0, "action": "wait", "params": {"duration": 5}}])
    state.update_position(0, 0, 0)
    service = _create_service(state)

    # Act
    service._tick()

    # Assert
    assert state.replaced
    assert state.wait_remaining() is None

def test_completion_reported_for_finished_mission_when_replaced_after_advance():
    # Arrange
    state = MissionReplacingState(
        replace_on="advance_waypoint", new_waypoints=[{"x": 10, "y": 0}],
    )
    state.set_mission("m-1", [{"x": 0, "y": 0}])
    state.update_position(0, 0, 0)
    mission_svc = FakeMissionService()
    service = _create_service(state, mission_svc=mission_svc)

    # Act
    service._tick()

    # Assert
    assert state.replaced
    assert mission_svc.completed == [("m-1", 1)]
    assert mission_svc.reached == []
