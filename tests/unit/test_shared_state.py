import threading

from system.vehicle.shared_state import SharedState


def test_position_roundtrip_returns_copy():
    shared = SharedState()
    shared.update_position(10.5, 20.25, 1.57)

    pos = shared.get_position()
    assert pos.valid is True
    assert (pos.x, pos.y, pos.rotation) == (10.5, 20.25, 1.57)

    pos.x = -1  # mutate returned object, source state must stay unchanged
    pos2 = shared.get_position()
    assert pos2.x == 10.5


def test_mission_lifecycle_and_current_waypoint():
    shared = SharedState()
    waypoints = [{"x": 1, "y": 2}, {"x": 3, "y": 4, "action": "stop"}]
    shared.set_mission("m-1", waypoints)

    mission = shared.get_mission()
    assert mission.mission_id == "m-1"
    assert mission.status == "executing"
    assert mission.current_waypoint_idx == 0
    assert shared.get_current_waypoint() == {"x": 1, "y": 2}

    shared.advance_waypoint()
    assert shared.get_mission().current_waypoint_idx == 1
    assert shared.get_mission().status == "executing"
    assert shared.get_current_waypoint() == {"x": 3, "y": 4, "action": "stop"}

    shared.advance_waypoint()
    assert shared.get_mission().status == "completed"
    assert shared.get_current_waypoint() is None


def test_thread_safety_smoke_for_reads_and_writes():
    shared = SharedState()
    shared.set_mission("m-thread", [{"x": 10, "y": 20}])

    def writer():
        for i in range(200):
            shared.update_position(i, i + 1, i / 10)
            shared.update_neighbors([{"vehicle_id": "v2", "x": i, "y": i, "rotation": 0.0}])

    def reader():
        for _ in range(200):
            _ = shared.get_position()
            _ = shared.get_neighbors()
            _ = shared.get_mission()
            _ = shared.get_current_waypoint()

    threads = [threading.Thread(target=writer), threading.Thread(target=reader), threading.Thread(target=reader)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    # No exceptions + state remains coherent
    assert shared.get_mission().mission_id == "m-thread"
