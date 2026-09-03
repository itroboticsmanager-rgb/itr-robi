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


def test_camera_is_off_while_robi_just_stands_there(app):
    """Спокій без камери — головна зміна поведінки пристрою.

    Раніше `mascot` тримав захоплення ввімкненим завжди, тобто ROBI
    дивився в порожній хол цілодобово. Тепер камера чекає, поки людина
    сама відкриє інтерактивний режим.
    """
    assert app.coordinator.mode is ModeName.MASCOT
    assert not app.vision.capturing


def test_camera_starts_only_when_robi_is_pulled_open(app):
    """І гасне, коли режим згортається."""
    mode = app.modes[ModeName.MASCOT]
    mode.expand()
    app.step(0.016)
    assert app.vision.capturing

    mode.collapse()
    app.step(0.016)
    assert not app.vision.capturing


def test_qr_interrupts_the_interactive_mode(app, clock):
    """Під час показу QR пристрою нема на що дивитися — захоплення гасне.

    А повернення в `mascot` не відновлює інтерактив: наступна людина не
    має заставати камеру ввімкненою від попередньої.
    """
    app.modes[ModeName.MASCOT].expand()
    app.step(0.016)
    assert app.vision.capturing

    app.coordinator.apply(
        Command(CommandKind.SHOW_QR, "c1", {"value": "https://example.org/x", "duration_ms": 500})
    )
    app.step(0.016)
    assert app.coordinator.mode is ModeName.QR
    assert not app.vision.capturing

    clock.advance(1.0)
    app.step(0.016)
    assert app.coordinator.mode is ModeName.MASCOT
    assert not app.vision.capturing


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


def test_bare_tap_does_not_preempt_crm(app):
    """Дотик у режимі mascot не має глушити CRM.

    Регресія з живого прогону: кожен клік захоплював USER-пріоритет на
    20 секунд, хоча на екрані нічого не змінювалося. Зовні це виглядало
    як «ROBI перестав показувати QR» без видимої причини, а на рецепції
    те саме зробив би випадковий доторк до екрана.
    """
    import pygame

    from robi.state.coordinator import Priority

    pygame.event.post(
        pygame.event.Event(pygame.MOUSEBUTTONDOWN, {"pos": (10, 10), "button": 1})
    )
    app.step(0.016)
    assert app.coordinator.active.priority is Priority.BACKGROUND

    result = app.accept_command(
        Command(CommandKind.SHOW_QR, "after-tap", {"value": "https://example.org/x",
                                                   "duration_ms": 5000})
    )
    assert result.status is CommandStatus.ACCEPTED


def test_tap_still_reaches_the_mode(app):
    """Дотик не зникає: обличчя реагує на нього підсвіткою.

    Намір визначається при **відпусканні**: натискання саме по собі ще не
    дотик, бо з нього може вирости свайп.
    """
    import pygame

    pygame.event.post(
        pygame.event.Event(pygame.MOUSEBUTTONDOWN, {"pos": (10, 10), "button": 1})
    )
    pygame.event.post(
        pygame.event.Event(pygame.MOUSEBUTTONUP, {"pos": (10, 10), "button": 1})
    )
    app.step(0.016)
    assert app.outputs.rgb is not None


def test_long_stall_is_clamped_for_logic(app):
    """Заблокований цикл не має телепортувати анімацію.

    Живий прогін дав кадр на 4.5 с — на Windows перетягування вікна
    блокує event pump. На пристрої те саме зробить throttling або
    гикавка носія. Логіка йде обмеженим кроком, метрика бачить правду.
    """
    from robi.bootstrap import MAX_STEP_S
    from robi.events import FaceSeen, Source

    # Без цього fake vision підкидав би власні події й перезаписував ціль.
    # Глушити адаптер напряму не можна: `_sync_camera` узгоджує стан раз на
    # секунду й увімкнув би його назад. Вимикаємо так, як розуміє застосунок.
    app.config.features.camera = False
    app._sync_camera()

    def gaze_after(step_dt: float) -> float:
        mode = app.modes[ModeName.MASCOT]
        mode.face._gaze = (0.0, 0.0)
        mode._since_face = 0.0
        mode.handle(FaceSeen(Source.VISION, count=1, x=1.0, y=0.0, size=0.3))
        app.step(step_dt)
        return mode.face._gaze[0]

    # Затримка в 4.5 с має дати рівно те саме, що й обмежений крок.
    stalled = gaze_after(4.5)
    clamped = gaze_after(MAX_STEP_S)
    assert stalled == pytest.approx(clamped)

    # Без обмеження погляд стрибнув би майже в ціль за один кадр.
    assert stalled < 0.9


def test_metrics_still_show_the_real_stall(app):
    """Затримку не можна ховати: обмеження стосується логіки, не вимірювання."""
    app.step(4.5)
    assert app.metrics.snapshot().ms_worst >= 4500.0
