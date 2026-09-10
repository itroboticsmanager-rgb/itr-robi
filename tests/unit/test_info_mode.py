"""Навігація контент-меню (D-048).

Окремо стережеться інваріант, який легко зламати непомітно: те, що
намальовано, і те, що натискається, рахується з однієї геометрії. Розбіжність
тут не видно на екрані розробника — вона виявляється пальцем на стійці.
"""

import os

import pygame
import pytest

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

from robi.content import Content  # noqa: E402
from robi.modes.info import InfoMode  # noqa: E402


@pytest.fixture(scope="module", autouse=True)
def _pygame():
    pygame.init()
    yield
    pygame.quit()


@pytest.fixture
def content():
    return Content.from_dict({
        "root": "root",
        "node": [
            {"id": "root", "kind": "menu", "title": "Меню", "items": ["courses", "goods"]},
            {"id": "courses", "kind": "menu", "title": "Курси", "items": ["c1"]},
            {"id": "c1", "kind": "card", "title": "3D", "body": "опис", "price": "100 грн"},
            {"id": "goods", "kind": "card", "title": "Товари", "body": "щось"},
        ],
    })


@pytest.fixture
def mode(content):
    return InfoMode((640, 480), content)


def test_starts_at_root(mode):
    assert mode.current.id == "root"
    assert mode.depth == 1
    assert not mode.wants_release()


def test_navigates_down_and_back(mode):
    mode.open("courses")
    assert mode.current.id == "courses"
    mode.open("c1")
    assert mode.current.id == "c1"
    mode.back()
    assert mode.current.id == "courses"
    mode.back()
    assert mode.current.id == "root"


def test_back_at_root_asks_to_leave(mode):
    """Крок назад із кореня — вихід, а не глухий кут."""
    assert not mode.wants_release()
    mode.back()
    assert mode.wants_release()
    assert mode.current.id == "root"


def test_exit_clears_navigation(mode):
    """Наступний відвідувач починає з початку, а не там, де копався попередній."""
    mode.open("courses")
    mode.open("c1")
    mode.exit()
    assert mode.current.id == "root"
    assert mode.depth == 1
    assert not mode.wants_release()


def test_unknown_node_is_ignored(mode):
    mode.open("не існує")
    assert mode.current.id == "root"


def test_enter_may_open_a_branch(mode):
    mode.enter({"node": "courses"})
    assert mode.current.id == "courses"
    assert mode.depth == 2


def test_enter_ignores_a_bogus_branch(mode):
    """id з команди CRM — це вхідні дані, а не адреса, якій можна вірити."""
    mode.enter({"node": "../secret"})
    assert mode.current.id == "root"


def test_menu_never_wants_the_camera(mode):
    """Обличчя на екрані немає, дивитися нема кому й нема навіщо."""
    assert mode.wants_camera() is False


# --- намальоване = натискуване -------------------------------------------


def test_touch_opens_the_item_that_was_drawn(mode):
    from robi.events import Source, Touch

    rects = mode.screen.item_rects(2)
    w, h = mode.screen.size
    centre = rects[1].center
    mode.handle(Touch(Source.TOUCH, x=centre[0] / w, y=centre[1] / h))
    assert mode.current.id == "goods"


def test_touch_on_back_goes_back(mode):
    from robi.events import Source, Touch

    mode.open("courses")
    back = mode.screen.back_rect()
    w, h = mode.screen.size
    mode.handle(Touch(Source.TOUCH, x=back.centerx / w, y=back.centery / h))
    assert mode.current.id == "root"


def test_touch_between_items_does_nothing(mode):
    """Проміжок між пунктами не має відкривати сусідній: це промах, а не вибір."""
    from robi.events import Source, Touch

    rects = mode.screen.item_rects(2)
    gap_x = (rects[0].right + rects[1].left) // 2
    w, h = mode.screen.size
    mode.handle(Touch(Source.TOUCH, x=gap_x / w, y=rects[0].centery / h))
    assert mode.current.id == "root"


def test_touch_on_a_card_does_not_navigate(mode):
    """Картка не меню: випадковий дотик по ній нікуди не веде."""
    from robi.events import Source, Touch

    mode.open("goods")
    rects = mode.screen.item_rects(2)
    w, h = mode.screen.size
    mode.handle(Touch(Source.TOUCH, x=rects[0].centerx / w, y=rects[0].centery / h))
    assert mode.current.id == "goods"


def test_items_do_not_overlap_and_stay_on_screen(mode):
    for count in range(1, 11):
        rects = mode.screen.item_rects(count)
        assert len(rects) == count
        for rect in rects:
            assert rect.height > 0
            assert rect.bottom <= mode.screen.size[1]
        for index, a in enumerate(rects):
            for b in rects[index + 1:]:
                assert not a.colliderect(b)


# --- відсутні ассети ------------------------------------------------------


def test_missing_image_gives_a_card_without_image(content, tmp_path):
    """D-048 вимагає fallback, а не порожній екран."""
    mode = InfoMode((640, 480), content, assets=tmp_path)
    assert mode._image("courses/none.webp") is None
    surface = pygame.Surface((640, 480))
    mode.open("c1")
    mode.draw(surface)  # не має падати


def test_draw_works_without_assets_dir(mode):
    surface = pygame.Surface((640, 480))
    mode.draw(surface)
    mode.open("c1")
    mode.draw(surface)
