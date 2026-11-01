import pytest
from pydantic import ValidationError

from system.common.config import NavigationServerConfig
from system.common.enums import ObstacleShape
from system.navigation_server.map_provider import MapProvider


def test_map_contains_typed_obstacles_from_config():
    # Arrange
    cfg = NavigationServerConfig(
        map_obstacles=[{"type": "rectangle", "x": 1, "y": 2, "width": 3, "height": 4}]
    )

    # Act
    map_msg = MapProvider(cfg).build_map_message()

    # Assert
    assert map_msg.obstacles[0].type is ObstacleShape.RECTANGLE
    assert (map_msg.obstacles[0].width, map_msg.obstacles[0].height) == (3.0, 4.0)


def test_invalid_obstacle_in_config_fails_at_startup():
    # Arrange
    cfg = NavigationServerConfig(map_obstacles=[{"type": "triangle"}])

    # Act / Assert
    with pytest.raises(ValidationError):
        MapProvider(cfg)
