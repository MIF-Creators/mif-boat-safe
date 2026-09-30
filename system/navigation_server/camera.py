"""Camera management for the navigation server."""

from __future__ import annotations

import glob
from typing import Any
import logging
import os
import time

# FFmpeg options must be set before OpenCV loads libav* (first import cv2 in this process).
# `.env` must be loaded in main.py before importing this module.
if os.environ.get("CAMERA_RTSP_URL", "").strip():
    if os.getenv("CAMERA_RTSP_TCP", "1").lower() in ("1", "true", "yes"):
        os.environ.setdefault(
            "OPENCV_FFMPEG_CAPTURE_OPTIONS",
            "rtsp_transport;tcp|fflags;nobuffer|flags;low_delay",
        )

import cv2

log = logging.getLogger(__name__)


class CameraManager:
    """Finds and manages a V4L2 camera device."""

    def __init__(self, device: str | None = None, skip_devices: list[str] | None = None,
                 width: int = 1280, height: int = 720,
                 autofocus: int | None = None, focus: float | None = None):
        self.device = device
        self.skip_devices = skip_devices or []
        self.width = width
        self.height = height
        self.autofocus = autofocus
        self.focus = focus
        self.cap: cv2.VideoCapture | None = None
        self.camera_path: str | None = None
        self._is_rtsp = False
        self._read_failures = 0
        self._rtsp_reconnect_after = int(os.getenv("CAMERA_RTSP_RECONNECT_AFTER", "5"))
        self.rtsp_url = os.environ.get("CAMERA_RTSP_URL", "").strip() or None

    def open(self) -> bool:
        """Open RTSP (if CAMERA_RTSP_URL), a specific device, or auto-detect V4L2."""
        if self.rtsp_url:
            return self._try_open_rtsp(self.rtsp_url)
        if self.device:
            return self._try_open_v4l2(self.device)
        return self._find_available()

    def _try_open(self, path: str) -> bool:
        """Open a stream URL (FFmpeg) or a V4L2 device path."""
        p = path.strip()
        if p.lower().startswith(
            ("rtsp://", "rtsps://", "rtmp://", "http://", "https://")
        ):
            return self._try_open_rtsp(p)
        return self._try_open_v4l2(p)

    def _try_open_rtsp(self, url: str) -> bool:
        self._is_rtsp = True
        # CAP_FFMPEG is required for stable RTSP on many platforms (incl. macOS).
        cap = cv2.VideoCapture(url, cv2.CAP_FFMPEG)
        if not cap.isOpened():
            log.error("RTSP: failed to open stream %s", url)
            return False

        try:
            cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        except Exception:
            pass
        try:
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
        except Exception:
            pass

        # Warm-up: first read often succeeds while follow-ups fail without draining / TCP.
        ok = False
        for attempt in range(40):
            ret, frame = cap.read()
            if ret and frame is not None:
                ok = True
                break
            time.sleep(0.05)
        if not ok:
            log.error("RTSP: no frame after warm-up reads")
            cap.release()
            return False

        self.cap = cap
        self.camera_path = url
        self._read_failures = 0
        log.info("RTSP stream opened and receiving frames")
        return True

    def _try_open_v4l2(self, path: str) -> bool:
        self._is_rtsp = False
        cap = cv2.VideoCapture(path, cv2.CAP_V4L2)
        if cap.isOpened():
            ret, frame = cap.read()
            if ret and frame is not None:
                cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
                cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
                self._apply_focus(cap)
                self.cap = cap
                self.camera_path = path
                return True
            cap.release()
        return False

    def _apply_focus(self, cap: cv2.VideoCapture) -> None:
        if self.autofocus is not None:
            ok = cap.set(cv2.CAP_PROP_AUTOFOCUS, float(self.autofocus))
            log.info("CAMERA_AUTOFOCUS=%d %s", self.autofocus, "applied" if ok else "not supported")
        if self.focus is not None:
            ok = cap.set(cv2.CAP_PROP_FOCUS, self.focus)
            log.info("CAMERA_FOCUS=%.1f %s", self.focus, "applied" if ok else "not supported")

    def _find_available(self) -> bool:
        for path in sorted(glob.glob("/dev/video*")):
            if path in self.skip_devices:
                continue
            if self._try_open_v4l2(path):
                return True
        return False

    def _read_attempts(self) -> tuple[bool, Any]:
        """Try to read one frame (with a few retries for RTSP)."""
        attempts = 12 if self._is_rtsp else 1
        ret, frame = False, None
        for _ in range(attempts):
            ret, frame = self.cap.read()
            if ret and frame is not None:
                return True, frame
            if self._is_rtsp:
                time.sleep(0.02)
        return False, None

    def read_frame(self):
        if self.cap is None:
            return False, None

        ret, frame = self._read_attempts()
        if ret and frame is not None:
            self._read_failures = 0
            return True, frame

        self._read_failures += 1

        # RTSP often drops after ~1 min idle; reopen the stream.
        if (
            self._is_rtsp
            and self.rtsp_url
            and self._read_failures >= self._rtsp_reconnect_after
        ):
            log.warning(
                "RTSP: %d failed reads — reconnecting to %s",
                self._read_failures,
                self.rtsp_url,
            )
            self.release()
            time.sleep(0.3)
            if self._try_open_rtsp(self.rtsp_url):
                ret, frame = self._read_attempts()
                if ret and frame is not None:
                    self._read_failures = 0
                    return True, frame
                log.warning("RTSP: no frame immediately after reconnect")

        if self._read_failures == 1 or self._read_failures % 60 == 0:
            log.warning(
                "Failed to read frame (%d consecutive). "
                "RTSP: try CAMERA_RTSP_TCP=0, or increase CAMERA_RTSP_RECONNECT_AFTER",
                self._read_failures,
            )
        return False, None

    def release(self):
        if self.cap is not None:
            self.cap.release()
            self.cap = None
