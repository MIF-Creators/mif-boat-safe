"""Configuration loader – reads .env from the component's working directory."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv


def component_dotenv_path(module_file: str) -> Path:
    """Path to ``.env`` in the same directory as the component ``main.py``.

    Pass ``__file__`` from ``main.py`` so settings load correctly regardless of
    the current working directory (e.g. ``python -m system.navigation_server.main``
    from the repo root).
    """
    return Path(module_file).resolve().parent / ".env"


def _load_env(env_path: str | Path | None = None) -> None:
    """Load environment variables from ``.env``.

    If ``env_path`` points to an existing file, it is loaded with
    ``override=True`` so values in the file win over the shell environment.
    Otherwise falls back to :func:`load_dotenv` (searches from CWD).
    """
    if env_path is not None:
        p = Path(env_path)
        if p.is_file():
            load_dotenv(p, override=True)
            return
    load_dotenv()


def _csv_list(raw: str) -> list[str]:
    return [v.strip() for v in raw.split(",") if v.strip()]


def _csv_int_list(raw: str) -> list[int]:
    return [int(v.strip()) for v in raw.split(",") if v.strip()]


def _optional_int(name: str) -> int | None:
    """Integer from the environment; ``None`` when unset or empty."""
    raw = os.getenv(name, "").strip()
    return int(raw) if raw else None


def _optional_float(name: str) -> float | None:
    """Float from the environment; ``None`` when unset or empty."""
    raw = os.getenv(name, "").strip()
    return float(raw) if raw else None


# ---------------------------------------------------------------------------
# Config dataclasses
# ---------------------------------------------------------------------------


@dataclass
class MqttConfig:
    broker_host: str = "127.0.0.1"
    broker_port: int = 1883


@dataclass
class ControlCenterConfig(MqttConfig):
    flask_host: str = "127.0.0.1"
    flask_port: int = 8080
    vehicle_ids: list[str] = field(default_factory=lambda: ["vehicle_0"])

    @classmethod
    def load(cls, env_path: str | Path | None = None) -> ControlCenterConfig:
        _load_env(env_path)
        return cls(
            broker_host=os.getenv("MQTT_BROKER_HOST", "127.0.0.1"),
            broker_port=int(os.getenv("MQTT_BROKER_PORT", "1883")),
            flask_host=os.getenv("FLASK_HOST", "127.0.0.1"),
            flask_port=int(os.getenv("FLASK_PORT", "8080")),
            vehicle_ids=_csv_list(os.getenv("VEHICLE_IDS", "vehicle_0")),
        )


@dataclass
class NavigationServerConfig(MqttConfig):
    camera_device: str = "/dev/video0"
    camera_width: int = 1280
    camera_height: int = 720
    camera_skip_devices: list[str] = field(default_factory=list)
    camera_autofocus: int | None = None  # None = don't touch; 0 = off, 1 = on
    camera_focus: float | None = None  # manual focus value (V4L2 only)
    reference_marker_ids: list[int] = field(default_factory=lambda: [1, 2, 3, 4])
    mobile_marker_ids: list[int] = field(default_factory=lambda: [0])
    # Side of a reference marker along its outer black border, cm. Sets the
    # map units to centimetres; None = unitless map (width 100).
    reference_marker_size_cm: float | None = None
    # Field size in map units. None = measured by the field calibration;
    # both set = used as is, the measurement is only logged.
    map_width: int | None = None
    map_height: int | None = None
    map_obstacles: list[dict] = field(default_factory=list)
    publish_rate_hz: int = 15
    show_video_preview: bool = True
    preview_window_title: str = "Navigation Server"

    @classmethod
    def load(cls, env_path: str | Path | None = None) -> NavigationServerConfig:
        _load_env(env_path)
        obstacles_raw = os.getenv("MAP_OBSTACLES", "[]")
        try:
            obstacles = json.loads(obstacles_raw)
        except json.JSONDecodeError:
            obstacles = []

        skip_raw = os.getenv("CAMERA_SKIP_DEVICES", "")
        skip = _csv_list(skip_raw) if skip_raw else []

        autofocus_raw = os.getenv("CAMERA_AUTOFOCUS", "").strip()
        camera_autofocus = int(autofocus_raw) if autofocus_raw in ("0", "1") else None

        focus_raw = os.getenv("CAMERA_FOCUS", "").strip()
        camera_focus = float(focus_raw) if focus_raw else None

        preview_raw = os.getenv("SHOW_VIDEO_PREVIEW", "1").strip().lower()
        show_video_preview = preview_raw in ("1", "true", "yes", "on")

        return cls(
            broker_host=os.getenv("MQTT_BROKER_HOST", "192.168.1.100"),
            broker_port=int(os.getenv("MQTT_BROKER_PORT", "1883")),
            camera_device=os.getenv("CAMERA_DEVICE", "/dev/video0"),
            camera_width=int(os.getenv("CAMERA_WIDTH", "1280")),
            camera_height=int(os.getenv("CAMERA_HEIGHT", "720")),
            camera_skip_devices=skip,
            camera_autofocus=camera_autofocus,
            camera_focus=camera_focus,
            reference_marker_ids=_csv_int_list(
                os.getenv("REFERENCE_MARKER_IDS", "1,2,3,4")
            ),
            mobile_marker_ids=_csv_int_list(os.getenv("MOBILE_MARKER_IDS", "0")),
            reference_marker_size_cm=_optional_float("REFERENCE_MARKER_SIZE_CM"),
            map_width=_optional_int("MAP_WIDTH"),
            map_height=_optional_int("MAP_HEIGHT"),
            map_obstacles=obstacles,
            publish_rate_hz=int(os.getenv("PUBLISH_RATE_HZ", "15")),
            show_video_preview=show_video_preview,
            preview_window_title=os.getenv("PREVIEW_WINDOW_TITLE", "Navigation Server"),
        )


@dataclass
class VehicleConfig(MqttConfig):
    vehicle_id: str = "vehicle_0"
    aruco_marker_id: int = 0
    position_tolerance: float = 5.0
    angle_tolerance: float = 0.2
    nav_loop_rate_hz: int = 10
    pwm_duty_cycle: int = 20
    drive_command_timeout: float = 0.5
    position_timeout: float = 1.0

    @classmethod
    def load(cls, env_path: str | Path | None = None) -> VehicleConfig:
        _load_env(env_path)
        return cls(
            broker_host=os.getenv("MQTT_BROKER_HOST", "192.168.1.100"),
            broker_port=int(os.getenv("MQTT_BROKER_PORT", "1883")),
            vehicle_id=os.getenv("VEHICLE_ID", "vehicle_0"),
            aruco_marker_id=int(os.getenv("ARUCO_MARKER_ID", "0")),
            position_tolerance=float(os.getenv("POSITION_TOLERANCE", "5")),
            angle_tolerance=float(os.getenv("ANGLE_TOLERANCE", "0.2")),
            nav_loop_rate_hz=int(os.getenv("NAV_LOOP_RATE_HZ", "10")),
            pwm_duty_cycle=int(os.getenv("PWM_DUTY_CYCLE", "20")),
            drive_command_timeout=float(os.getenv("DRIVE_COMMAND_TIMEOUT", "0.5")),
            position_timeout=float(os.getenv("POSITION_TIMEOUT", "1.0")),
        )
