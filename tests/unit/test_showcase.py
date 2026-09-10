"""Вітрина: геометрія, влучання й карусель.

Найважливіше тут — намальоване й натискуване рахуються з однієї
геометрії. Розбіжність не видно на екрані розробника: вона виявляється
пальцем на стійці.
"""

import os

import pygame
import pytest

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

from robi.banners import Banner  # noqa: E402
from robi.ui.showcase import SLIDE_S, NavAction, Showcase  # noqa: E402

SIZE = (1920, 1280)


@pytest.fixture(scope="module", autouse=True)
def _pygame():
    pygame.init()
    pygame.display.set_mode((320, 240))
    yield
    pygame.quit()


@pytest.fixture
def showcase():
    return Showcase(SIZE)


def banners(n: int) -> list[Banner]:
    return [Banner(id=i, title=f"Банер {i}") for i in range(1, n + 1)]


# --- геометрія ------------------------------------------------------------


def test_three_bands_do_not_overlap(showcase):
    box = showcase.layout()
    assert box.strip.bottom <= box.carousel.top
    assert box.carousel.bottom <= box.buttons.top
    assert box.buttons.bottom <= SIZE[1]


def test_strip_is_narrow_and_carousel_takes_the_space(showcase):
    """ROBI не має займати екран, поки з ним не почали взаємодіяти."""
    box = showcase.layout()
    assert box.strip.height < SIZE[1] * 0.25
    assert box.carousel.height > box.strip.height


def test_compact_robot_uses_a_taller_cropped_portrait(showcase):
    """Вітрина кадрує один канонічний портрет, а не сплющує іншу модель."""
    face_w, face_h = showcase.face_size()
    assert face_w <= showcase.size[0]
    assert face_h > showcase.layout().strip.height
    assert face_w / face_h == pytest.approx(1.60, rel=0.02)


# --- влучання -------------------------------------------------------------


def test_strip_is_hit_only_at_the_top(showcase):
    assert showcase.hit_strip(0.5, 0.02)
    assert not showcase.hit_strip(0.5, 0.5)
    assert not showcase.hit_strip(0.5, 0.95)


def test_buttons_are_where_they_are_drawn(showcase):
    rects = showcase.button_rects(3)
    for index, rect in enumerate(rects):
        x = rect.centerx / SIZE[0]
        y = rect.centery / SIZE[1]
        assert showcase.hit_button(x, y, 3) == index


def test_gap_between_buttons_is_not_a_hit(showcase):
    a, b = showcase.button_rects(2)
    x = (a.right + b.left) / 2 / SIZE[0]
    y = a.centery / SIZE[1]
    assert showcase.hit_button(x, y, 2) is None


def test_buttons_stay_inside_the_row(showcase):
    row = showcase.layout().buttons
    for count in range(1, 11):
        for rect in showcase.button_rects(count):
            assert row.left <= rect.left and rect.right <= row.right
            assert row.top <= rect.top and rect.bottom <= row.bottom


@pytest.mark.parametrize("count, rows", [(8, [4, 4]), (9, [5, 4]), (10, [5, 5])])
def test_large_action_sets_are_balanced(showcase, count, rows):
    rects = showcase.button_rects(count)
    grouped: dict[int, int] = {}
    for rect in rects:
        grouped[rect.top] = grouped.get(rect.top, 0) + 1
    assert list(grouped.values()) == rows


def test_no_buttons_no_rects(showcase):
    assert showcase.button_rects(0) == []
    assert showcase.hit_button(0.5, 0.9, 0) is None


# --- карусель -------------------------------------------------------------


def test_carousel_advances_and_wraps(showcase):
    items = banners(3)
    assert showcase.index == 0
    for expected in (1, 2, 0):
        showcase.update(SLIDE_S + 0.1, len(items))
        assert showcase.index == expected


def test_single_banner_does_not_flip(showcase):
    """Перемикати нема на що: миготіння без причини ловить око збоку."""
    for _ in range(5):
        showcase.update(SLIDE_S + 0.1, 1)
    assert showcase.index == 0


def test_empty_showcase_is_not_an_error(showcase):
    showcase.update(SLIDE_S + 0.1, 0)
    surface = pygame.Surface(SIZE)
    face = pygame.Surface(showcase.face_size())
    showcase.draw(surface, face, [], [], lambda b: None)


def test_draws_with_banners_and_buttons(showcase):
    surface = pygame.Surface(SIZE)
    face = pygame.Surface(showcase.face_size())
    showcase.draw(surface, face, banners(2), ["Курси", "Товари"], lambda b: None)


def test_draws_all_ten_icon_actions(showcase):
    surface = pygame.Surface(SIZE)
    face = pygame.Surface(showcase.face_size())
    names = [
        "courses",
        "events",
        "clubs",
        "store",
        "gallery",
        "video",
        "payment",
        "form",
        "contacts",
        "help",
    ]
    actions = [NavAction(f"Розділ {index}", str(index), name) for index, name in enumerate(names)]
    showcase.draw(surface, face, banners(1), actions, lambda b: None)


def test_missing_image_does_not_break_the_slide(showcase):
    """Банер без картинки має показати підпис, а не порожній екран."""
    surface = pygame.Surface(SIZE)
    face = pygame.Surface(showcase.face_size())
    showcase.draw(surface, face, banners(1), [], lambda b: None)
