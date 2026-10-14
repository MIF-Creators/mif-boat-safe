from system.vehicle.services.drive_service import DriveService
from tests.unit.fakes import FakeClock

def _create_service(timeout: float = 0.5):
    clock = FakeClock()
    service = DriveService(command_timeout=timeout, clock=clock)
    applied_commands = []
    service._execute = applied_commands.append
    return service, clock, applied_commands


def test_applies_last_command():
    # Arrange
    command_name = "forward"
    service, _, applied_commands = _create_service()

    # Act
    service.send_command(command_name)
    service._step()

    # Assert
    assert applied_commands == [command_name]

def test_stops_motors_when_commands_stop_arriving():
    # Arrange
    startup_command_name = "forward"
    service, clock, applied_commands = _create_service(timeout=0.5)
    service.send_command(startup_command_name)
    service._step()
    assert applied_commands == [startup_command_name]

    # Act
    clock.advance(0.6)
    service._step()

    # Assert
    assert applied_commands[-1] == "stop"

def test_keeps_moving_while_commands_arrive_in_time():
    # Arrange
    command_name = "forward"
    service, clock, applied_commands = _create_service(timeout=0.5)

    # Act
    for _ in range(5):
        service.send_command(command_name)
        service._step()
        clock.advance(0.3)

    # Assert
    assert applied_commands == [command_name]

def test_repeated_command_does_not_restart_motors():
    # Arrange
    command_name = "forward"
    service, _, applied_commands = _create_service()

    # Act
    for _ in range(3):
        service.send_command(command_name)
        service._step()

    # Assert
    assert applied_commands == [command_name]

def test_stop_is_not_lost_after_many_commands():
    # Arrange
    command_name = "forward"
    stop_command = "stop"
    service, _, applied_commands = _create_service()

    for _ in range(50):
        service.send_command(command_name)

    # Act
    service.send_command(stop_command)
    service._step()

    # Assert
    assert applied_commands == [stop_command]

def test_moves_again_after_new_command_following_timeout():
    # Arrange
    service, clock, applied_commands = _create_service(timeout=0.5)
    service.send_command("forward")
    service._step()
    clock.advance(1.0)
    service._step()
    assert applied_commands == ["forward", "stop"]

    # Act
    service.send_command("left")
    service._step()

    # Assert
    assert applied_commands[-1] == "left"