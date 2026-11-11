# Distributed Vehicle Control System

Multi-component MQTT-based system for tracking and controlling robotic vehicles using ArUco markers.

## Architecture

```
PC1 (Control Center + MQTT Broker)
  └─ system/control_center   – web UI for mission management
  └─ Mosquitto MQTT broker

PC2 (Raspberry Pi 4 – Vehicle)
  └─ system/vehicle           – mission execution, motor control

PC3 (Navigation Server)
  └─ system/navigation_server – camera + ArUco tracking, position publishing
```

All components communicate through a single MQTT broker.

## Prerequisites

- Python 3.10+
- Mosquitto MQTT broker (on PC1)
- USB camera (on PC3)
- Raspberry Pi 4 with GPIO motors (on PC2)

## Quick Start

### 1. Install (all machines)

From the repo root, in a virtual environment, install the dependency groups
for what runs on the machine (all groups are defined in `pyproject.toml`):

| Machine | Command |
|---|---|
| PC1 – Control Center | `pip install -e ".[control]"` |
| PC2 – Vehicle (Raspberry Pi) | `pip install -e ".[vehicle,rpi]"` |
| PC3 – Navigation Server | `pip install -e ".[nav]"` |
| Development (all components and tests) | `pip install -e ".[vehicle,nav,control,dev]"` |

The `rpi` group installs `RPi.GPIO` and only builds on a Raspberry Pi. Without it
the vehicle runs a mock motor driver, so do not forget it on the boat.

`pip install -e .` installs the `system` package in editable mode and adds the
console commands `boat-vehicle`, `boat-nav` and `boat-control`. After that each
component can be started either by its command or with
`python -m system.<component>.main` from any directory.

### 2. Start MQTT Broker (PC1)

Install Mosquitto:

```bash
# Ubuntu/Debian
sudo apt install mosquitto

# macOS
brew install mosquitto
```

Create `mosquitto.conf`:

```
listener 1883 0.0.0.0
allow_anonymous true
```

Run:

```bash
mosquitto -c mosquitto.conf
```

### 3. Configure and run Navigation Server (PC3)

```bash
cp system/navigation_server/.env.example system/navigation_server/.env
# Edit .env: set MQTT_BROKER_HOST to PC1 IP address
boat-nav
# or: python -m system.navigation_server.main
```

### 4. Configure and run Vehicle (PC2 – Raspberry Pi)

```bash
cp system/vehicle/.env.example system/vehicle/.env
# Edit .env: set MQTT_BROKER_HOST to PC1 IP address, configure VEHICLE_ID
boat-vehicle
# or: python -m system.vehicle.main
```

### 5. Configure and run Control Center (PC1)

```bash
cp system/control_center/.env.example system/control_center/.env
# Edit .env if needed (broker is localhost by default)
boat-control
# or: python -m system.control_center.main
```

Open browser: `http://localhost:8080`

## MQTT Topics

| Topic | Publisher | Subscriber | Description |
|-------|-----------|------------|-------------|
| `nav/{vehicle_id}/position` | Nav Server | Vehicle, Control Center | Position + rotation |
| `vehicle/{vehicle_id}/mission/assign` | Control Center | Vehicle | New mission |
| `vehicle/{vehicle_id}/mission/control` | Control Center | Vehicle | Pause/resume/cancel |
| `vehicle/{vehicle_id}/mission/status` | Vehicle | Control Center | Mission progress |
| `vehicle/{vehicle_id}/status` | Vehicle | Control Center | Heartbeat |
| `control/map/request` | Control Center | Nav Server | Request map |
| `control/map/response` | Nav Server | Control Center | Map JSON |

### Status and command values

Values are defined as enums in `system/common/enums.py` and sent as plain
strings in JSON.

