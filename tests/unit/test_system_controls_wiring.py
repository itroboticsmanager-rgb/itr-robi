"""Веб-кіоск headless, але керує справжнім екраном і звуком (D-068).

19.11.2026 служба кіоску мала `App(config, headless=True)`, а headless
підставляв фальшиве керування: CRM бачила «brightness=ok,volume=ok», а
планшет лишався на 100 % яскравості.
"""

from __future__ import annotations

import os

from robi.config import Config
from robi.hardware.system import FakeSystemControls
from robi.settings import KioskSettings, SettingsSet


def _config() -> Config:
    return Config.from_dict({
        "device_id": "robi-1",
        "site": "kyiv",
        "crm": {"enabled": False},
        "features": {"camera": False},
    })


def test_explicit_controls_are_used_and_receive_targets():
    os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
    os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
    from robi.bootstrap import App

    controls = FakeSystemControls()
    app = App(_config(), headless=True, system=controls)
    assert app.system is controls

    app._settings_set = SettingsSet(2, KioskSettings(
        manage_display=True, brightness=5, manage_volume=True, volume=40,
    ))
    app._apply_settings(force=True)

    assert controls.brightness == [5]
    assert controls.volume == [40]
    assert app._settings_report == "brightness=ok,volume=ok"


def test_headless_without_controls_stays_fake():
    os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
    from robi.bootstrap import App

    assert isinstance(App(_config(), headless=True).system, FakeSystemControls)


def test_web_entry_point_passes_real_controls():
    # Захист від повернення до `App(config, headless=True)` у веб-кіоску.
    import inspect

    import robi.web.__main__ as entry

    source = inspect.getsource(entry.main)
    assert "system=make_system_controls()" in source
