"""Налаштування стійки з CRM (D-068).

Охороняються три обіцянки. Перша — пристрій, якому CRM нічого не казала,
не чіпає яскравість і гучність. Друга — битий набір не заміняє робочий.
Третя — розклад перемикає «день» і «ніч» саме тоді, коли написано.
"""

import io
import json
import urllib.error
import urllib.request
from datetime import datetime

import pytest

from robi.integration.crm import CrmClient
from robi.settings import KioskSettings, SettingsError, SettingsStore

URL = "https://crm.example.org/api/device/settings"
#: Понеділок, 2026-11-16.
MON_NOON = datetime(2026, 11, 16, 12, 0)
MON_NIGHT = datetime(2026, 11, 16, 23, 30)
SUN_NOON = datetime(2026, 11, 22, 12, 0)

WEEK = {day: ["09:00", "20:00"] for day in ("mon", "tue", "wed", "thu", "fri", "sat")} | {"sun": None}


def test_defaults_touch_nothing():
    effective = KioskSettings().effective(MON_NIGHT)
    assert effective.brightness is None and effective.volume is None
    assert effective.open_now and not effective.sleeping and effective.camera_allowed


def test_managed_values_follow_the_schedule():
    settings = KioskSettings.from_dict({
        "manage_display": True, "brightness": 90, "night_brightness": 20,
        "manage_volume": True, "volume": 60, "night_volume": 5,
        "schedule_enabled": True, "schedule": WEEK, "after_hours": "dim",
    })
    day, night, sunday = (settings.effective(t) for t in (MON_NOON, MON_NIGHT, SUN_NOON))
    assert (day.brightness, day.volume, day.open_now) == (90, 60, True)
    assert (night.brightness, night.volume, night.open_now) == (20, 5, False)
    assert not sunday.open_now and not sunday.sleeping


def test_after_hours_modes():
    base = {"manage_display": True, "brightness": 90, "night_brightness": 20,
            "schedule_enabled": True, "schedule": WEEK}
    same = KioskSettings.from_dict(base | {"after_hours": "same"}).effective(MON_NIGHT)
    sleep = KioskSettings.from_dict(base | {"after_hours": "sleep"}).effective(MON_NIGHT)
    assert same.brightness == 90 and not same.sleeping
    assert sleep.brightness == 20 and sleep.sleeping


def test_closing_after_midnight():
    settings = KioskSettings.from_dict({"schedule_enabled": True,
                                        "schedule": {day: ["10:00", "01:00"] for day in WEEK}})
    assert settings.is_open(datetime(2026, 11, 16, 0, 30))
    assert not settings.is_open(datetime(2026, 11, 16, 3, 0))
    assert settings.is_open(MON_NIGHT)


def test_camera_follows_open_hours_unless_released():
    hours = {"schedule_enabled": True, "schedule": WEEK}
    assert not KioskSettings.from_dict(hours).effective(MON_NIGHT).camera_allowed
    assert KioskSettings.from_dict(hours | {"camera_open_hours_only": False}).effective(MON_NIGHT).camera_allowed


def test_unknown_fields_are_ignored_for_newer_crm():
    assert KioskSettings.from_dict({"volume": 40, "future_knob": "x"}).volume == 40


@pytest.mark.parametrize("raw, reason", [
    ({"volume": 101}, "volume"),
    ({"brightness": 1}, "brightness"),
    ({"volume": True}, "volume"),
    ({"idle_timeout_s": "45"}, "idle_timeout_s"),
    ({"show_wifi": 1}, "show_wifi"),
    ({"after_hours": "off"}, "after_hours"),
    ({"schedule": {"mon": ["9:00", "20:00"]}}, "schedule.mon"),
    ({"schedule": {"mon": ["10:00", "10:00"]}}, "schedule.mon"),
    ({"schedule": []}, "schedule"),
    ("not-a-dict", "об'єктом"),
])
def test_broken_values_reject_the_set(raw, reason):
    with pytest.raises(SettingsError, match=reason):
        KioskSettings.from_dict(raw)


# --- кеш і забирання з CRM ---------------------------------------------------


