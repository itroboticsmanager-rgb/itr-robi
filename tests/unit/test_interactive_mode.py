"""Інтерактивний режим маскота.

Головне, що тут охороняється, — не жест, а обіцянка: **камера працює
лише тоді, коли людина сама її відкрила.** Це не оптимізація, а те, що
дозволяє пояснити батькам роботу пристрою однією фразою.
"""

import os

import pygame
import pytest

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

from robi.events import Source, Swipe, Touch  # noqa: E402
from robi.mascot_state import MascotState  # noqa: E402
from robi.modes.mascot import INTERACTIVE_TIMEOUT_S, MascotMode  # noqa: E402


@pytest.fixture(scope="module", autouse=True)
def _pygame():
    pygame.init()
    pygame.display.set_mode((320, 240))
    yield
    pygame.quit()


@pytest.fixture
def mode():
    return MascotMode((320, 240))


def swipe(direction: str) -> Swipe:
    return Swipe(Source.TOUCH, direction=direction, x=0.5, y=0.1, distance=0.2)


# --- камера ---------------------------------------------------------------


def test_camera_is_off_until_asked(mode):
    """Спокій без камери: ROBI не дивиться в порожній хол."""
    assert mode.wants_camera() is False


def test_swipe_down_opens_the_camera(mode):
    mode.handle(swipe("down"))
    assert mode.interactive
    assert mode.wants_camera() is True


def test_swipe_up_closes_it_again(mode):
    """Вихід має бути таким самим жестом, а не лише очікуванням таймера."""
    mode.handle(swipe("down"))
    mode.handle(swipe("up"))
    assert not mode.interactive
    assert mode.wants_camera() is False


def test_swipe_up_in_idle_does_nothing(mode):
    mode.handle(swipe("up"))
    assert not mode.interactive


def test_second_swipe_down_does_not_reset_the_state(mode):
    mode.handle(swipe("down"))
    mode.update(10.0)
    mode.handle(swipe("down"))
    assert mode.interactive


# --- повернення в спокій --------------------------------------------------


def test_it_closes_itself_when_nobody_plays(mode):
    mode.handle(swipe("down"))
    mode.update(INTERACTIVE_TIMEOUT_S + 1)
    assert not mode.interactive
    assert mode.wants_camera() is False


def test_touch_keeps_it_open(mode):
    mode.handle(swipe("down"))
    for _ in range(4):
        mode.update(INTERACTIVE_TIMEOUT_S * 0.6)
        mode.handle(Touch(Source.TOUCH, x=0.5, y=0.5))
    assert mode.interactive


def test_being_seen_does_not_keep_it_open(mode):
    """Інакше камера трималася б увімкненою тому, що бачить людину.

    Це замкнене коло, і воно є рівно тим постійним спостереженням, від
    якого цей режим і рятує.
    """
    from robi.events import FaceSeen

    mode.handle(swipe("down"))
    for _ in range(4):
        mode.update(INTERACTIVE_TIMEOUT_S * 0.6)
        mode.handle(FaceSeen(Source.VISION, count=1, x=0.0, y=0.0, size=0.3))
    assert not mode.interactive


def test_entering_the_mode_starts_from_rest(mode):
    """Наступна людина не має застати камеру ввімкненою від попередньої."""
    mode.handle(swipe("down"))
    mode.enter({})
    assert not mode.interactive
    assert mode.wants_camera() is False


# --- підказка про жест ----------------------------------------------------


def test_handle_is_shown_in_idle_and_hidden_when_open(mode):
    assert mode.face.show_handle is True
    mode.handle(swipe("down"))
    assert mode.face.show_handle is False
    mode.handle(swipe("up"))
    assert mode.face.show_handle is True


def test_face_draws_in_both_states(mode):
    surface = pygame.Surface((320, 240))
    mode.face.update(0.05)
    mode.face.draw(surface)
    mode.handle(swipe("down"))
    mode.face.update(0.05)
    mode.face.draw(surface)


def test_opening_greets_the_person(mode):
    """Розгортання — момент зустрічі, і ROBI має на нього відреагувати."""
    mode.handle(swipe("down"))
    assert mode.face.state is MascotState.HAPPY
