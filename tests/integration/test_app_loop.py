"""Інтеграція: справжній застосунок у headless-режимі.

Тут перевіряється те, чого не видно в юніт-тестах окремих класів —
що камера вмикається й гасне разом зі зміною режиму, і що посилання з
недозволеного домену не доходить до рендеру.
"""

import pytest

from robi.config import Config
from robi.events import Command, CommandKind, CommandStatus
from robi.state.coordinator import ModeName


class FakeClock:
    """Керований час. Уся логіка TTL зав'язана на нього, тож інакше
    тести залежали б від реального монотонного годинника."""

    def __init__(self, start: float = 100.0) -> None:
        self.t = start

    def __call__(self) -> float:
        return self.t

    def advance(self, seconds: float) -> None:
        self.t += seconds


@pytest.fixture
def clock():
    return FakeClock()


@pytest.fixture
def app(clock):
    from robi.bootstrap import App

    cfg = Config.from_dict({
        "device_id": "robi-test",
        "display": {"width": 320, "height": 240, "target_fps": 60},
        "crm": {"enabled": False, "allowed_domains": ["example.org"]},
    })
    instance = App(cfg, headless=True, clock=clock)
    instance.boot()
    yield instance
    instance.shutdown()


def test_boots_to_ready(app):
    from robi.state.machine import SystemState

    assert app.machine.state is SystemState.READY


def test_camera_starts_in_mascot(app):
    """mascot — єдиний режим, що вмикає захоплення (D-033)."""
    assert app.coordinator.mode is ModeName.MASCOT
    assert app.vision.capturing


def test_camera_stops_in_qr_and_resumes_after(app, clock):
    """Під час показу QR пристрою нема на що дивитися — захоплення гасне."""
    app.coordinator.apply(
        Command(CommandKind.SHOW_QR, "c1", {"value": "https://example.org/x", "duration_ms": 500})
    )
    app.step(0.016)
    assert app.coordinator.mode is ModeName.QR
    assert not app.vision.capturing

    clock.advance(1.0)
    app.step(0.016)
    assert app.coordinator.mode is ModeName.MASCOT
    assert app.vision.capturing


def test_camera_disabled_by_feature_flag():
    from robi.bootstrap import App

    cfg = Config.from_dict({
        "display": {"width": 320, "height": 240},
        "crm": {"enabled": False},
        "features": {"camera": False},
    })
    instance = App(cfg, headless=True)
    try:
        instance.boot()
        instance.step(0.016)
        assert not instance.vision.capturing
    finally:
        instance.shutdown()


def test_shutdown_clears_outputs(app):
    """Сценарій не переживає застосунок: підсвітка гасне при вимкненні."""
    app.outputs.apply((255, 0, 0), None)
    assert app.outputs.rgb is not None
    app.shutdown()
    assert app.outputs.rgb is None


def test_many_frames_do_not_crash(app):
    for _ in range(120):
        app.step(0.016)
    assert app.metrics.snapshot().frames == 120


def test_qr_payload_reaches_the_mode(app):
    app.coordinator.apply(
        Command(
            CommandKind.SHOW_QR,
            "c2",
            {"value": "https://example.org/pay", "title": "Оплата", "duration_ms": 5000},
        )
    )
    app.step(0.016)
    assert app.modes[ModeName.QR]._value == "https://example.org/pay"


def test_qr_value_is_cleared_on_exit(app, clock):
    """Платіжні посилання одноразові: кешованого показу бути не повинно (D-038)."""
    app.coordinator.apply(
        Command(CommandKind.SHOW_QR, "c3", {"value": "https://example.org/pay", "duration_ms": 500})
    )
    app.step(0.016)
    clock.advance(1.0)
    app.step(0.016)
    assert app.modes[ModeName.QR]._value == ""


@pytest.mark.parametrize(
    "url",
    [
        "https://evil.example.net/pay",
        "http://example.org/insecure",
        "https://user:pass@example.org/x",
        "https://example.org.attacker.net/pay",
    ],
)
def test_disallowed_url_never_reaches_the_screen(app, url):
    """Головна перевірка D-038 на рівні застосунку, а не самої політики."""
    result = app.accept_command(
        Command(CommandKind.SHOW_QR, f"bad-{url}", {"value": url, "duration_ms": 5000})
    )
    assert result.status is CommandStatus.REJECTED

    app.step(0.016)
    # Режим не змінився, отже посилання не дійшло навіть до координатора.
    assert app.coordinator.mode is ModeName.MASCOT
    assert app.modes[ModeName.QR]._value == ""


def test_allowed_url_is_accepted(app):
    result = app.accept_command(
        Command(CommandKind.SHOW_QR, "good", {"value": "https://example.org/ok", "duration_ms": 5000})
    )
    assert result.status is CommandStatus.ACCEPTED
    app.step(0.016)
    assert app.coordinator.mode is ModeName.QR
