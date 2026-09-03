"""Стани маскота — спільний словник із CRM.

Цінність цих тестів не в тому, що код не падає, а в тому, що словник не
розійдеться з рештою продуктів школи. Той самий персонаж живе в трьох
місцях, і розбіжність тут коштує перекладача між системами.
"""

import os

import pygame
import pytest

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

from robi.mascot_state import (  # noqa: E402
    EYE_SHAPES,
    LOOKS,
    MascotState,
    look_for,
    parse,
)

#: Ключі з docs/mascot/mascot-states.md у CRM. Якщо там додасться стан,
#: цей список має оновитися свідомо, а не мовчки розійтися.
CRM_STATES = [
    "idle", "happy", "success", "error", "warning", "loading",
    "empty", "pointing", "achievement", "thinking", "sad", "sleeping",
]


def test_vocabulary_matches_the_crm_guide():
    assert [s.value for s in MascotState] == CRM_STATES


def test_every_state_has_a_look():
    """Стан без вигляду означав би, що CRM може попросити те, чого немає."""
    for state in MascotState:
        assert state in LOOKS, state


def test_looks_use_known_eye_shapes():
    for state, look in LOOKS.items():
        assert look.eye in EYE_SHAPES, (state, look.eye)


def test_only_idle_follows_the_person():
    """Інакше емоція боролася б із камерою за напрямок очей."""
    following = [s for s, look in LOOKS.items() if look.follows_face]
    assert following == [MascotState.IDLE]


def test_alarming_states_do_not_expire_on_their_own():
    """Помилка, яка зникла сама, лише спантеличить людину біля стійки."""
    assert look_for(MascotState.ERROR).hold_s is not None  # error таки згасає
    for state in (MascotState.LOADING, MascotState.SLEEPING, MascotState.THINKING):
        assert look_for(state).hold_s is None, state


def test_gaze_bias_stays_in_range():
    for state, look in LOOKS.items():
        x, y = look.gaze
        assert -1.0 <= x <= 1.0 and -1.0 <= y <= 1.0, state


@pytest.mark.parametrize("value", CRM_STATES)
def test_parse_accepts_every_crm_key(value):
    assert parse(value) is MascotState(value)


@pytest.mark.parametrize("value", ["", "  ", "dancing", "HAPPY!", None])
def test_parse_rejects_unknown_without_raising(value):
    """Новіший словник у CRM не має валити пристрій на стійці."""
    assert parse(value) is None


def test_parse_is_case_insensitive():
    assert parse("HAPPY") is MascotState.HAPPY
    assert parse(" success ") is MascotState.SUCCESS


# --- рендер ---------------------------------------------------------------


@pytest.fixture(scope="module", autouse=True)
def _pygame():
    pygame.init()
    pygame.display.set_mode((320, 240))
    yield
    pygame.quit()


@pytest.fixture
def face():
    from robi.ui.face import FaceRenderer

    return FaceRenderer((320, 240))


def test_face_starts_idle(face):
    assert face.state is MascotState.IDLE


@pytest.mark.parametrize("state", list(MascotState))
def test_every_state_renders(face, state):
    """Кожен стан має малюватися, а не лише існувати в словнику."""
    surface = pygame.Surface((320, 240))
    face.set_state(state)
    face.update(0.05)
    face.draw(surface)
    assert face.state is state or look_for(state).hold_s is not None


def test_transient_state_returns_to_idle(face):
    face.set_state(MascotState.HAPPY)
    assert face.state is MascotState.HAPPY
    face.update(look_for(MascotState.HAPPY).hold_s + 0.1)
    assert face.state is MascotState.IDLE


def test_persistent_state_stays(face):
    face.set_state(MascotState.SLEEPING)
    for _ in range(20):
        face.update(1.0)
    assert face.state is MascotState.SLEEPING


def test_face_has_no_mouth_left():
    """Рота в персонажа немає — ні в гайді CRM, ні на 3D-референсах."""
    from robi.ui import face as face_module
    from robi.ui.theme import GEOMETRY, PALETTE

    source = open(face_module.__file__, encoding="utf-8").read()
    assert "_mouth_frames" not in source
    assert not hasattr(PALETTE, "mouth")
    assert not any(f.startswith("mouth") for f in GEOMETRY.__slots__)
