"""Екран показу QR.

Вимоги з software.md: достатня quiet zone, контраст і розмір, CTA не
перекриває код. Payload сюди приходить уже перевіреним — валідація живе
в `integration.policy`, бо це питання безпеки, а не рендеру.
"""

from __future__ import annotations

import pygame
import segno

from .theme import PALETTE

#: Модулів тихої зони навколо коду. Менше чотирьох — і сканери починають
#: помилятися, особливо на глянцевому екрані.
QUIET_ZONE = 4


class QrScreen:
    def __init__(self, size: tuple[int, int]) -> None:
        self.size = size
        self._cache_key: tuple[str, int] | None = None
        self._cache: pygame.Surface | None = None
        self._caption_key: str | None = None
        self._caption_surface: pygame.Surface | None = None
        self._font = pygame.font.Font(None, max(18, int(size[1] * 0.07)))

    def resize(self, size: tuple[int, int]) -> None:
        self.size = size
        self._cache_key = None
        self._caption_key = None
        self._font = pygame.font.Font(None, max(18, int(size[1] * 0.07)))

    def _render_code(self, matrix: list[list[int]], box: int) -> pygame.Surface:
        """Растеризує QR вручну: segno дає матрицю, ми — рівні модулі.

        Масштабування готового зображення дало б розмиті межі модулів,
        а це прямий шлях до нечитабельного коду.
        """
        n = len(matrix)
        total = (n + QUIET_ZONE * 2) * box
        surf = pygame.Surface((total, total))
        surf.fill((255, 255, 255))
        for y, row in enumerate(matrix):
            for x, on in enumerate(row):
                if on:
                    surf.fill(
                        (0, 0, 0),
                        pygame.Rect(
                            (x + QUIET_ZONE) * box,
                            (y + QUIET_ZONE) * box,
                            box,
                            box,
                        ),
                    )
        return surf

    def _prepare(self, value: str) -> pygame.Surface:
        """Кодування й растеризація один раз на значення.

        Раніше `segno.make` викликався щокадру — бенчмарк показав 3.4 мс
        на кадр там, де має бути один blit. Кодування QR не залежить від
        часу, тож йому нема чого робити в гарячому шляху.
        """
        h = self.size[1]
        if self._cache_key == (value, h) and self._cache is not None:
            return self._cache

        matrix = [list(row) for row in segno.make(value, error="m").matrix]
        # Код займає доступну висоту, лишаючи місце під CTA знизу.
        available = int(h * 0.72)
        box = max(1, available // (len(matrix) + QUIET_ZONE * 2))

        self._cache = self._render_code(matrix, box)
        self._cache_key = (value, h)
        return self._cache

    def draw(self, target: pygame.Surface, value: str, caption: str = "") -> None:
        w, h = self.size
        target.fill(PALETTE.face_bottom)

        code = self._prepare(value)
        top = int(h * 0.06)
        target.blit(code, (w // 2 - code.get_width() // 2, top))

        if caption:
            if caption != self._caption_key:
                self._caption_surface = self._font.render(caption, True, PALETTE.hud)
                self._caption_key = caption
            label = self._caption_surface
            # CTA під кодом, а не поверх нього.
            target.blit(
                label,
                (w // 2 - label.get_width() // 2, top + code.get_height() + int(h * 0.03)),
            )
