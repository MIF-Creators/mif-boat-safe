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

### 1. Install dependencies (all machines)

```bash
cd system
pip install -r requirements.txt
# On Raspberry Pi also:
pip install RPi.GPIO
```

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
cd system/navigation_server
cp .env.example .env
# Edit .env: set MQTT_BROKER_HOST to PC1 IP address
python -m system.navigation_server.main
```

Run from the repo root:

```bash
python -m system.navigation_server.main
```

### 4. Configure and run Vehicle (PC2 – Raspberry Pi)

```bash
cd system/vehicle
cp .env.example .env
# Edit .env: set MQTT_BROKER_HOST to PC1 IP address, configure VEHICLE_ID
python -m system.vehicle.main
```

Run from the repo root:

```bash
python -m system.vehicle.main
```

### 5. Configure and run Control Center (PC1)

```bash
cd system/control_center
cp .env.example .env
# Edit .env if needed (broker is localhost by default)
python -m system.control_center.main
```

Run from the repo root:

```bash
python -m system.control_center.main
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

## Configuration

Each component reads settings from a `.env` file next to that component’s `main.py` (for example `system/navigation_server/.env`). You can run `python -m system.navigation_server.main` from the repo root; the correct file is still loaded. Values in `.env` override the same variables if they were set in the shell. See `.env.example` files for available options.

**Navigation server — RTSP IP camera:** set `CAMERA_RTSP_URL=rtsp://...` in `.env`. The server loads `.env` before OpenCV so FFmpeg can use TCP (`CAMERA_RTSP_TCP=1`, default). If the stream stops after ~1 minute, the server reconnects automatically after `CAMERA_RTSP_RECONNECT_AFTER` failed reads (default 5). If problems persist, try `CAMERA_RTSP_TCP=0` (UDP).

**Video preview window:** with `SHOW_VIDEO_PREVIEW=1` (default), a window opens showing the stream with ArUco overlays; press **Q** to stop the server. Set `SHOW_VIDEO_PREVIEW=0` on machines without a display.

## Adding More Vehicles

1. Place a new ArUco marker (e.g., ID 5) on the vehicle.
2. Add the marker ID to `MOBILE_MARKER_IDS` in navigation server `.env`: `MOBILE_MARKER_IDS=0,5`
3. On the new Raspberry Pi, set `VEHICLE_ID=vehicle_5` and `ARUCO_MARKER_ID=5` in vehicle `.env`.
4. Add `vehicle_5` to `VEHICLE_IDS` in control center `.env`: `VEHICLE_IDS=vehicle_0,vehicle_5`
