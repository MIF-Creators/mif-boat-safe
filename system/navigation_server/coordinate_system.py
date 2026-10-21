"""Perspective-transform coordinate system based on 4 reference ArUco markers.

Transforms pixel coordinates into a logical polygon space (default 0-100 x 0-100).
Maintains per-vehicle smoothing state.
"""

import math
import cv2
import numpy as np


class CoordinateSystem:
    TARGET_COORDS = {
        1: (0, 0),
        2: (0, 100),
        3: (100, 100),
        4: (100, 0),
    }

    def __init__(
        self, map_width: int = 100, map_height: int = 100, smoothing_factor: float = 0.7
    ):
        self.map_width = map_width
        self.map_height = map_height
        self.smoothing_factor = smoothing_factor
        self.transform_matrix: np.ndarray | None = None
        self.is_calibrated = False

        # per-vehicle smoothing state: {marker_id: (prev_coords, prev_rotation)}
        self._smooth: dict[int, dict] = {}

    def calibrate(self, marker_centers: dict[int, np.ndarray]) -> bool:
        """Calibrate from reference marker pixel centres.

        ``marker_centers`` maps marker_id -> centre pixel (x, y).
        """
        if len(marker_centers) < 4:
            return False
        for mid in [1, 2, 3, 4]:
            if mid not in marker_centers:
                return False

        src = np.array([marker_centers[mid] for mid in [1, 2, 3, 4]], dtype=np.float32)
        dst = np.array(
            [self.TARGET_COORDS[mid] for mid in [1, 2, 3, 4]], dtype=np.float32
        )
        self.transform_matrix = cv2.getPerspectiveTransform(src, dst)
        self.is_calibrated = True
        return True

    def transform_point(self, pixel_point: np.ndarray, marker_id: int = 0):
        """Pixel -> polygon coords with per-vehicle smoothing.

        Returns (x, y) as floats or None.
        """
        if not self.is_calibrated:
            return None

        pt = np.array([[pixel_point[0], pixel_point[1]]], dtype=np.float32)
        transformed = cv2.perspectiveTransform(
            pt.reshape(-1, 1, 2), self.transform_matrix
        )
        coords = transformed[0][0].copy()
        coords[0] = float(np.clip(coords[0], 0, self.map_width))
        coords[1] = float(np.clip(coords[1], 0, self.map_height))

        state = self._smooth.setdefault(marker_id, {})
        prev = state.get("coords")
        if prev is not None:
            coords = self.smoothing_factor * prev + (1 - self.smoothing_factor) * coords
        state["coords"] = coords.copy()

        return (round(float(coords[0]), 2), round(float(coords[1]), 2))

    def calculate_rotation(
        self, marker_corners, marker_center_pixel: np.ndarray, marker_id: int = 0
    ) -> float | None:
        """Calculate vehicle heading in polygon space (radians, 0 = +X, CCW positive)."""
        if not self.is_calibrated:
            return None

        corners_2d = marker_corners[0].reshape(-1, 2)
        front = corners_2d[0]

        center_pt = np.array(
            [[marker_center_pixel[0], marker_center_pixel[1]]], dtype=np.float32
        )
        front_pt = np.array([[front[0], front[1]]], dtype=np.float32)

        c_t = cv2.perspectiveTransform(
            center_pt.reshape(-1, 1, 2), self.transform_matrix
        )[0][0]
        f_t = cv2.perspectiveTransform(
            front_pt.reshape(-1, 1, 2), self.transform_matrix
        )[0][0]

        dx = f_t[0] - c_t[0]
        dy = f_t[1] - c_t[1]
        rotation = math.atan2(dy, dx)

        state = self._smooth.setdefault(marker_id, {})
        prev_rot = state.get("rotation")
        if prev_rot is not None:
            diff = rotation - prev_rot
            if diff > math.pi:
                diff -= 2 * math.pi
            elif diff < -math.pi:
                diff += 2 * math.pi
            rotation = prev_rot + (1 - self.smoothing_factor) * diff
            rotation = math.atan2(math.sin(rotation), math.cos(rotation))
        state["rotation"] = rotation
        return rotation