| Topic, field | Enum | Values |
|---|---|---|
| `vehicle/{vehicle_id}/mission/status`, `status` | `MissionEvent` | `accepted`, `rejected`, `waypoint_reached`, `paused`, `resumed`, `completed`, `cancelled`, `failed` |
| `vehicle/{vehicle_id}/status`, `state` | `VehicleState` | `idle`, `executing`, `paused`, `error` |
| `vehicle/{vehicle_id}/mission/control`, `command` | `MissionCommand` | `cancel`, `pause`, `resume` |
| `/api/missions`, `status` (Control Center web API) | `MissionStatus` | `pending`, `executing`, `paused`, `completed`, `cancelled`, `failed` |

- `MissionEvent` says what happened to a mission. The Control Center turns
  events into the mission status: `accepted`, `waypoint_reached` and
  `resumed` → `executing`; `paused` → `paused`; `completed` and `cancelled` →
  the same status; `failed` and `rejected` → `failed`. A mission that was sent
  but not answered yet is `pending`.
- `VehicleState` is the state of the vehicle, not of its mission: after a
  mission is completed, cancelled or failed the vehicle is `idle`.
- `rejected` and `failed` events and the `error` state are reserved: nothing
  sends them yet.

## Configuration

Each component reads settings from a `.env` file next to that component’s `main.py` (for example `system/navigation_server/.env`). The working directory does not matter: `boat-nav` or `python -m system.navigation_server.main` loads the same file. Values in `.env` override the same variables if they were set in the shell. See `.env.example` files for available options.

**Navigation server — RTSP IP camera:** set `CAMERA_RTSP_URL=rtsp://...` in `.env`. The server loads `.env` before OpenCV so FFmpeg can use TCP (`CAMERA_RTSP_TCP=1`, default). If the stream stops after ~1 minute, the server reconnects automatically after `CAMERA_RTSP_RECONNECT_AFTER` failed reads (default 5). If problems persist, try `CAMERA_RTSP_TCP=0` (UDP).

**Video preview window:** with `SHOW_VIDEO_PREVIEW=1` (default), a window opens showing the stream with ArUco overlays; press **Q** to stop the server. Set `SHOW_VIDEO_PREVIEW=0` on machines without a display.

## Field calibration

The navigation server measures the field itself, no tape measure needed. At
startup it collects 30 frames in which all 4 reference markers are visible
and only then starts publishing positions and answers map requests.

How it works: the reference markers are squares of the same size. The
perspective transform from their centres is known only up to the field
size; the size follows from the requirement that every marker is a square
again on the map (equal sides, right angle). This gives the aspect ratio
of the field, and `REFERENCE_MARKER_SIZE_CM` gives the scale.

The map is then in centimetres: (0, 0) is the centre of marker 1, X runs
towards marker 4, Y towards marker 2; markers 2, 3, 4 are at (0, H), (W, H),
(W, 0). `MAP_OBSTACLES` and the vehicle's `POSITION_TOLERANCE` use the same
units. Without `REFERENCE_MARKER_SIZE_CM` the map is unitless (width 100);
with both `MAP_WIDTH` and `MAP_HEIGHT` set, they are used instead of the
measurement.

Conditions:

- markers 1-4 lie at the corners of a rectangle, flat on the floor the
  vehicles drive on, all of the same printed size;
- `REFERENCE_MARKER_SIZE_CM` is measured along the outer black border;
- markers at least ~20 px in the image (about 24 px for a 4 m field in a
  1280 px frame); the camera and markers do not move after the start —
  restart the server if they do.

The log shows the field size, the aspect ratio, the spread between the
per-marker estimates and the marker size in pixels. A spread above 5% means
the field is probably not a rectangle or the markers differ in size.

## Adding More Vehicles

1. Place a new ArUco marker (e.g., ID 5) on the vehicle.
2. Add the marker ID to `MOBILE_MARKER_IDS` in navigation server `.env`: `MOBILE_MARKER_IDS=0,5`
3. On the new Raspberry Pi, set `VEHICLE_ID=vehicle_5` and `ARUCO_MARKER_ID=5` in vehicle `.env`.
4. Add `vehicle_5` to `VEHICLE_IDS` in control center `.env`: `VEHICLE_IDS=vehicle_0,vehicle_5`
