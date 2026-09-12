"""Кнопка «Оплатити» в меню кіоску (D-060).

Посилання приходить з CRM вузлом `qr` і показується кодом на екрані. Тут
сторожимо дві речі. Перша: посилання береться з контенту, а не з запиту
веб-інтерфейсу, і проходить той самий allowlist, що й команди CRM (D-038).
Друга: кнопку, яку allowlist не пустить, відвідувач не бачить зовсім —
дотик у нікуди біля стійки гірший за відсутню кнопку.
"""

from __future__ import annotations

import json

import pytest

from robi.config import Config
from robi.content import MAX_TITLE, Content, ContentError
from robi.state.coordinator import ModeName, Priority

PAY = "https://shorts.pb.ua/-/ee32d9fb"


def build(**pay):
    return Content.from_dict({
        "root": "root",
        "node": [
            {"id": "root", "kind": "menu", "title": "Обрати заняття", "items": ["pay"]},
            {"id": "pay", "kind": "qr", "title": "Оплатити", **pay},
        ],
    })


# --- контент ----------------------------------------------------------------


def test_qr_node_carries_its_link():
    node = build(url=PAY, body="Оплата навчання").node("pay")
    assert node.is_qr and not node.is_menu
    assert node.url == PAY


def test_qr_node_requires_an_https_link():
    for url in ("", "http://shorts.pb.ua/-/x", "javascript:alert(1)"):
        with pytest.raises(ContentError, match="https"):
            build(url=url)


def test_qr_link_keeps_the_device_length_limit():
    with pytest.raises(ContentError, match="url"):
        build(url="https://shorts.pb.ua/" + "x" * 600)


def test_qr_headline_is_short():
    with pytest.raises(ContentError, match="body"):
        build(url=PAY, body="я" * (MAX_TITLE + 1))


def test_only_qr_nodes_carry_a_link():
    with pytest.raises(ContentError, match="url"):
        Content.from_dict({
            "root": "root",
            "node": [
                {"id": "root", "kind": "menu", "title": "Головна", "items": ["a"]},
                {"id": "a", "kind": "card", "title": "Курс", "url": PAY},
            ],
        })


def test_qr_node_has_no_menu_items():
    with pytest.raises(ContentError, match="пунктів"):
        build(url=PAY, items=["root"])


# --- кіоск ------------------------------------------------------------------


def _app(tmp_path, domains):
    import os

    os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
    os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
    from robi.bootstrap import App

    content = tmp_path / "content.toml"
    content.write_text(
        "\n".join([
            'root = "root"',
            "[[node]]", 'id = "root"', 'kind = "menu"', 'title = "Обрати заняття"', 'items = ["kurs", "pay"]',
            "[[node]]", 'id = "kurs"', 'kind = "card"', 'title = "Робототехніка"',
            "[[node]]", 'id = "pay"', 'kind = "qr"', 'title = "Оплатити"', 'body = "Оплата навчання"', f'url = "{PAY}"',
        ]),
        encoding="utf-8",
    )
    cfg = Config.from_dict({
        "device_id": "robi-1",
        "site": "kyiv",
        "crm": {"enabled": False, "allowed_domains": list(domains)},
        "features": {"camera": False},
        "content": {"path": str(content)},
        "web": {"enabled": True, "port": 0},
    })
    app = App(cfg, headless=True)
    app.boot()
    app.step(.03)
    return app


def _pay_node(app) -> dict:
    return next(n for n in app._web_snapshot()["content"]["nodes"] if n["id"] == "pay")


def test_pay_button_shows_its_code(tmp_path):
    app = _app(tmp_path, ["shorts.pb.ua"])
    try:
        pay = _pay_node(app)
        assert pay["allowed"] is True
        assert "url" not in pay  # у веб іде лише відповідь allowlist, не посилання

        result = app._web_action({"action": "qr", "node": "pay"})
        assert result["ok"]
        display = result["snapshot"]["display"]
        assert display["mode"] == "qr" and len(display["qr"]) >= 21
        assert display["title"] == "Оплата навчання"
        assert "https://" not in json.dumps(display)
        assert app.coordinator.active.priority is Priority.USER

        # Строк коду фіксований, а закрити його відвідувач може сам.
        assert not app._web_action({"action": "activity", "token": display["token"]})["ok"]
        assert app._web_action({"action": "close", "token": display["token"]})["ok"]
    finally:
        app.shutdown()


def test_pay_button_with_a_foreign_domain_is_hidden_and_refused(tmp_path):
    app = _app(tmp_path, ["example.org"])
    try:
        assert _pay_node(app)["allowed"] is False
        assert app._web_action({"action": "qr", "node": "pay"}) == {"ok": False, "reason": "not_allowed"}
        assert app._web_snapshot()["display"]["mode"] == "home"
    finally:
        app.shutdown()


def test_qr_action_opens_only_qr_nodes_and_ignores_links_in_the_request(tmp_path):
    app = _app(tmp_path, ["shorts.pb.ua"])
    try:
        for node in ("kurs", "root", "missing", ""):
            assert app._web_action({"action": "qr", "node": node}) == {"ok": False, "reason": "unknown_node"}
        assert app._web_action({"action": "qr", "node": "pay", "value": "https://evil.example.net"})["ok"]
        assert app.coordinator.active.payload["value"] == PAY
    finally:
        app.shutdown()


def test_visitor_code_follows_the_device_priority_model(tmp_path):
    # Людина біля стійки важливіша за команду CRM (architecture.md): її дотик
    # замінює код від CRM, а CRM не витисне код, який людина відкрила сама.
    from robi.events import Command, CommandKind, CommandStatus

    app = _app(tmp_path, ["shorts.pb.ua", "crm.example"])
    try:
        first = Command(CommandKind.SHOW_QR, "crm-qr-1", {"value": "https://crm.example/pay", "duration_ms": 60000})
        assert app.accept_command(first).status is CommandStatus.ACCEPTED
        app.step(.03)

        assert app._web_action({"action": "qr", "node": "pay"})["ok"]
        assert app.coordinator.active.payload["value"] == PAY

        second = Command(CommandKind.SHOW_QR, "crm-qr-2", {"value": "https://crm.example/pay", "duration_ms": 60000})
        result = app.accept_command(second)
        assert result.status is CommandStatus.REJECTED and result.reason == "preempted"
    finally:
        app.shutdown()


def test_pygame_menu_hides_the_code_button(tmp_path):
    # Екрана коду з меню в pygame-версії немає: там «Оплатити» було б
    # карткою без коду, тобто глухим кутом.
    app = _app(tmp_path, ["shorts.pb.ua"])
    try:
        info = app.modes[ModeName.INFO]
        assert info._items(info.content.node("root")) == ("kurs",)
    finally:
        app.shutdown()
