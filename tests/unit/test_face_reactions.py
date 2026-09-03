"""Поведінка обличчя має бути подієвою, а не декоративною."""

import pytest

from robi.events import FaceSeen, Source, Touch
from robi.modes.mascot import MascotMode


def test_new_face_triggers_greeting() -> None:
    mode = MascotMode((320, 240))
    mode.enter({})

    mode.handle(FaceSeen(Source.VISION, count=1, x=0.25, y=-0.1, size=0.3))

    assert mode.face._reaction_kind == "greeting"
    assert mode.face._has_face


def test_touch_gets_a_happy_reaction_and_local_gaze() -> None:
    mode = MascotMode((320, 240))

    mode.handle(Touch(Source.TOUCH, x=0.8, y=0.2))
    mode.update(0.2)

    assert mode.face._reaction_kind == "happy"
    assert mode.face._reaction_amount() > 0.0
    assert mode.face._gesture_target == pytest.approx((0.6, -0.6))


def test_idle_eye_motion_is_eased_instead_of_jumping() -> None:
    mode = MascotMode((320, 240))
    mode.face._saccade = (0.0, 0.0)
    mode.face._saccade_target = (0.12, -0.07)
    mode.face._saccade_t = 1.0

    mode.face.update(0.016)

    x, y = mode.face._saccade
    assert 0.0 < x < 0.12
    assert -0.07 < y < 0.0
