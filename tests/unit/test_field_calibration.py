"""Field calibration from the shape of the reference markers.

All scenes are synthetic: a floor plane in centimetres is projected to
pixels by a perspective transform (homography), so no camera is needed.
"""

import math

import cv2
import numpy as np
import pytest

from system.common.config import NavigationServerConfig
from system.navigation_server.coordinate_system import CoordinateSystem
from system.navigation_server.field_calibration import (
    FieldCalibrator,
    calibrate_field,
)
from system.navigation_server.map_provider import MapProvider

MARKER_CM = 7.5

# Field corners (marker centres 1, 2, 3, 4) in pixels of a 1280x720 frame,
# deliberately not a rectangle: the camera looks at the floor at an angle.
VIEW_WIDE = [(40, 700), (140, 90), (1200, 60), (1260, 690)]
# A tall field seen by a camera turned by ~90 degrees.
VIEW_TALL = [(1220, 700), (60, 660), (120, 50), (1180, 80)]

# Rotation of each reference marker on the floor, degrees.
MIXED_ANGLES = {1: 10, 2: -20, 3: 35, 4: 60}


# -- Synthetic scene ---------------------------------------------------------


def rectangle(width, height):
    """Marker centres 1..4 in floor centimetres for a rectangular field."""
    return {1: (0, 0), 2: (0, height), 3: (width, height), 4: (width, 0)}


def make_view(floor_corners, pixel_quad):
    """Homography floor cm -> pixels mapping marker centres 1..4 to the quad."""
    src = np.float32([floor_corners[mid] for mid in (1, 2, 3, 4)])
    return cv2.getPerspectiveTransform(src, np.float32(pixel_quad))


def to_pixels(view, points):
    pts = np.float32(points).reshape(-1, 1, 2)
    return cv2.perspectiveTransform(pts, view).reshape(-1, 2)


def square_corners(center, size, first_corner_deg):
    """Corners of a square on the floor, in order around it.

    ``first_corner_deg`` is the direction from the centre to corner 0:
    45 gives sides along the floor axes, 90 gives a diamond.
    """
    half_diag = size / math.sqrt(2)
    return [
        (
            center[0] + half_diag * math.cos(math.radians(first_corner_deg + 90 * k)),
            center[1] + half_diag * math.sin(math.radians(first_corner_deg + 90 * k)),
        )
        for k in range(4)
    ]


def make_frames(view, floor_corners, angles, count=1, noise_px=0.0, seed=0):
    """Pixel corners of the 4 reference markers, one dict per frame."""
    rng = np.random.default_rng(seed)
    clean = {
        mid: to_pixels(
            view, square_corners(floor_corners[mid], MARKER_CM, 45 + angles[mid])
        )
        for mid in (1, 2, 3, 4)
    }
    return [
        {
            mid: corners + rng.uniform(-noise_px, noise_px, corners.shape)
            for mid, corners in clean.items()
        }
        for _ in range(count)
    ]


def scene(width, height, pixel_quad, angles=None, **kwargs):
    floor = rectangle(width, height)
    view = make_view(floor, pixel_quad)
    return view, make_frames(view, floor, angles or MIXED_ANGLES, **kwargs)


def mobile_marker(view, center, heading_deg):
    """ArUco-style corners (1, 4, 2) of a vehicle marker; corner 0 is the nose."""
    corners = to_pixels(view, square_corners(center, MARKER_CM, heading_deg))
    return corners.reshape(1, 4, 2), corners.mean(axis=0)


def coordinate_system(calibration):
    coord = CoordinateSystem(
        map_width=calibration.width,
        map_height=calibration.height,
        smoothing_factor=0.0,
    )
    assert coord.calibrate(calibration.centers)
    return coord


def assert_within(actual, expected, pct):
    assert abs(actual - expected) <= expected * pct / 100, (actual, expected)


# -- Field size --------------------------------------------------------------


@pytest.mark.parametrize(
    ("width", "height", "view"),
    [(400, 200, VIEW_WIDE), (200, 400, VIEW_TALL)],
)
def test_field_size_is_measured_from_marker_shape(width, height, view):
    # Arrange
    _, frames = scene(width, height, view)

    # Act
    cal = calibrate_field(frames, marker_size_cm=MARKER_CM)

    # Assert
    assert_within(cal.width, width, 2)
    assert_within(cal.height, height, 2)
    assert_within(cal.aspect_ratio, width / height, 2)
    assert cal.spread_pct < 1
    assert cal.source == "measured"


def test_noisy_corners_are_averaged_over_frames():
    # Arrange: +-0.3 px on every corner of ~22 px markers
    _, frames = scene(400, 200, VIEW_WIDE, count=40, noise_px=0.3, seed=1)

    # Act
    cal = calibrate_field(frames, marker_size_cm=MARKER_CM)

    # Assert
    assert_within(cal.width, 400, 3)
    assert_within(cal.height, 200, 3)


@pytest.mark.parametrize("angle", [0, 45])
def test_markers_aligned_with_axes_or_diagonal(angle):
    # Arrange: each angle makes one of the two square conditions degenerate
    angles = dict.fromkeys((1, 2, 3, 4), angle)
    _, frames = scene(400, 200, VIEW_WIDE, angles=angles)

    # Act
    cal = calibrate_field(frames, marker_size_cm=MARKER_CM)

    # Assert
    assert_within(cal.width, 400, 2)
    assert_within(cal.height, 200, 2)


