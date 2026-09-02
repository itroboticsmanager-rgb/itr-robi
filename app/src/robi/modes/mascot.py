"""Режим `mascot` — фонова поведінка за замовчуванням.

Це єдиний режим, який вмикає камеру (D-033). Наслідок, який варто
пам'ятати: оскільки mascot фоновий, камера працює майже весь час роботи
пристрою, а видимої події «сканування» не існує. Саме тому апаратний
індикатор активності є вимогою, а не покращенням (D-029).
"""

from __future__ import annotations

import pygame

from ..events import Event, FaceSeen, Intent, NfcTouched, Presence, Touch
from ..state.coordinator import ModeName
from ..ui.face import FaceRenderer
from ..ui.theme import PALETTE

#: Скільки секунд без детекції обличчя треба, щоб ROBI повернув погляд
#: у нейтраль. Миттєве повернення виглядає смиканням.
# При 4 к/с (D-053) кадр приходить раз на 250 мс, тож 0.8 с — це лише три
# спроби. Профіль обличчя детектується гірше за анфас, і людина біля стійки
# губилася на звичайному повороті голови. 1.5 с переживає кілька промахів
# поспіль і все одно повертає погляд у нейтраль, коли людина справді пішла.
FACE_LOST_GRACE_S = 1.5

#: Мінімальний проміжок між RGB-акцентами, щоб підсвітка не блимала
#: безперервно при кожному русі перед столом.
ACCENT_COOLDOWN_S = 6.0


class MascotMode:
    name = ModeName.MASCOT

    def __init__(self, size: tuple[int, int]) -> None:
        self.face = FaceRenderer(size)
        self._since_face = 999.0
        self._present = False
        self._accent_cooldown = 0.0
        self._pending_accent: tuple[int, int, int] | None = None

    def wants_camera(self) -> bool:
        return True

    def enter(self, payload: dict) -> None:
        self._since_face = 999.0

    def exit(self) -> None:
        self.face.look_away()

    def resize(self, size: tuple[int, int]) -> None:
        self.face.resize(size)

    def handle(self, event: Event) -> None:
        if isinstance(event, FaceSeen):
            if event.count > 0:
                self._since_face = 0.0
                self.face.look_at(event.x, event.y)
            return

        if isinstance(event, Presence):
            was = self._present
            self._present = event.present
            if event.present and not was:
                self._request_accent(PALETTE.accent)
            return

        if isinstance(event, Touch):
            self._request_accent(PALETTE.ok)
            return

        if isinstance(event, NfcTouched):
            self._request_accent(PALETTE.ok if event.ok else PALETTE.error)

    def _request_accent(self, rgb: tuple[int, int, int]) -> None:
        if self._accent_cooldown > 0.0:
            return
        self._pending_accent = rgb
        self._accent_cooldown = ACCENT_COOLDOWN_S

    def update(self, dt: float) -> Intent | None:
        self._since_face += dt
        self._accent_cooldown = max(0.0, self._accent_cooldown - dt)

        if self._since_face > FACE_LOST_GRACE_S:
            self.face.look_away()

        self.face.update(dt)

        if self._pending_accent is not None:
            rgb, self._pending_accent = self._pending_accent, None
            return Intent(rgb=rgb, ttl=1.5)
        return None

    def draw(self, surface: pygame.Surface) -> None:
        self.face.draw(surface)
