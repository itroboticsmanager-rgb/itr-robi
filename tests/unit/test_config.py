"""Конфігурація: пристрій не має стартувати з непридатною."""

import pytest

from robi.config import Config, ConfigError


def test_defaults_are_valid():
    Config().validate()


def test_reads_nested_sections():
    cfg = Config.from_dict({
        "device_id": "robi-01",
        "display": {"width": 1280, "height": 720, "target_fps": 30},
        "crm": {"allowed_domains": ["example.org"]},
    })
    assert cfg.device_id == "robi-01"
    assert cfg.display.height == 720
    assert cfg.crm.allowed_domains == ("example.org",)


def test_rejects_empty_device_id():
    with pytest.raises(ConfigError):
        Config.from_dict({"device_id": ""})


def test_rejects_tiny_display():
    with pytest.raises(ConfigError):
        Config.from_dict({"display": {"width": 64, "height": 64}})


def test_rejects_absurd_fps():
    with pytest.raises(ConfigError):
        Config.from_dict({"display": {"target_fps": 0}})


def test_rejects_inverted_reconnect_window():
    with pytest.raises(ConfigError):
        Config.from_dict({"crm": {"reconnect_min_s": 30.0, "reconnect_max_s": 1.0}})


def test_rejects_voice_until_implemented():
    """Краще відмовити на старті, ніж мовчки не мати обіцяного режиму."""
    with pytest.raises(ConfigError):
        Config.from_dict({"features": {"voice": True}})


def test_missing_file_is_an_error():
    with pytest.raises(ConfigError):
        Config.load("no/such/device.toml")


def test_none_path_gives_defaults():
    assert Config.load(None).device_id == "robi-dev"
