"""Межа vision — архітектурна реалізація заборони D-027.

Тип, який шар віддає назовні, є `FaceSeen`: кількість, позиція, розмір.
Кадру в ньому немає, тому решта системи фізично не може його отримати,
залогувати чи відправити в CRM. Це не дисципліна виклику, а межа модуля.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from ..events import FaceSeen
from ..hardware.base import Health


@dataclass(frozen=True, slots=True)
class VisionStats:
    """Те, що vision дозволено розповідати про себе."""

    frames: int = 0
    detections: int = 0
    capturing: bool = False


class Vision(Protocol):
    name: str

    def initialize(self) -> Health: ...

    def start_capture(self) -> None:
        """Захоплення вмикається лише коли режим його справді потребує."""
        ...

    def stop_capture(self) -> None:
        """Зупинка має бути реальною: індикатор гасне за нею (D-029)."""
        ...

    @property
    def capturing(self) -> bool: ...

    def poll(self, dt: float) -> list[FaceSeen]: ...

    def stats(self) -> VisionStats: ...

    def health(self) -> Health: ...

    def shutdown(self) -> None: ...
