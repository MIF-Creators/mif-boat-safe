import pytest

from system.common.config import NavigationServerConfig

_FIELD_VARS = ("MAP_WIDTH", "MAP_HEIGHT", "REFERENCE_MARKER_SIZE_CM")


@pytest.fixture
def env_file(tmp_path, monkeypatch):
    """An empty ``.env`` and no field settings in the environment."""
    for name in _FIELD_VARS:
        monkeypatch.delenv(name, raising=False)
    path = tmp_path / ".env"
    path.write_text("")
    return path


def test_field_settings_are_unset_by_default(env_file):
    cfg = NavigationServerConfig.load(env_path=env_file)

    assert (cfg.map_width, cfg.map_height) == (None, None)
    assert cfg.reference_marker_size_cm is None


def test_field_settings_are_read(env_file, monkeypatch):
    # Arrange: 100 is a real value now, not the "not set" default
    monkeypatch.setenv("MAP_WIDTH", "100")
    monkeypatch.setenv("MAP_HEIGHT", "100")
    monkeypatch.setenv("REFERENCE_MARKER_SIZE_CM", "7.5")

    # Act
    cfg = NavigationServerConfig.load(env_path=env_file)

    # Assert
    assert (cfg.map_width, cfg.map_height) == (100, 100)
    assert cfg.reference_marker_size_cm == 7.5


def test_empty_field_settings_mean_unset(env_file, monkeypatch):
    monkeypatch.setenv("MAP_WIDTH", "")
    monkeypatch.setenv("REFERENCE_MARKER_SIZE_CM", " ")

    cfg = NavigationServerConfig.load(env_path=env_file)

    assert cfg.map_width is None
    assert cfg.reference_marker_size_cm is None
