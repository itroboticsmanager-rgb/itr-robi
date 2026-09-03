"""Розрізнення дотику й протягування.

До цього будь-яке торкання екрана рахувалося натисканням, тож
протягування пальцем відкривало меню. Тепер намір визначається при
відпусканні — і саме тому натискання саме по собі нічого не робить.
"""

import pygame
import pytest

from robi.bootstrap import SWIPE_MIN, TAP_SLOP
from robi.config import Config
from robi.events import Swipe, Touch


@pytest.fixture
def app():
    from robi.bootstrap import App

    cfg = Config.from_dict({
        "device_id": "robi-test",
        "display": {"width": 400, "height": 400, "target_fps": 60},
        "crm": {"enabled": False},
    })
    instance = App(cfg, headless=True)
    instance.boot()
    yield instance
    instance.shutdown()


def gesture(app, start, end):
    """Проводить палець від start до end у пікселях і віддає події."""
    pygame.event.clear()
    pygame.event.post(pygame.event.Event(pygame.MOUSEBUTTONDOWN, {"pos": start, "button": 1}))
    pygame.event.post(pygame.event.Event(pygame.MOUSEBUTTONUP, {"pos": end, "button": 1}))
    return app._pump_window()


def test_press_alone_is_not_a_tap(app):
    """Натискання без відпускання ще не намір: з нього може вирости свайп."""
    pygame.event.clear()
    pygame.event.post(pygame.event.Event(pygame.MOUSEBUTTONDOWN, {"pos": (200, 200), "button": 1}))
    assert app._pump_window() == []


def test_tap_in_place(app):
    events = gesture(app, (200, 200), (200, 200))
    assert len(events) == 1
    assert isinstance(events[0], Touch)


def test_small_wobble_is_still_a_tap(app):
    """Палець ніколи не стоїть ідеально нерухомо."""
    shift = int(TAP_SLOP * 400 * 0.5)
    events = gesture(app, (200, 200), (200 + shift, 200 + shift))
    assert len(events) == 1
    assert isinstance(events[0], Touch)


def test_downward_drag_is_a_swipe_not_a_tap(app):
    """Головне: протягування більше не відкриває меню."""
    distance = int(SWIPE_MIN * 400 * 1.5)
    events = gesture(app, (200, 100), (200, 100 + distance))
    assert len(events) == 1
    assert isinstance(events[0], Swipe)
    assert events[0].direction == "down"
    assert not any(isinstance(e, Touch) for e in events)


def test_upward_drag_is_reported_as_up(app):
    distance = int(SWIPE_MIN * 400 * 1.5)
    events = gesture(app, (200, 300), (200, 300 - distance))
    assert isinstance(events[0], Swipe)
    assert events[0].direction == "up"


def test_horizontal_drag_is_not_a_downward_swipe(app):
    """Горизонтальний рух не має розгортати ROBI: він для каруселі."""
    distance = int(SWIPE_MIN * 400 * 1.5)
    events = gesture(app, (100, 200), (100 + distance, 200))
    assert not any(isinstance(e, Swipe) for e in events)
    assert not any(isinstance(e, Touch) for e in events)


def test_smudge_is_neither(app):
    """Рух завеликий для дотику й закороткий для свайпу — намір невідомий."""
    shift = int(TAP_SLOP * 400 * 2)
    events = gesture(app, (200, 200), (200 + shift, 200 + shift))
    assert events == []


def test_swipe_carries_the_starting_point(app):
    """Початок жесту знадобиться вітрині: тягнути можна саме за смужку ROBI."""
    distance = int(SWIPE_MIN * 400 * 1.5)
    events = gesture(app, (120, 40), (120, 40 + distance))
    assert events[0].x == pytest.approx(120 / 400)
    assert events[0].y == pytest.approx(40 / 400)
