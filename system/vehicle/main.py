"""Vehicle entry point – launches all service threads in a single process."""

import logging
import signal
import sys
import threading
import time

sys.path.insert(0, __file__.rsplit("/system/", 1)[0])

from system.common.config import VehicleConfig, component_dotenv_path
from system.common.messages import VehicleStatusMessage
from system.common.topics import Topics
from system.vehicle.shared_state import SharedState
from system.vehicle.mqtt_client import VehicleMqttClient
from system.vehicle.services.position_service import PositionService
from system.vehicle.services.mission_service import MissionService
from system.vehicle.services.drive_service import DriveService
from system.vehicle.services.navigation_service import NavigationService
from system.vehicle.services.obstacle_detection import ObstacleDetectionService
from system.vehicle.services.obstacle_avoidance import ObstacleAvoidanceService

logging.basicConfig(level=logging.INFO, format="%(asctime)s [VEHICLE] %(message)s")
log = logging.getLogger(__name__)


def main():
    cfg = VehicleConfig.load(env_path=component_dotenv_path(__file__))
    log.info("Vehicle ID: %s  (ArUco marker %d)", cfg.vehicle_id, cfg.aruco_marker_id)

    shared = SharedState(position_timeout=cfg.position_timeout)

    mqtt = VehicleMqttClient(cfg)
    mqtt.connect()
    time.sleep(0.5)

    position_svc = PositionService(cfg.vehicle_id, shared, mqtt)
    mission_svc = MissionService(cfg.vehicle_id, shared, mqtt)
    drive_svc = DriveService(duty_cycle=cfg.pwm_duty_cycle, command_timeout=cfg.drive_command_timeout)
    obstacle_det = ObstacleDetectionService(shared)
    obstacle_avoid = ObstacleAvoidanceService(obstacle_det)
    nav_svc = NavigationService(
        shared=shared,
        drive=drive_svc,
        avoidance=obstacle_avoid,
        mission_service=mission_svc,
        position_tolerance=cfg.position_tolerance,
        angle_tolerance=cfg.angle_tolerance,
        loop_rate_hz=cfg.nav_loop_rate_hz,
    )

    position_svc.start()
    mission_svc.start()
    drive_svc.start()
    obstacle_det.start()
    obstacle_avoid.start()
    nav_svc.start()

    log.info("All services started. Waiting for missions...")

    shutdown = threading.Event()

    def _signal_handler(sig, frame):
        log.info("Shutdown signal received")
        shutdown.set()

    signal.signal(signal.SIGINT, _signal_handler)
    signal.signal(signal.SIGTERM, _signal_handler)

    heartbeat_interval = 2.0
    while not shutdown.is_set():
        mission = shared.get_mission()
        status_msg = VehicleStatusMessage(
            vehicle_id=cfg.vehicle_id,
            state=mission.status,
            current_waypoint_idx=mission.current_waypoint_idx,
            mission_id=mission.mission_id,
        )
        mqtt.publish(Topics.vehicle_status(cfg.vehicle_id), status_msg.to_json())
        shutdown.wait(heartbeat_interval)

    log.info("Stopping services...")
    nav_svc.stop()
    drive_svc.stop()
    obstacle_avoid.stop()
    obstacle_det.stop()
    mqtt.disconnect()
    log.info("Done.")


if __name__ == "__main__":
    main()
