import pytest
from pydantic import ValidationError

from system.common.config import NavigationServerConfig
from system.common.enums import ObstacleShape
from system.common.topics import Topics
from system.navigation_server.map_provider import MapProvider


class FakeMqtt:
    def __init__(self):
        self.published = []

    def publish(self, topic, payload, qos=0):
        self.published.append((topic, payload))


def test_map_contains_typed_obstacles_from_config():
    # Arrange
    cfg = NavigationServerConfig(
        map_obstacles=[{"type": "rectangle", "x": 1, "y": 2, "width": 3, "height": 4}]
    )
    provider = MapProvider(cfg)
    provider.set_field(400, 200)

    # Act
    map_msg = provider.build_map_message()

    # Assert
    assert map_msg.obstacles[0].type is ObstacleShape.RECTANGLE
    assert (map_msg.obstacles[0].width, map_msg.obstacles[0].height) == (3.0, 4.0)


def test_invalid_obstacle_in_config_fails_at_startup():
    # Arrange
    cfg = NavigationServerConfig(map_obstacles=[{"type": "triangle"}])

    # Act / Assert
    with pytest.raises(ValidationError):
        MapProvider(cfg)


def test_map_has_calibrated_size_and_reference_markers():
    # Arrange
    provider = MapProvider(NavigationServerConfig())
    provider.set_field(400, 200)

    # Act
    map_msg = provider.build_map_message()

    # Assert
    assert (map_msg.width, map_msg.height) == (400, 200)
    assert map_msg.reference_markers == {
        "1": (0, 0),
        "2": (0, 200),
        "3": (400, 200),
        "4": (400, 0),
    }


def test_map_request_before_calibration_is_not_answered():
    # Arrange
    provider = MapProvider(NavigationServerConfig())
    mqtt = FakeMqtt()

    # Act
    provider.publish_map(mqtt)

    # Assert
    assert provider.build_map_message() is None
    assert mqtt.published == []


def test_map_is_published_after_calibration():
    # Arrange
    provider = MapProvider(NavigationServerConfig())
    mqtt = FakeMqtt()
    provider.set_field(400, 200)

    # Act
    provider.publish_map(mqtt)

    # Assert
    assert [topic for topic, _ in mqtt.published] == [Topics.MAP_RESPONSE]
