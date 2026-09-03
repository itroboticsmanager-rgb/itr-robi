"""Наскрізний шлях контент-меню (D-048).

Перевіряється те, чого не видно в юніт-тестах: дотик відкриває меню,
меню тримається, поки з ним працюють, і зникає само, коли людина пішла.
Останнє — головне: залишений на екрані чужий екран є і незручністю, і
початком того, чого `D-049` не дозволяє для анкети.
"""

import pytest

from robi.config import Config
from robi.events import Command, CommandKind, CommandStatus, Source, Touch
from robi.state.coordinator import ModeName

CONTENT = {
    "root": "root",
    "node": [
        {"id": "root", "kind": "menu", "title": "Меню", "items": ["a"]},
        {"id": "a", "kind": "card", "title": "Курс", "body": "опис"},
    ],
}


class FakeClock:
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
def app(clock, tmp_path, monkeypatch):
    from robi.bootstrap import App
    from robi.content import Content

    cfg = Config.from_dict({
        "device_id": "robi-test",
        "display": {"width": 320, "height": 240, "target_fps": 60},
        "crm": {"enabled": False},
        "content": {"path": "ignored", "timeout_s": 30.0},
    })
    monkeypatch.setattr(Content, "load", staticmethod(lambda _p: Content.from_dict(CONTENT)))
    instance = App(cfg, headless=True, clock=clock)
    instance.boot()
    yield instance
    instance.shutdown()


def tap(app, x=0.5, y=0.5):
    app._route_touches([Touch(Source.TOUCH, x=x, y=y)])


def test_menu_is_available_when_content_is_configured(app):
    assert ModeName.INFO in app.modes
    assert ModeName.INFO not in app.coordinator.unsupported


def test_touch_opens_the_menu(app):
    assert app.coordinator.mode is ModeName.MASCOT
    tap(app)
    app.step(0.05)
    assert app.coordinator.mode is ModeName.INFO


def test_opening_touch_does_not_also_press_an_item(app):
    """Координати були з екрана маскота — влучання тут було б випадковим."""
    rects = app.modes[ModeName.INFO].screen.item_rects(1)
    w, h = app.modes[ModeName.INFO].screen.size
    app._route_touches([Touch(Source.TOUCH, x=rects[0].centerx / w, y=rects[0].centery / h)])
    app.step(0.05)
    assert app.modes[ModeName.INFO].current.id == "root"


def test_menu_returns_to_mascot_on_timeout(app, clock):
    tap(app)
    app.step(0.05)
    assert app.coordinator.mode is ModeName.INFO

    clock.advance(31.0)
    app.step(0.05)
    assert app.coordinator.mode is ModeName.MASCOT


def test_touching_keeps_the_menu_alive(app, clock):
    tap(app)
    app.step(0.05)
    for _ in range(4):
        clock.advance(20.0)
        tap(app)
        app.step(0.05)
        assert app.coordinator.mode is ModeName.INFO


def test_navigation_is_cleared_after_returning_to_mascot(app, clock):
    """Наступний відвідувач не має побачити, де копався попередній."""
    tap(app)
    app.step(0.05)
    app.modes[ModeName.INFO].open("a")
    assert app.modes[ModeName.INFO].current.id == "a"

    clock.advance(31.0)
    app.step(0.05)
    assert app.coordinator.mode is ModeName.MASCOT
    assert app.modes[ModeName.INFO].current.id == "root"


def test_back_out_of_root_returns_to_mascot(app):
    tap(app)
    app.step(0.05)
    app.modes[ModeName.INFO].back()
    app.step(0.05)
    assert app.coordinator.mode is ModeName.MASCOT


def test_camera_is_off_while_the_menu_is_open(app):
    """У меню обличчя немає, тож і захопленню там нема чого працювати."""
    tap(app)
    app.step(0.05)
    assert not app.vision.capturing


def test_crm_can_open_the_menu_when_content_exists(app, clock):
    result = app.accept_command(
        Command(CommandKind.SET_MODE, "c1", {"mode": "info"})
    )
    assert result.status is CommandStatus.ACCEPTED


def test_menu_is_rejected_without_content(clock):
    """Без контенту `info` має відхилятися чесно, а не відкривати порожньо."""
    from robi.bootstrap import App

    cfg = Config.from_dict({
        "device_id": "robi-test",
        "display": {"width": 320, "height": 240},
        "crm": {"enabled": False},
    })
    instance = App(cfg, headless=True, clock=clock)
    instance.boot()
    try:
        assert ModeName.INFO not in instance.modes
        result = instance.accept_command(
            Command(CommandKind.SET_MODE, "c2", {"mode": "info"})
        )
        assert result.status is CommandStatus.REJECTED
        assert result.reason == "unsupported_mode"
    finally:
        instance.shutdown()


def test_broken_content_disables_the_menu_but_not_the_device(clock, monkeypatch):
    """Маскот на стійці цінніший за меню: помилка в контенті не валить пристрій."""
    from robi.bootstrap import App
    from robi.content import Content, ContentError

    def boom(_path):
        raise ContentError("посилання в нікуди")

    monkeypatch.setattr(Content, "load", staticmethod(boom))
    cfg = Config.from_dict({
        "device_id": "robi-test",
        "display": {"width": 320, "height": 240},
        "crm": {"enabled": False},
        "content": {"path": "broken.toml"},
    })
    instance = App(cfg, headless=True, clock=clock)
    instance.boot()
    try:
        assert ModeName.INFO not in instance.modes
        instance.step(0.05)
        assert instance.coordinator.mode is ModeName.MASCOT
    finally:
        instance.shutdown()
