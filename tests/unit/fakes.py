"""Test fakes shared by several test modules"""

class FakeClock:
    """Controllable time source: tests move time forward explicitly."""

    def __init__(self):
        self.now = 0.0

    def __call__(self, *args, **kwds) -> float:
        return self.now

    def advance(self, seconds: float):
        self.now += seconds