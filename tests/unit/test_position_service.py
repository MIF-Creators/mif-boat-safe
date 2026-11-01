import json

from system.common.messages import NeighborInfo
from system.vehicle.services.position_service import PositionService
from system.vehicle.shared_state import SharedState


class FakeMsg:
    def __init__(self, payload):
        self.payload = payload


def _position_payload(**overrides):
    fields = {
        "vehicle_id": "vehicle_0",
        "x": 1,
        "y": 2,
        "rotation": 0.5,
        "neighbors": [{"vehicle_id": "vehicle_1", "x": 3, "y": 4, "rotation": 0}],
    }
    fields.update(overrides)
    return json.dumps({k: v for k, v in fields.items() if v is not None})


def test_valid_position_updates_position_and_neighbors():
    # Arrange
    shared = SharedState()
    service = PositionService("vehicle_0", shared, mqtt_client=None)

    # Act
    service._on_position(FakeMsg(_position_payload()))

    # Assert
    pos = shared.get_position()
    assert (pos.valid, pos.x, pos.y, pos.rotation) == (True, 1.0, 2.0, 0.5)
    assert shared.get_neighbors() == [
        NeighborInfo(vehicle_id="vehicle_1", x=3, y=4, rotation=0)
    ]


def test_invalid_position_is_ignored():
    # Arrange
    shared = SharedState()
    service = PositionService("vehicle_0", shared, mqtt_client=None)

    # Act
    service._on_position(FakeMsg(_position_payload(x="far away")))

    # Assert
    assert shared.get_position().valid is False
    assert shared.get_neighbors() == []
