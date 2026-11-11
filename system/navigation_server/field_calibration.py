"""Field calibration from the shape of the reference ArUco markers.

The 4 reference markers lie at the corners of a rectangular field, flat on
the floor, and are squares of the same known size. Their centres give a
perspective transform only up to the field size; the shape of the markers
gives the size itself:

1. ``H0`` maps the marker centres 1, 2, 3, 4 to (0,0), (0,1), (1,1), (1,0).
2. All marker corners are mapped by ``H0``. On the floor a point of this unit
   square is at ``(W*x, H*y)``.
3. For each marker take two adjacent sides ``u1``, ``u2`` (each averaged
   with its opposite side). On the floor they are equal and perpendicular,
   which is linear in ``q = (W/H)**2``::

       q * (u1x**2 - u2x**2) = u2y**2 - u1y**2
       q * (u1x * u2x)       = -u1y * u2y

   ``q`` is solved by least squares over all markers and frames, so markers
   at 0 or 45 degrees (one equation degenerate) still contribute.
4. The mean marker side in units of ``W`` and the real marker size give ``W``
   and ``H`` in centimetres.

The field size is the distance between the marker centres.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field

import cv2
import numpy as np

REFERENCE_IDS = (1, 2, 3, 4)
UNIT_SQUARE = {1: (0, 0), 2: (0, 1), 3: (1, 1), 4: (1, 0)}

DEFAULT_FRAMES = 30
UNITLESS_WIDTH = 100
SPREAD_WARN_PCT = 5.0
MIN_MARKER_PX = 20.0


class CalibrationError(ValueError):
    """The marker shapes do not give a usable field size."""


@dataclass
class FieldCalibration:
    width: int  # map units: cm, or unitless (source == "unitless")
    height: int
    aspect_ratio: float  # measured width / height
    # Measured size in cm; None without REFERENCE_MARKER_SIZE_CM.
    measured_size_cm: tuple[float, float] | None
    # Max disagreement between per-marker estimates (aspect ratio, scale), %.
    spread_pct: float
    marker_size_px: float  # mean side of a reference marker in the image
    centers: dict[int, np.ndarray]  # mean pixel centre of each reference marker
    source: str  # "measured", "config" or "unitless"
    frames: int
    warnings: list[str] = field(default_factory=list)


def _apply(matrix: np.ndarray, points: np.ndarray) -> np.ndarray:
    pts = np.asarray(points, dtype=np.float64).reshape(-1, 1, 2)
    return cv2.perspectiveTransform(pts, matrix).reshape(-1, 2)


def _spread_pct(values: list[float]) -> float:
    return (max(values) - min(values)) / float(np.mean(values)) * 100


def _side_vectors(corners: np.ndarray) -> np.ndarray:
    """Sides p1-p0, p2-p1, p3-p2, p0-p3 of a quadrilateral."""
    return np.roll(corners, -1, axis=0) - corners


def _solve_q(pairs: list[tuple[np.ndarray, np.ndarray]]) -> float:
    """Least-squares ``q = (W/H)**2`` from (u1, u2) side pairs."""
    num = 0.0
    den = 0.0
    for u1, u2 in pairs:
        equations = (
            (u1[0] ** 2 - u2[0] ** 2, u2[1] ** 2 - u1[1] ** 2),
            (u1[0] * u2[0], -u1[1] * u2[1]),
        )
        for a, b in equations:
            num += a * b
            den += a * a
    if den <= 0:
        raise CalibrationError("marker sides give no equations for the aspect ratio")
    return num / den


def calibrate_field(
    frames: list[dict[int, np.ndarray]],
    marker_size_cm: float | None = None,
    map_width: int | None = None,
    map_height: int | None = None,
) -> FieldCalibration:
    """Field size and reference centres from reference marker corners.

    ``frames`` is a list of {marker_id: 4x2 pixel corners} with all 4
    reference markers in every frame.
    """
    if not frames:
        raise CalibrationError("no frames")

    corners = {
        mid: np.array(
            [np.asarray(f[mid], dtype=np.float64).reshape(4, 2) for f in frames]
        )
        for mid in REFERENCE_IDS
    }
    centers = {mid: c.mean(axis=(0, 1)) for mid, c in corners.items()}
    h0 = cv2.getPerspectiveTransform(
        np.float32([centers[mid] for mid in REFERENCE_IDS]),
        np.float32([UNIT_SQUARE[mid] for mid in REFERENCE_IDS]),
    ).astype(np.float64)

    pairs: dict[int, list] = {mid: [] for mid in REFERENCE_IDS}
    sides: dict[int, list] = {mid: [] for mid in REFERENCE_IDS}
    pixel_sides: list[float] = []
    for mid in REFERENCE_IDS:
        for frame_corners in corners[mid]:
            s = _side_vectors(_apply(h0, frame_corners))
            pairs[mid].append(((s[0] - s[2]) / 2, (s[1] - s[3]) / 2))
            sides[mid].extend(s)
            pixel_sides.extend(np.linalg.norm(_side_vectors(frame_corners), axis=1))

    q = _solve_q([p for mid in REFERENCE_IDS for p in pairs[mid]])
    if q <= 0:
        raise CalibrationError(f"negative aspect ratio estimate (q={q:.3g})")
    aspect = math.sqrt(q)

    # Marker side in units of the field width: a unit-square point (x, y)
    # is (x, y / aspect) * W on the floor.
    def side_in_widths(vectors) -> float:
        v = np.asarray(vectors)
        return float(np.mean(np.hypot(v[:, 0], v[:, 1] / aspect)))

    per_marker_side = [side_in_widths(sides[mid]) for mid in REFERENCE_IDS]
    per_marker_aspect = [
        math.sqrt(max(_solve_q(pairs[mid]), 0.0)) for mid in REFERENCE_IDS
    ]
    spread = max(_spread_pct(per_marker_aspect), _spread_pct(per_marker_side))
    marker_px = float(np.mean(pixel_sides))
    mean_side = float(np.mean(per_marker_side))

    warnings: list[str] = []
    measured = None
    if marker_size_cm:
        measured_w = marker_size_cm / mean_side
        measured = (measured_w, measured_w / aspect)

    if (map_width is None) != (map_height is None):
        warnings.append(
            "Only one of MAP_WIDTH / MAP_HEIGHT is set: ignored, set both or neither"
        )
    if map_width is not None and map_height is not None:
        width, height, source = map_width, map_height, "config"
    elif measured is not None:
        width, height = round(measured[0]), round(measured[1])
        source = "measured"
    else:
        width = UNITLESS_WIDTH
        height = round(UNITLESS_WIDTH / aspect)
        source = "unitless"
        warnings.append(
            "REFERENCE_MARKER_SIZE_CM is not set: map is unitless "
            f"(width {UNITLESS_WIDTH}, height from the aspect ratio)"
        )

    if spread > SPREAD_WARN_PCT:
        warnings.append(
            f"Reference markers disagree by {spread:.1f}% (> {SPREAD_WARN_PCT:g}%): "
            "the field is probably not a rectangle, or the markers differ in size"
        )
    if marker_px < MIN_MARKER_PX:
        warnings.append(
            f"Reference markers are only {marker_px:.1f} px "
            f"(< {MIN_MARKER_PX:g} px): the size estimate is unreliable"
        )

    return FieldCalibration(
        width=max(int(width), 1),
        height=max(int(height), 1),
        aspect_ratio=aspect,
        measured_size_cm=measured,
        spread_pct=spread,
        marker_size_px=marker_px,
        centers={mid: c.astype(np.float32) for mid, c in centers.items()},
        source=source,
        frames=len(frames),
        warnings=warnings,
    )


class FieldCalibrator:
    """Collects frames with all reference markers, then calibrates once."""

    def __init__(
        self,
        marker_size_cm: float | None = None,
        map_width: int | None = None,
        map_height: int | None = None,
        frames_required: int = DEFAULT_FRAMES,
    ):
        self._marker_size_cm = marker_size_cm
        self._map_width = map_width
        self._map_height = map_height
        self.frames_required = frames_required
        self._frames: list[dict[int, np.ndarray]] = []

    @property
    def frames_collected(self) -> int:
        return len(self._frames)

    def add_frame(self, ref_corners: dict[int, np.ndarray]) -> FieldCalibration | None:
        """Add one frame; returns the calibration when enough frames are in.

        Raises ``CalibrationError`` if the collected frames are unusable; the
        frames are dropped then, so collection starts over.
        """
        self._frames.append({mid: ref_corners[mid] for mid in REFERENCE_IDS})
        if len(self._frames) < self.frames_required:
            return None
        frames, self._frames = self._frames, []
        return calibrate_field(
            frames, self._marker_size_cm, self._map_width, self._map_height
        )


def log_calibration(cal: FieldCalibration, log: logging.Logger) -> None:
    unit = "" if cal.source == "unitless" else " cm"
    log.info(
        "Field calibrated from %d frames: %d x %d%s (%s)",
        cal.frames,
        cal.width,
        cal.height,
        unit,
        cal.source,
    )
    if cal.measured_size_cm is not None:
        log.info(
            "Measured field: %.1f x %.1f cm (between reference marker centres)",
            *cal.measured_size_cm,
        )
    log.info(
        "Aspect ratio W/H %.3f, spread between markers %.1f%%, "
        "reference marker size %.1f px",
        cal.aspect_ratio,
        cal.spread_pct,
        cal.marker_size_px,
    )
    for warning in cal.warnings:
        log.warning("Field calibration: %s", warning)
