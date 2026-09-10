"""Режим `qr` — показ коду. ROBI коди не сканує (D-031).

Камера тут не бере участі: якщо перехід стався з `mascot`, захоплення
зупиняється на час показу. Це не оптимізація, а очікувана поведінка —
під час показу QR пристрою нема на що дивитися.
"""

from __future__ import annotations

import pygame

from ..events import Event, Intent
from ..state.coordinator import ModeName
from ..ui.qr_screen import QrScreen

DEFAULT_CAPTION = "Наведіть камеру телефона"


class QrMode:
    name = ModeName.QR

    def __init__(self, size: tuple[int, int]) -> None:
        self.screen = QrScreen(size)
        self._value = ""
        self._caption = DEFAULT_CAPTION

    def wants_camera(self) -> bool:
        return False

    def wants_release(self) -> bool:
        return False

    def enter(self, payload: dict) -> None:
        self._value = str(payload.get("value", ""))
        self._caption = str(payload.get("title") or DEFAULT_CAPTION)
        self.screen.enter()

    def exit(self) -> None:
        # Значення не переживає вихід із режиму: платіжні посилання
        # одноразові, і кешованого показу бути не повинно (D-038).
        self._value = ""

    def resize(self, size: tuple[int, int]) -> None:
        self.screen.resize(size)

    def handle(self, event: Event) -> None:
        return

    def update(self, dt: float) -> Intent | None:
        self.screen.update(dt)
        return None

    def draw(self, surface: pygame.Surface) -> None:
        if self._value:
            self.screen.draw(surface, self._value, self._caption)
