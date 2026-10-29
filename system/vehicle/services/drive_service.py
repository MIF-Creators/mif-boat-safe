"""Motor control service – applies the latest drive command to GPIO.

If no new command arrives within the timeout, the motors are stopped
(watchdog), so a crashed or frozen navigation loop cannot leave them running.

Pin layout and motor functions taken directly from LocalNavigation/machine.py.
On non-Raspberry Pi systems a mock GPIO is used so the rest of the stack can
be developed and tested without hardware.
"""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable

from system.common.enums import StrValueEnum

log = logging.getLogger(__name__)

try:
    import RPi.GPIO as GPIO

    _HAS_GPIO = True
except (ImportError, RuntimeError):
    _HAS_GPIO = False
    log.warning("RPi.GPIO not available – using mock driver")


# ---------------------------------------------------------------------------
# Pin definitions (BOARD numbering)
# ---------------------------------------------------------------------------

PWMA_L = 36
AIN1_L = 40
AIN2_L = 38

PWMB_R = 33
BIN1_R = 35
BIN2_R = 37

PWM_FREQ = 255

LOOP_PERIOD = 0.02  # seconds between watchdog checks


class DriveCommand(StrValueEnum):
    """Command for the whole vehicle; FORWARD, BACKWARD and STOP also set one motor."""

    FORWARD = "forward"
    BACKWARD = "backward"
    LEFT = "left"
    RIGHT = "right"
    STOP = "stop"


class DriveService:
    """Consumes drive commands from a thread-safe queue and actuates motors."""

    def __init__(
        self,
        duty_cycle: int = 20,
        command_timeout: float = 0.5,
        clock: Callable[[], float] = time.monotonic,
    ):
        self._duty = duty_cycle
        self._timeout = command_timeout
        self._clock = clock
        self._command = DriveCommand.STOP
        self._applied_command: DriveCommand | None = None
        self._last_command_time = clock()
        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None
        self._running = False
        self._pwm_l = None
        self._pwm_r = None

    def start(self):
        self._init_gpio()
        self._thread = threading.Thread(
            target=self._loop, daemon=True, name=self.__class__.__name__
        )
        self._thread.start()
        self._running = True
        log.info(
            "DriveService started (GPIO=%s, duty=%d, timeout=%.2fs)",
            _HAS_GPIO,
            self._duty,
            self._timeout,
        )

    def send_command(self, command: DriveCommand):
        with self._lock:
            self._command = command
            self._last_command_time = self._clock()

    def stop(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=2)
        self._execute(DriveCommand.STOP)
        self._cleanup_gpio()

    def _loop(self):
        while self._running:
            self._step()
            time.sleep(LOOP_PERIOD)

    def _step(self):
        with self._lock:
            command = self._command
            is_expired = self._clock() - self._last_command_time > self._timeout

        target = DriveCommand.STOP if is_expired else command

        if target == self._applied_command:
            return

        if is_expired:
            log.warning("No drive commands for %.2fs, stopping motors", self._timeout)

        self._execute(target)
        self._applied_command = target

    def _execute(self, cmd: DriveCommand):
        self._motor_left(DriveCommand.STOP)
        self._motor_right(DriveCommand.STOP)

        if cmd == DriveCommand.FORWARD:
            self._motor_left(DriveCommand.FORWARD)
            self._motor_right(DriveCommand.FORWARD)
        elif cmd == DriveCommand.BACKWARD:
            self._motor_left(DriveCommand.BACKWARD)
            self._motor_right(DriveCommand.BACKWARD)
        elif cmd == DriveCommand.LEFT:
            self._motor_left(DriveCommand.BACKWARD)
            self._motor_right(DriveCommand.FORWARD)
        elif cmd == DriveCommand.RIGHT:
            self._motor_left(DriveCommand.FORWARD)
            self._motor_right(DriveCommand.BACKWARD)
        elif cmd == DriveCommand.STOP:
            pass
        else:
            log.warning("Unknown drive command: %s", cmd)

    # -- GPIO helpers (mirror machine.py) ----------------------------------

    def _init_gpio(self):
        if not _HAS_GPIO:
            return
        GPIO.setmode(GPIO.BOARD)
        for pin in (PWMA_L, AIN1_L, AIN2_L, PWMB_R, BIN1_R, BIN2_R):
            GPIO.setup(pin, GPIO.OUT)
        self._pwm_l = GPIO.PWM(PWMA_L, PWM_FREQ)
        self._pwm_l.start(0)
        self._pwm_r = GPIO.PWM(PWMB_R, PWM_FREQ)
        self._pwm_r.start(0)

    def _cleanup_gpio(self):
        if not _HAS_GPIO:
            return
        if self._pwm_l:
            self._pwm_l.stop()
        if self._pwm_r:
            self._pwm_r.stop()
        GPIO.cleanup()

    def _motor_left(self, direction: DriveCommand):
        if not _HAS_GPIO:
            return
        if direction == DriveCommand.FORWARD:
            GPIO.output(AIN1_L, GPIO.LOW)
            GPIO.output(AIN2_L, GPIO.HIGH)
            self._pwm_l.ChangeDutyCycle(self._duty)
        elif direction == DriveCommand.BACKWARD:
            GPIO.output(AIN1_L, GPIO.HIGH)
            GPIO.output(AIN2_L, GPIO.LOW)
            self._pwm_l.ChangeDutyCycle(self._duty)
        else:
            GPIO.output(AIN1_L, GPIO.LOW)
            GPIO.output(AIN2_L, GPIO.LOW)
            self._pwm_l.ChangeDutyCycle(0)

    def _motor_right(self, direction: DriveCommand):
        if not _HAS_GPIO:
            return
        if direction == DriveCommand.FORWARD:
            GPIO.output(BIN1_R, GPIO.HIGH)
            GPIO.output(BIN2_R, GPIO.LOW)
            self._pwm_r.ChangeDutyCycle(self._duty)
        elif direction == DriveCommand.BACKWARD:
            GPIO.output(BIN1_R, GPIO.LOW)
            GPIO.output(BIN2_R, GPIO.HIGH)
            self._pwm_r.ChangeDutyCycle(self._duty)
        else:
            GPIO.output(BIN1_R, GPIO.LOW)
            GPIO.output(BIN2_R, GPIO.LOW)
            self._pwm_r.ChangeDutyCycle(0)