def test_trapezoid_field_gives_large_spread_and_warning():
    # Arrange: markers 2 and 3 are moved inwards, the field is a trapezoid
    floor = {1: (0, 0), 2: (60, 200), 3: (340, 200), 4: (400, 0)}
    view = make_view(rectangle(400, 200), VIEW_WIDE)
    frames = make_frames(view, floor, MIXED_ANGLES)

    # Act
    cal = calibrate_field(frames, marker_size_cm=MARKER_CM)

    # Assert
    assert cal.spread_pct > 5
    assert any("not a rectangle" in w for w in cal.warnings)


def test_rectangular_field_has_no_spread_warning():
    _, frames = scene(400, 200, VIEW_WIDE)

    cal = calibrate_field(frames, marker_size_cm=MARKER_CM)

    assert not any("not a rectangle" in w for w in cal.warnings)


def test_small_markers_give_warning():
    # Arrange: the same field seen from twice as far away
    quad = [(x / 2, y / 2) for x, y in VIEW_WIDE]
    _, frames = scene(400, 200, quad)

    # Act
    cal = calibrate_field(frames, marker_size_cm=MARKER_CM)

    # Assert
    assert cal.marker_size_px < 20
    assert any("px" in w for w in cal.warnings)


def test_without_marker_size_field_is_unitless_with_measured_aspect():
    # Arrange
    _, frames = scene(400, 200, VIEW_WIDE)

    # Act
    cal = calibrate_field(frames)

    # Assert
    assert (cal.width, cal.height) == (100, 50)
    assert cal.source == "unitless"
    assert any("REFERENCE_MARKER_SIZE_CM" in w for w in cal.warnings)


def test_explicit_map_size_overrides_measurement():
    # Arrange
    _, frames = scene(400, 200, VIEW_WIDE)

    # Act
    cal = calibrate_field(
        frames, marker_size_cm=MARKER_CM, map_width=500, map_height=300
    )

    # Assert
    assert (cal.width, cal.height) == (500, 300)
    assert cal.source == "config"


def test_calibrator_finishes_after_required_frames():
    # Arrange
    _, frames = scene(400, 200, VIEW_WIDE, count=3)
    calibrator = FieldCalibrator(marker_size_cm=MARKER_CM, frames_required=3)

    # Act
    results = [calibrator.add_frame(f) for f in frames]

    # Assert
    assert results[:2] == [None, None]
    assert_within(results[2].width, 400, 2)


# -- Positions and heading in the calibrated system --------------------------


def test_coordinate_system_maps_markers_to_field_size():
    # Arrange: centres of the reference markers of a 400x200 field
    view = make_view(rectangle(400, 200), VIEW_WIDE)
    centers = dict(
        zip(
            (1, 2, 3, 4),
            to_pixels(view, list(rectangle(400, 200).values())),
            strict=True,
        )
    )
    coord = CoordinateSystem(map_width=400, map_height=200, smoothing_factor=0.0)
    coord.calibrate(centers)

    # Act
    far_corner = coord.transform_point(centers[3], marker_id=1)

    # Assert
    assert far_corner == pytest.approx((400, 200), abs=0.1)


def test_equal_floor_moves_give_equal_map_moves():
    # Arrange
    view, frames = scene(400, 200, VIEW_WIDE)
    coord = coordinate_system(calibrate_field(frames, marker_size_cm=MARKER_CM))

    def map_point(floor_xy, marker_id):
        _, center = mobile_marker(view, floor_xy, 0)
        return np.array(coord.transform_point(center, marker_id=marker_id))

    # Act
    start = map_point((200, 100), marker_id=0)
    right = map_point((230, 100), marker_id=1)
    up = map_point((200, 130), marker_id=2)

    # Assert
    step_x = np.linalg.norm(right - start)
    step_y = np.linalg.norm(up - start)
    assert_within(step_x, 30, 2)
    assert_within(step_y, 30, 2)


@pytest.mark.parametrize("heading", [0, 30, 90, -135])
def test_heading_matches_marker_rotation_on_floor(heading):
    # Arrange
    view, frames = scene(400, 200, VIEW_WIDE)
    coord = coordinate_system(calibrate_field(frames, marker_size_cm=MARKER_CM))
    corners, center = mobile_marker(view, (120, 80), heading)

    # Act
    rotation = coord.calculate_rotation(corners, center, marker_id=0)

    # Assert
    diff = math.remainder(rotation - math.radians(heading), 2 * math.pi)
    assert abs(math.degrees(diff)) < 1


# -- Map ---------------------------------------------------------------------


def test_map_reference_markers_match_transform_targets():
    # Arrange
    _, frames = scene(400, 200, VIEW_WIDE)
    cal = calibrate_field(frames, marker_size_cm=MARKER_CM)
    coord = coordinate_system(cal)
    provider = MapProvider(NavigationServerConfig())
    provider.set_field(cal.width, cal.height)

    # Act
    map_msg = provider.build_map_message()

    # Assert
    assert (map_msg.width, map_msg.height) == (cal.width, cal.height)
    for mid in (1, 2, 3, 4):
        on_map = coord.transform_point(cal.centers[mid], marker_id=100 + mid)
        assert on_map == pytest.approx(map_msg.reference_markers[str(mid)], abs=0.01)