class _Response(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()


@pytest.fixture
def crm(monkeypatch):
    state = {"body": None, "headers": None}

    def urlopen(request, timeout=None):
        state["headers"] = dict(request.header_items())
        body = state["body"]
        if isinstance(body, Exception):
            raise body
        return _Response(json.dumps(body).encode("utf-8"))

    monkeypatch.setattr(urllib.request, "urlopen", urlopen)
    return state


def test_refresh_caches_and_reports_what_is_applied(tmp_path, crm):
    crm["body"] = {"revision": 3, "settings": {"manage_volume": True, "volume": 30}}
    store = SettingsStore(tmp_path)
    fresh, reason = store.refresh(URL, "secret", applied=2, report="brightness=off,volume=ok")
    assert reason == "" and fresh.revision == 3 and fresh.settings.volume == 30
    assert crm["headers"]["X-robi-applied-revision"] == "2"
    assert crm["headers"]["X-robi-controls"] == "brightness=off,volume=ok"
    assert store.load().settings.volume == 30


def test_broken_set_keeps_the_previous_one(tmp_path, crm):
    store = SettingsStore(tmp_path)
    crm["body"] = {"revision": 1, "settings": {"volume": 30}}
    store.refresh(URL, "secret")
    crm["body"] = {"revision": 2, "settings": {"volume": 300}}
    fresh, reason = store.refresh(URL, "secret")
    assert fresh is None and reason.startswith("invalid")
    assert store.load().revision == 1


def test_offline_keeps_the_cache(tmp_path, crm):
    store = SettingsStore(tmp_path)
    crm["body"] = {"revision": 1, "settings": {}}
    store.refresh(URL, "secret")
    crm["body"] = urllib.error.URLError("down")
    assert store.refresh(URL, "secret")[1].startswith("net_")
    assert store.load().revision == 1


def test_signal_wakes_settings_and_is_not_a_command():
    seen = []
    client = CrmClient("ws://x", "robi-1", on_signal=seen.append)
    assert client._parse(json.dumps({"event": "settings.changed", "data": {}})) is None
    assert seen == ["settings.changed"]


# --- застосування на пристрої ------------------------------------------------


def _app(tmp_path):
    from tests.unit.test_web_service import _app as make_app  # noqa: PLC0415 — спільний помічник
    return make_app(tmp_path)


def test_app_applies_only_changes_and_reports_them(tmp_path):
    app = _app(tmp_path)
    try:
        app._settings_set = app._settings_set.__class__(5, KioskSettings.from_dict({
            "manage_display": True, "brightness": 70, "night_brightness": 20,
            "schedule_enabled": True, "schedule": WEEK,
        }))
        app._apply_settings(now=MON_NOON)
        app._apply_settings(now=MON_NOON)
        app._apply_settings(now=MON_NIGHT)
        assert app.system.brightness == [70, 20]
        assert app.system.volume == []
        assert app._settings_report == "brightness=ok,volume=off"
        app._apply_settings(now=MON_NIGHT, force=True)
        assert app.system.brightness == [70, 20, 20]
    finally:
        app.shutdown()


def test_failed_control_is_reported_and_retried(tmp_path):
    app = _app(tmp_path)
    try:
        app.system.ok = False
        app._settings_set = app._settings_set.__class__(1, KioskSettings.from_dict({"manage_volume": True, "volume": 40}))
        app._apply_settings(now=MON_NOON)
        app._apply_settings(now=MON_NOON)
        assert app.system.volume == [40, 40]
        assert app._settings_report == "brightness=off,volume=failed"
    finally:
        app.shutdown()


def test_web_snapshot_carries_kiosk_settings(tmp_path):
    app = _app(tmp_path)
    app.boot()
    try:
        assert app._web_snapshot()["idle_timeout_s"] == app.config.content.timeout_s
        app._settings_set = app._settings_set.__class__(2, KioskSettings.from_dict({
            "idle_timeout_s": 90, "show_wifi": False, "video_volume": 40,
            "schedule_enabled": True, "schedule": WEEK, "after_hours": "sleep",
        }))
        app._apply_settings(now=MON_NIGHT)
        app._publish_web()
        snapshot = app._web_snapshot()
        assert snapshot["idle_timeout_s"] == 90
        assert snapshot["settings"] | {} == {
            "idle_timeout_s": 90, "banner_interval_s": 14, "reduced_motion": False,
            "video_sound": True, "video_volume": 40, "show_wifi": False, "show_scanner": True,
            "open_now": False, "sleeping": True,
        }
        assert "volume" not in snapshot["settings"]
    finally:
        app.shutdown()


def test_config_requires_a_cache_for_crm_settings():
    from robi.config import Config, ConfigError

    with pytest.raises(ConfigError, match="cache_dir"):
        Config.from_dict({"settings": {"url": URL}})
    with pytest.raises(ConfigError, match="30"):
        Config.from_dict({"settings": {"url": URL, "cache_dir": "c", "refresh_s": 5}})
    assert Config.from_dict({"settings": {"url": URL, "cache_dir": "c"}}).settings.refresh_s == 300.0


def test_example_config_loads():
    from pathlib import Path

    from robi.config import Config

    example = Path(__file__).resolve().parents[2] / "app" / "config" / "device.example.toml"
    assert Config.load(example).settings.url.endswith("/api/device/settings")
