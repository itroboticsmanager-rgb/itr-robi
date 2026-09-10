"""Режим `info` — контент-меню для батьків (D-048).

Навігація — стек вузлів. Повернення з кореня означає «я закінчив»:
режим не перемикає себе сам, а лише повідомляє про це через
`wants_release()`, бо рішення про те, хто займає екран, ухвалює
координатор (див. `architecture.md`).

Камера тут вимкнена. Обличчя маскота на екрані немає, дивитися нема
кому й нема навіщо, тож тримати захоплення ввімкненим означало б лише
гріти пристрій і світити індикатором без причини.

Стан не переживає вихід. `exit()` чистить стек до кореня: наступний
відвідувач має почати з початку, а не побачити, де копався попередній.
Це та сама вимога, що й у `D-049` для анкети, і поширювати її на меню
дешевше, ніж потім пригадувати, які саме екрани були нешкідливими.
"""

from __future__ import annotations

from pathlib import Path

import pygame

from ..content import Content, Node
from ..events import Event, Intent, Touch
from ..state.coordinator import ModeName
from ..ui.menu_screen import MenuScreen


class InfoMode:
    name = ModeName.INFO

    def __init__(self, size: tuple[int, int], content: Content, assets: Path | None = None) -> None:
        self.screen = MenuScreen(size)
        self.content = content
        self._assets = assets
        self._stack: list[str] = [content.root]
        self._release = False
        self._images: dict[str, pygame.Surface | None] = {}

    # -- контракт режиму ---------------------------------------------------

    def wants_camera(self) -> bool:
        return False

    def wants_release(self) -> bool:
        return self._release

    def enter(self, payload: dict) -> None:
        self._stack = [self.content.root]
        self._release = False
        # Дозволяємо CRM відкрити конкретну гілку, але лише наявну: id з
        # команди — це вхідні дані, а не адреса, якій можна вірити.
        target = str(payload.get("node", "")).strip()
        if target and target in self.content.nodes and target != self.content.root:
            self._stack.append(target)
        self.screen.animate_in(1)

    def exit(self) -> None:
        self._stack = [self.content.root]
        self._release = False

    def resize(self, size: tuple[int, int]) -> None:
        self.screen.resize(size)

    # -- стан --------------------------------------------------------------

    @property
    def current(self) -> Node:
        return self.content.node(self._stack[-1])

    @property
    def depth(self) -> int:
        return len(self._stack)

    def back(self) -> None:
        if len(self._stack) > 1:
            self._stack.pop()
            self.screen.animate_in(-1)
        else:
            # Крок назад із кореня — це вихід із меню, а не глухий кут.
            self._release = True

    def open(self, node_id: str) -> None:
        if node_id in self.content.nodes:
            self._stack.append(node_id)
            self.screen.animate_in(1)

    # -- події -------------------------------------------------------------

    def handle(self, event: Event) -> None:
        if not isinstance(event, Touch):
            return
        if self.screen.hit_back(event.x, event.y):
            self.back()
            return
        node = self.current
        if not node.is_menu:
            return
        index = self.screen.hit_item(event.x, event.y, len(node.items))
        if index is not None:
            self.open(node.items[index])

    def update(self, dt: float) -> Intent | None:
        self.screen.update(dt)
        return None

    # -- малювання ---------------------------------------------------------

    def draw(self, surface: pygame.Surface) -> None:
        node = self.current
        if node.is_menu:
            labels = [self.content.label_for(i) for i in node.items]
            icons = [self.content.icon_for(i) for i in node.items]
            self.screen.draw_menu(surface, node.title, labels, show_back=True, icons=icons)
        else:
            self.screen.draw_card(
                surface, node.title, node.body, node.price, self._image(node.image)
            )

    def _image(self, name: str) -> pygame.Surface | None:
        """Відсутній або битий файл дає картку без картинки, а не падіння."""
        if not name or self._assets is None:
            return None
        if name in self._images:
            return self._images[name]
        path = self._assets / name
        surface: pygame.Surface | None = None
        try:
            if path.is_file():
                surface = pygame.image.load(str(path)).convert_alpha()
        except pygame.error:
            surface = None
        self._images[name] = surface
        return surface
