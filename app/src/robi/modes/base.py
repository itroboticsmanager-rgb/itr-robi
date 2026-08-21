"""Контракт режиму контенту.

Режим не володіє обладнанням: він оголошує, що йому потрібно
(`wants_camera`), і повертає намір (`Intent`). Розподіляє ресурси
координатор і scheduler — див. architecture.md.
"""

from __future__ import annotations

from typing import Protocol

import pygame

from ..events import Event, Intent
from ..state.coordinator import ModeName


class Mode(Protocol):
    name: ModeName

    def wants_camera(self) -> bool:
        """Чи потрібне цьому режиму захоплення. Камера вмикається лише тут."""
        ...

    def enter(self, payload: dict) -> None: ...

    def exit(self) -> None: ...

    def handle(self, event: Event) -> None: ...

    def update(self, dt: float) -> Intent | None: ...

    def draw(self, surface: pygame.Surface) -> None: ...

    def resize(self, size: tuple[int, int]) -> None: ...
