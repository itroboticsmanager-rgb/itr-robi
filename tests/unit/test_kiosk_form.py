"""Анкета, яку CRM відкриває просто на планшеті (D-065).

Сторожимо: адресу перевіряє той самий allowlist, що й для QR (D-038); у
знімку вона є лише поки анкета на екрані; людина подовжує строк дотиками,
але не далі стелі; «Скасувати» закриває анкету, хоч її відкрила CRM; без
дотиків анкета зникає сама (D-049).
"""

from __future__ import annotations

import json

from robi.config import Config
from robi.events import Command, CommandKind, CommandStatus
from robi.state.coordinator import FORM_IDLE_S, FORM_MAX_S, Coordinator, ModeName, Priority

URL = "https://crm.example/enroll/abcdefgh12345678?kiosk=1"


def form_command(cid="form-1", url=URL, **payload):
    return Command(CommandKind.OPEN_FORM, cid, {"kind": "enrollment", "url": url, "title": "Анкета нового учня", **payload})


# --- координатор ------------------------------------------------------------


def test_form_opens_with_an_idle_window():
    c = Coordinator()
    result = c.apply(form_command(duration_ms=180000, max_ms=1200000), at=100.0)
    assert result.status is CommandStatus.ACCEPTED
    assert c.mode is ModeName.FORM
    assert c.active.expires_at == 280.0
    assert c.active.payload["max_until"] == 1300.0


def test_form_without_url_is_rejected():
    c = Coordinator()
    assert c.apply(form_command(url=""), at=1.0).reason == "empty_payload"
    assert c.mode is ModeName.MASCOT


def test_activity_extends_but_never_past_the_cap():
    c = Coordinator()
    c.apply(form_command(duration_ms=180000, max_ms=600000), at=0.0)
    assert c.form_activity(at=100.0)
    assert c.active.expires_at == 280.0
    assert c.form_activity(at=270.0)
    assert c.form_activity(at=440.0)
    assert c.active.expires_at == 600.0  # стеля, а не 620


def test_crm_cannot_ask_for_more_than_the_device_allows():
    c = Coordinator()
    c.apply(form_command(duration_ms=10_000_000, max_ms=99_000_000), at=0.0)
    assert c.active.expires_at == FORM_IDLE_S
    assert c.active.payload["max_until"] == FORM_MAX_S


def test_untouched_form_disappears_by_itself():
    c = Coordinator()
    c.apply(form_command(duration_ms=180000), at=0.0)
    assert c.tick(at=181.0)
    assert c.mode is ModeName.MASCOT
    assert not c.form_activity(at=182.0)


def test_set_mode_cannot_open_a_form_without_its_command():
    c = Coordinator()
    result = c.apply(Command(CommandKind.SET_MODE, "s1", {"mode": "form", "duration_ms": 5000}), at=0.0)
    assert result.reason == "unsupported_mode"


def test_cancel_from_crm_closes_the_form():
    c = Coordinator()
    c.apply(form_command(cid="f1"), at=0.0)
    c.apply(Command(CommandKind.CANCEL, "x1", {"target_command_id": "f1"}), at=5.0)
    assert c.mode is ModeName.MASCOT


# --- кіоск ------------------------------------------------------------------


def _app(tmp_path, domains, web=True):
    import os

    os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
    os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
    from robi.bootstrap import App

    cfg = Config.from_dict({
        "device_id": "robi-1",
        "site": "kyiv",
        "crm": {"enabled": False, "allowed_domains": list(domains)},
        "features": {"camera": False},
        "web": {"enabled": web, "port": 0},
    })
    app = App(cfg, headless=True)
    app.boot()
    app.step(.03)
    return app


def test_form_reaches_the_web_only_while_on_screen(tmp_path):
    app = _app(tmp_path, ["crm.example"])
    try:
        assert "url" not in app._web_snapshot()["display"] or not app._web_snapshot()["display"].get("url")
        assert app.accept_command(form_command()).status is CommandStatus.ACCEPTED
        app.step(.03)
        display = app._web_snapshot()["display"]
        assert display["mode"] == "form" and display["kind"] == "form"
        assert display["url"] == URL
        assert display["title"] == "Анкета нового учня"

        # Людина натиснула «Скасувати»: анкету відкрила CRM, але закриває вона.
        assert app._web_action({"action": "close", "token": display["token"]})["ok"]
        after = app._web_snapshot()["display"]
        assert after["mode"] == "home"
        assert URL not in json.dumps(app._web_snapshot())
    finally:
        app.shutdown()


def test_touch_extends_the_form(tmp_path):
    app = _app(tmp_path, ["crm.example"])
    try:
        app.accept_command(form_command(duration_ms=60000))
        app.step(.03)
        token = app._web_snapshot()["display"]["token"]
        before = app.coordinator.active.expires_at
        result = app._web_action({"action": "activity", "token": token})
        assert result["ok"]
        assert app.coordinator.active.expires_at > before
        assert app.coordinator.active.priority is Priority.CRM
        assert app._web_action({"action": "activity", "token": "stale"}) == {"ok": False, "reason": "stale"}
    finally:
        app.shutdown()


def test_form_with_a_foreign_domain_is_refused(tmp_path):
    app = _app(tmp_path, ["crm.example"])
    try:
        result = app.accept_command(form_command(url="https://evil.example.net/enroll/x"))
        assert result.status is CommandStatus.REJECTED and result.reason == "domain_not_allowed"
        assert app._web_snapshot()["display"]["mode"] == "home"
    finally:
        app.shutdown()


def test_device_without_web_kiosk_refuses_the_form(tmp_path):
    app = _app(tmp_path, ["crm.example"], web=False)
    try:
        assert app.accept_command(form_command()).reason == "unsupported_mode"
    finally:
        app.shutdown()


def test_expired_form_leaves_no_url_in_the_snapshot(tmp_path):
    app = _app(tmp_path, ["crm.example"])
    try:
        app.accept_command(form_command(duration_ms=60000))
        app.step(.03)
        # Головний цикл завис і не встиг повернути «спокій»: міст знімка
        # однаково не віддасть адресу анкети після її строку.
        app.coordinator.active.expires_at = app.clock_fn() - 1
        app._web_bridge.publish(app._web_bridge.state[0], app.coordinator.active)
        display = app._web_bridge.read()["display"]
        assert display["mode"] == "home" and display["url"] == ""
    finally:
        app.shutdown()
