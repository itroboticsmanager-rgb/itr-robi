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
from .primitives import draw_panel
from .theme import PALETTE
from .typography import ui_font


class Overlay:
    def __init__(self, size: tuple[int, int]) -> None:
        # На рецепції екран є обличчям. Діагностика доступна через F1,
        # але не має зустрічати відвідувача після запуску.
        self.visible = False
        self.resize(size)

    def resize(self, size: tuple[int, int]) -> None:
        self.size = size
        self._font = ui_font(max(14, int(size[1] * 0.022)), weight="semibold")
        self._dot_r = max(4, int(size[1] * 0.008))

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

        w, h = self.size
        pad = max(10, int(h * 0.014))
        panel = pygame.Rect(
            pad,
            pad,
            min(int(w * 0.46), max(360, int(w * 0.30))),
            self._font.get_height() * 2 + pad * 2,
        )
        draw_panel(
            target,
            panel,
            fill=PALETTE.surface,
            radius=max(10, int(panel.height * 0.20)),
            border=PALETTE.border,
        )

        left = self._font.render(f"{state} / {mode}", True, PALETTE.hud)
        target.blit(left, (panel.left + pad, panel.top + pad // 2))

        right = self._font.render(f"{metrics.recent_fps:.0f} FPS", True, PALETTE.hud)
        target.blit(
            right,
            (panel.right - right.get_width() - pad, panel.top + pad // 2),
        )

        # Дві крапки: зв'язок і захоплення.
        y = panel.bottom - pad // 2 - self._dot_r
        x = panel.left + pad + self._dot_r
        self._dot(target, x, y, PALETTE.ok if online else PALETTE.offline)
        self._dot(
            target,
            x + self._dot_r * 4,
            y,
            PALETTE.error if capturing else PALETTE.dot_muted,
        )

    def _dot(self, target: pygame.Surface, x: int, y: int, color: tuple[int, int, int]) -> None:
        pygame.draw.circle(target, color, (x, y), self._dot_r)
