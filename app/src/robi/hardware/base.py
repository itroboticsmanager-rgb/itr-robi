"""Контракт апаратного адаптера.

Кожен адаптер зобов'язаний уміти п'ять речей (software.md): явний
`initialize`, нормалізовані події, `health`, безпечний `shutdown` і fake-
реалізацію для тестів. Решта системи не знає, який модуль стоїть насправді.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from ..events import Event


@dataclass(frozen=True, slots=True)
class Health:
    name: str
    ok: bool
    detail: str = ""


class Adapter(Protocol):
    name: str

    def initialize(self) -> Health: ...

    def poll(self, dt: float) -> list[Event]:
        """Повертає нормалізовані події з моменту минулого виклику."""
        ...

    def health(self) -> Health: ...

    def shutdown(self) -> None: ...


class OutputAdapter(Protocol):
    """Виходи (RGB, звук). Рухомих виходів у v1 немає — D-019."""

    name: str

    def initialize(self) -> Health: ...

    def apply(self, rgb: tuple[int, int, int] | None, sound: str | None) -> None: ...

    def health(self) -> Health: ...

    def shutdown(self) -> None: ...
