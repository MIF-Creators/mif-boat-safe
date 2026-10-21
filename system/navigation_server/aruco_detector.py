"""ArUco marker detection – supports multiple mobile markers."""

import cv2
import numpy as np


class ArucoDetector:
    """Detects reference (static) and mobile ArUco markers in a frame."""

    def __init__(
        self,
        reference_ids: list[int] | None = None,
        mobile_ids: list[int] | None = None,
    ):
        self.reference_ids = set(reference_ids or [1, 2, 3, 4])
        self.mobile_ids = set(mobile_ids or [0])

        aruco_dict = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_6X6_250)
        params = cv2.aruco.DetectorParameters()
        params.adaptiveThreshWinSizeMin = 3
        params.adaptiveThreshWinSizeMax = 23
        params.adaptiveThreshWinSizeStep = 10
        params.minMarkerPerimeterRate = 0.03
        params.maxMarkerPerimeterRate = 4.0
        params.polygonalApproxAccuracyRate = 0.03
        params.minCornerDistanceRate = 0.05
        self.detector = cv2.aruco.ArucoDetector(aruco_dict, params)

    def detect(self, gray: np.ndarray):
        """Run detection on a grayscale frame.

        Returns (corners, ids, rejected).
        """
        return self.detector.detectMarkers(gray)

    @staticmethod
    def marker_center(corners) -> np.ndarray:
        return np.mean(corners[0].reshape(-1, 2), axis=0).astype(np.float32)

    def filter_reference_markers(self, corners, ids) -> dict | None:
        """Return {marker_id: center_pixel} for all reference markers, or None."""
        if ids is None:
            return None
        result: dict[int, np.ndarray] = {}
        for i, mid in enumerate(ids.flatten()):
            if int(mid) in self.reference_ids:
                result[int(mid)] = self.marker_center(corners[i])
        return result if len(result) == len(self.reference_ids) else None

    def get_mobile_markers(self, corners, ids) -> dict:
        """Return {marker_id: (corners, center)} for every detected mobile marker."""
        if ids is None:
            return {}
        result: dict[int, tuple] = {}
        for i, mid in enumerate(ids.flatten()):
            if int(mid) in self.mobile_ids:
                result[int(mid)] = (corners[i], self.marker_center(corners[i]))
        return result
