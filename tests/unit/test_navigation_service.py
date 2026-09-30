from system.vehicle.services.navigation_service import NavigationService
from system.vehicle.shared_state import SharedState


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


def test_tick_does_nothing_when_mission_not_executing():
    shared = SharedState()
    shared.set_mission("m-idle", [{"x": 10, "y": 10}])
    shared.set_mission_status("paused")
    shared.update_position(0, 0, 0)

    drive = FakeDrive()
    svc = _create_service(shared, drive=drive)
    svc._tick()

    assert drive.commands == []


def test_tick_sends_turn_command_based_on_heading_error():
    shared = SharedState()
    shared.set_mission("m-turn", [{"x": 0, "y": 10}])  # desired angle ~ +pi/2
    shared.update_position(0, 0, 0)  # heading to +x -> should rotate left

    drive = FakeDrive()
    avoidance = FakeAvoidance(suffix="_safe")
    svc = _create_service(shared, drive=drive, avoidance=avoidance)
    svc._tick()

    assert avoidance.raw_commands == ["left"]
    assert drive.commands == ["left_safe"]


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


def test_tick_skips_when_position_invalid():
    shared = SharedState()
    shared.set_mission("m-invalid-pos", [{"x": 5, "y": 5}])
    # position.valid remains False by default
    drive = FakeDrive()
    svc = _create_service(shared, drive=drive)

    svc._tick()

    assert drive.commands == []
