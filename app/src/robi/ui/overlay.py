"""Діагностичний HUD.

Не частина продукту: на рецепції його не буде. Але під час розробки він
показує головне — стан, режим, зв'язок із CRM і чи працює захоплення.

Індикатор камери тут навмисно дубльований з апаратним (D-029): якщо
софтверний горить, а апаратний ні, значить десь розійшлися стани, і це
треба побачити на столі, а не в полі.
"""

from __future__ import annotations

import pygame

from ..health.metrics import Metrics
from .theme import PALETTE


class Overlay:
    def __init__(self, size: tuple[int, int]) -> None:
        self.visible = True
        self.resize(size)

    def resize(self, size: tuple[int, int]) -> None:
        self.size = size
        self._font = pygame.font.Font(None, max(16, int(size[1] * 0.045)))
        self._dot_r = max(4, int(size[1] * 0.014))

    def draw(
        self,
        target: pygame.Surface,
        *,
        state: str,
        mode: str,
        online: bool,
        capturing: bool,
        metrics: Metrics,
    ) -> None:
        if not self.visible:
            return

        w, _ = self.size
        pad = self._dot_r

        left = self._font.render(f"{state} / {mode}", True, PALETTE.hud)
        target.blit(left, (pad * 2, pad))

        right = self._font.render(f"{metrics.recent_fps:.0f} FPS", True, PALETTE.hud)
        target.blit(right, (w - right.get_width() - pad * 2, pad))

        # Дві крапки: зв'язок і захоплення.
        y = pad + left.get_height() + self._dot_r + 2
        self._dot(target, pad * 2 + self._dot_r, y, PALETTE.ok if online else PALETTE.offline)
        self._dot(
            target,
            pad * 2 + self._dot_r * 4,
            y,
            PALETTE.error if capturing else (90, 110, 140),
        )

    def _dot(self, target: pygame.Surface, x: int, y: int, color: tuple[int, int, int]) -> None:
        pygame.draw.circle(target, color, (x, y), self._dot_r)
