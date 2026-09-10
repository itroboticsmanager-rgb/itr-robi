"""Межа між пристроєм і веб-інтерфейсом.

Найважливіше тут — не формат відповіді, а те, що служба не виходить за
петлю й не віддає нічого за межами своєї теки. Пристрій стоїть у холі
школи, тож ці дві властивості перевіряються прямо, а не припускаються.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request

import pytest

from robi.config import Config, ConfigError
from robi.content import Content
from robi.mascot_state import MascotState
from robi.state.coordinator import ModeName
from robi.web import LocalWebService, WebServiceError, snapshot

CONTENT = {
    "root": "root",
    "node": [
        {"id": "root", "kind": "menu", "title": "Головна", "items": ["kurs"]},
        {"id": "kurs", "kind": "card", "title": "Робототехніка", "body": "Опис", "price": "1200 грн"},
    ],
}


def _service(tmp_path=None, **kwargs) -> LocalWebService:
    content = Content.from_dict(CONTENT)
    provider = lambda: snapshot(content, MascotState.IDLE, device_id="robi-1", site="kyiv")
    return LocalWebService(provider, port=0, root=str(tmp_path) if tmp_path else "", **kwargs)


def _get(service: LocalWebService, path: str) -> tuple[int, bytes]:
    url = f"http://127.0.0.1:{service.port}{path}"
    try:
        with urllib.request.urlopen(url, timeout=5) as response:
            return response.status, response.read()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read()


def test_snapshot_carries_content_as_data_not_markup() -> None:
    content = Content.from_dict(CONTENT)
    payload = snapshot(content, MascotState.HAPPY, device_id="robi-1", site="kyiv", revision=3)
    assert payload["revision"] == 3
    assert payload["device"] == {"id": "robi-1", "site": "kyiv"}
    assert payload["mascot"]["state"] == "happy"
    assert payload["content"]["root"] == "root"
    card = next(n for n in payload["content"]["nodes"] if n["id"] == "kurs")
    assert card["title"] == "Робототехніка"
    assert card["price"] == "1200 грн"
    # Вузол лишається набором полів: рендерити його — робота клієнта.
    assert set(card) == {
        "id", "kind", "title", "items", "body", "price", "icon", "image",
        "age_min", "age_max", "duration_months", "highlights", "accent",
    }


def test_snapshot_without_content_is_still_valid() -> None:
    payload = snapshot(None, MascotState.IDLE, device_id="robi-1", site="local")
    assert payload["content"] == {"root": "", "nodes": []}


def test_service_refuses_any_address_beyond_the_loopback() -> None:
    provider = lambda: {}
    for host in ("0.0.0.0", "192.168.1.10", "localhost", ""):
        with pytest.raises(WebServiceError):
            LocalWebService(provider, host=host, port=0)


def test_config_refuses_a_non_loopback_host() -> None:
    raw = {"device_id": "robi-1", "web": {"enabled": True, "host": "0.0.0.0"}}
    with pytest.raises(ConfigError):
        Config.from_dict(raw)


def test_config_keeps_the_service_off_by_default() -> None:
    cfg = Config.from_dict({"device_id": "robi-1"})
    assert cfg.web.enabled is False
    assert cfg.web.host == "127.0.0.1"


def test_service_serves_the_snapshot() -> None:
    with _service() as service:
        status, body = _get(service, "/api/snapshot")
    assert status == 200
    payload = json.loads(body)
    assert payload["mascot"]["state"] == "idle"
    assert payload["device"]["id"] == "robi-1"


def test_service_serves_files_from_its_own_directory(tmp_path) -> None:
    (tmp_path / "index.html").write_text("<p>Робі</p>", encoding="utf-8")
    with _service(tmp_path) as service:
        root_status, root_body = _get(service, "/")
        named_status, _ = _get(service, "/index.html")
    assert root_status == 200 and "Робі" in root_body.decode("utf-8")
    assert named_status == 200


def test_service_does_not_serve_anything_above_its_directory(tmp_path) -> None:
    secret = tmp_path.parent / "secret.json"
    secret.write_text('{"token": "..."}', encoding="utf-8")
    root = tmp_path / "web"
    root.mkdir()
    (root / "index.html").write_text("ok", encoding="utf-8")
    with _service(root) as service:
        for path in ("/../secret.json", "/..%2fsecret.json", "/web/../../secret.json"):
            status, _ = _get(service, path)
            assert status == 404, path


def test_service_refuses_a_missing_directory(tmp_path) -> None:
    provider = lambda: {}
    with pytest.raises(WebServiceError):
        LocalWebService(provider, port=0, root=str(tmp_path / "absent"))


def test_step_one_reads_and_never_writes() -> None:
    with _service() as service:
        url = f"http://127.0.0.1:{service.port}/api/snapshot"
        request = urllib.request.Request(url, data=b"{}", method="POST")
        with pytest.raises(urllib.error.HTTPError) as exc:
            urllib.request.urlopen(request, timeout=5)
    assert exc.value.code == 405


def test_service_stops_cleanly_and_can_restart() -> None:
    service = _service()
    service.start()
    port = service.port
    assert _get(service, "/api/snapshot")[0] == 200
    service.stop()
    service.stop()  # повторна зупинка не має падати
    with pytest.raises(urllib.error.URLError):
        urllib.request.urlopen(f"http://127.0.0.1:{port}/api/snapshot", timeout=2)


def _app(tmp_path, **web):
    """Кіоск у headless-режимі з увімкненою локальною службою."""
    import os

    os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
    os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
    from robi.bootstrap import App
    from robi.state.coordinator import ModeName  # noqa: F401

    content = tmp_path / "content.toml"
    content.write_text(
        '\n'.join(
            [
                'root = "root"',
                '[[node]]',
                'id = "root"',
                'kind = "menu"',
                'title = "Головна"',
                'items = ["kurs"]',
                '[[node]]',
                'id = "kurs"',
                'kind = "card"',
                'title = "Робототехніка"',
                'body = "Опис"',
            ]
        ),
        encoding="utf-8",
    )
    cfg = Config.from_dict(
        {
            "device_id": "robi-1",
            "site": "kyiv",
            "crm": {"enabled": False},
            "features": {"camera": False},
            "content": {"path": str(content)},
            "web": {"enabled": True, "port": 0, **web},
        }
    )
    return App(cfg, headless=True)


def test_boot_starts_the_service_and_shutdown_stops_it(tmp_path) -> None:
    app = _app(tmp_path)
    app.boot()
    try:
        assert app._web is not None
        status, body = _get(app._web, "/api/snapshot")
        assert status == 200
        payload = json.loads(body)
        # Знімок бере справжній контент і справжній стан маскота кіоску.
        assert payload["device"] == {"id": "robi-1", "site": "kyiv"}
        assert payload["mascot"]["state"] == app.modes[ModeName.MASCOT].face.state.value
        assert {n["id"] for n in payload["content"]["nodes"]} == {"root", "kurs"}
    finally:
        app.shutdown()
    assert app._web is None


def test_service_stays_off_unless_it_is_switched_on(tmp_path) -> None:
    app = _app(tmp_path)
    app.config.web.enabled = False
    app.boot()
    try:
        assert app._web is None
    finally:
        app.shutdown()


def test_a_busy_port_degrades_the_kiosk_instead_of_killing_it(tmp_path) -> None:
    from robi.state.machine import SystemState

    blocker = _service()
    blocker.start()
    try:
        app = _app(tmp_path, port=blocker.port)
        app.boot()
        try:
            # Кіоск на рецепції корисніший без веб-частини, ніж темний екран.
            assert app._web is None
            assert app.machine.state is SystemState.DEGRADED
        finally:
            app.shutdown()
    finally:
        blocker.stop()


def test_web_input_uses_device_priority_and_never_renews_qr(tmp_path):
    from robi.events import Command, CommandKind, CommandStatus
    app = _app(tmp_path)
    app.boot()
    try:
        result = app._web_action({"action": "menu", "node": "kurs"})
        assert result["ok"]
        token = result["snapshot"]["display"]["token"]
        app.step(.03)
        assert app._current is ModeName.INFO
        assert app.modes[ModeName.INFO].current.id == "kurs"
        cmd = Command(CommandKind.SHOW_QR, "blocked-qr", {"value": "https://example.org/pay"})
        assert app.accept_command(cmd).status is CommandStatus.REJECTED
        assert app._web_action({"action": "activity", "token": token})["ok"]
        assert app._web_snapshot()["display"]["token"] == token
        assert app._web_action({"action": "close", "token": token})["ok"]
        app.step(.03)
        qr = Command(CommandKind.SHOW_QR, "qr-1", {"value": "https://example.org/pay", "duration_ms": 2000})
        assert app.accept_command(qr).status is CommandStatus.ACCEPTED
        app.step(.03)
        display = app._web_snapshot()["display"]
        assert display["mode"] == "qr" and len(display["qr"]) >= 21
        assert "https://" not in json.dumps(display)
        assert not app._web_action({"action": "activity", "token": display["token"]})["ok"]
        assert not app._web_action({"action": "close", "token": token})["ok"]
        # Even a stalled main loop cannot serve an expired payment code.
        app._web_bridge.clock = lambda: app.coordinator.active.expires_at + 1
        expired = app._web_snapshot()["display"]
        assert expired["mode"] == "home" and expired["qr"] is None
    finally:
        app.shutdown()


def test_same_mode_crm_command_enters_new_node_and_rejects_unknown_id(tmp_path):
    from robi.events import Command, CommandKind, CommandStatus
    app = _app(tmp_path)
    app.boot()
    try:
        for command_id, node in [("first", "kurs"), ("second", "root")]:
            cmd = Command(CommandKind.SET_MODE, command_id, {"mode": "info", "node": node})
            assert app.accept_command(cmd).status is CommandStatus.ACCEPTED
            app.step(.03)
            assert app.modes[ModeName.INFO].current.id == node
        unknown = Command(CommandKind.SET_MODE, "bad", {"mode": "info", "node": "missing"})
        assert app.accept_command(unknown).reason == "unknown_node"
        bypass = Command(CommandKind.SET_MODE, "bad-qr", {"mode": "qr", "value": "javascript:alert(1)"})
        assert app.accept_command(bypass).status is CommandStatus.REJECTED
    finally:
        app.shutdown()


def test_removed_workshop_action_cannot_expand_mascot(tmp_path):
    app = _app(tmp_path)
    app.boot()
    try:
        result = app._web_action({"action": "workshop"})
        assert result == {"ok": False, "reason": "unknown_action"}
        app.step(.03)
        assert not app.modes[ModeName.MASCOT].interactive
        assert app._web_snapshot()["display"]["mode"] == "home"
    finally:
        app.shutdown()


def test_service_rejects_cross_origin_inputs_and_foreign_hosts():
    service = LocalWebService(lambda: {}, port=0, action=lambda body: {"ok": True})
    service.start()
    try:
        url = f"http://127.0.0.1:{service.port}/api/action"
        for headers in [
            {"Origin": "https://unrelated.example", "Content-Type": "application/json"},
            {"Host": "attacker.example", "Content-Type": "application/json"},
            {"Content-Type": "text/plain"},
        ]:
            req = urllib.request.Request(url, data=b'{"action":"workshop"}', headers=headers)
            with pytest.raises(urllib.error.HTTPError) as error:
                urllib.request.urlopen(req, timeout=3)
            assert error.value.code == 403
        req = urllib.request.Request(url, data=b'{"action":"workshop"}', headers={"Content-Type": "application/json"})
        assert json.load(urllib.request.urlopen(req, timeout=3))["ok"]
    finally:
        service.stop()


def test_http_action_is_applied_on_main_loop(tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    import time
    app = _app(tmp_path)
    app.boot()
    try:
        def request():
            url = f"http://127.0.0.1:{app._web.port}/api/action"
            req = urllib.request.Request(url, data=b'{"action":"menu","node":"kurs"}', headers={"Content-Type": "application/json"})
            return json.load(urllib.request.urlopen(req, timeout=4))
        with ThreadPoolExecutor() as executor:
            future = executor.submit(request)
            stop = time.monotonic() + 3
            while not future.done() and time.monotonic() < stop:
                app.step(.03)
                time.sleep(.005)
            result = future.result(timeout=1)
        assert result["ok"] and result["snapshot"]["display"]["mode"] == "info"
    finally:
        app.shutdown()


def test_public_media_uses_cache_without_exposing_paths_or_secrets(tmp_path):
    from robi.banners import Banner, BannerStore
    app = _app(tmp_path)
    app.boot()
    try:
        directory = tmp_path / "banners"
        directory.mkdir()
        (directory / "banners.json").write_text("private index")
        app._banners = BannerStore(directory)
        app.modes[ModeName.MASCOT].banners = [Banner(7, "Новий курс", image="https://crm.example/7.png")]
        app._banners.image_path(app.modes[ModeName.MASCOT].banners[0]).write_bytes(b"image-bytes")
        app._publish_web()
        assert app._web_snapshot()["banners"][0]["image"] == "/media/banner/7"
        assert _get(app._web, "/media/banner/7") == (200, b"image-bytes")
        assert _get(app._web, "/media/banner/../banners.json")[0] == 404
        assert _get(app._web, "/media/content/../device-secret.txt")[0] == 404
    finally:
        app.shutdown()
