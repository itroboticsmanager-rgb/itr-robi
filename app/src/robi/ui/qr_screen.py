"""High-contrast QR handoff screen with a calm, trustworthy hierarchy."""

from __future__ import annotations

import pygame
import segno

from .icons import render_icon
from .primitives import draw_panel, ease_out_quart
from .theme import PALETTE
from .typography import ui_font, wrap_text

QUIET_ZONE = 4
ENTER_S = 0.28


class QrScreen:
    def __init__(self, size: tuple[int, int]) -> None:
        self.size = size
        self._cache_key: tuple[str, int] | None = None
        self._cache: pygame.Surface | None = None
        self._enter = 1.0
        self._build_fonts()

    def _build_fonts(self) -> None:
        h = self.size[1]
        self._font_title = ui_font(max(28, int(h * 0.056)), weight="bold")
        self._font_body = ui_font(max(18, int(h * 0.029)))
        self._font_note = ui_font(max(15, int(h * 0.021)), weight="semibold")

    def resize(self, size: tuple[int, int]) -> None:
        self.size = size
        self._cache_key = None
        self._build_fonts()

    def enter(self) -> None:
        self._enter = 0.0

    def update(self, dt: float) -> None:
        self._enter = min(1.0, self._enter + dt / ENTER_S)

    def _render_code(self, matrix: list[list[int]], box: int) -> pygame.Surface:
        n = len(matrix)
        total = (n + QUIET_ZONE * 2) * box
        surf = pygame.Surface((total, total))
        surf.fill(PALETTE.qr_paper)
        for y, row in enumerate(matrix):
            for x, on in enumerate(row):
                if on:
                    surf.fill(
                        PALETTE.qr_ink,
                        pygame.Rect(
                            (x + QUIET_ZONE) * box,
                            (y + QUIET_ZONE) * box,
                            box,
                            box,
                        ),
                    )
        return surf

    def _prepare(self, value: str, available: int) -> pygame.Surface:
        if self._cache_key == (value, available) and self._cache is not None:
            return self._cache
        matrix = [list(row) for row in segno.make(value, error="m").matrix]
        box = max(1, available // (len(matrix) + QUIET_ZONE * 2))
        self._cache = self._render_code(matrix, box)
        self._cache_key = (value, available)
        return self._cache

    def draw(self, target: pygame.Surface, value: str, caption: str = "") -> None:
        w, h = self.size
        target.fill(PALETTE.canvas)
        side = int(w * 0.055)
        top = int(h * 0.075)
        bottom = int(h * 0.075)
        gap = int(w * 0.055)
        left_w = int(w * 0.43)
        panel = pygame.Rect(side, top, left_w, h - top - bottom)

        progress = ease_out_quart(self._enter)
        slide = int((1.0 - progress) * w * 0.025)
        panel = panel.move(-slide, 0)
        draw_panel(
            target,
            panel,
            fill=PALETTE.surface,
            radius=max(20, int(h * 0.035)),
            border=PALETTE.border,
        )

        available = min(int(panel.width * 0.78), int(panel.height * 0.78))
        code = self._prepare(value, available)
        target.blit(code, code.get_rect(center=panel.center))

        text_left = panel.right + gap + slide
        text_width = w - side - text_left
        title = caption.strip() or "Відскануйте QR"
        title_y = int(h * 0.22)
        for line in wrap_text(self._font_title, title, text_width, max_lines=2):
            glyph = self._font_title.render(line, True, PALETTE.hud)
            target.blit(glyph, (text_left, title_y))
            title_y += int(self._font_title.get_linesize() * 0.98)

        accent_y = title_y + int(h * 0.025)
        pygame.draw.line(
            target,
            PALETTE.accent_yellow,
            (text_left, accent_y),
            (text_left + int(w * 0.052), accent_y),
            max(4, int(h * 0.009)),
        )

        body_y = accent_y + int(h * 0.065)
        body = "Наведіть камеру телефона на код. Посилання відкриється автоматично."
        for line in wrap_text(self._font_body, body, text_width, max_lines=4):
            glyph = self._font_body.render(line, True, PALETTE.hud_muted)
            target.blit(glyph, (text_left, body_y))
            body_y += int(self._font_body.get_linesize() * 1.18)

        note_y = min(int(h * 0.76), body_y + int(h * 0.075))
        note_icon = render_icon("help", max(32, int(h * 0.055)))
        target.blit(note_icon, (text_left, note_y))
        note = "ROBI не зберігає дані вашого телефона"
        note_surface = self._font_note.render(note, True, PALETTE.hud)
        target.blit(
            note_surface,
            note_surface.get_rect(
                midleft=(text_left + note_icon.get_width() + int(w * 0.014), note_y + note_icon.get_height() // 2)
            ),
        )

        # Small canonical face signature: the same ROBI on every screen.
        eye_y = int(h * 0.10)
        eye_x = w - side
        eye_r = max(8, int(h * 0.015))
        signature = pygame.Rect(0, 0, eye_r * 6, eye_r * 3)
        signature.midright = (eye_x + eye_r, eye_y)
        pygame.draw.rect(
            target,
            PALETTE.display_bottom,
            signature,
            border_radius=eye_r,
        )
        pygame.draw.rect(
            target,
            PALETTE.display_glass,
            signature,
            width=max(1, eye_r // 5),
            border_radius=eye_r,
        )
        for shift in (-eye_r, eye_r):
            pygame.draw.circle(target, PALETTE.surface, (signature.centerx + shift, eye_y), eye_r // 2)
            pygame.draw.circle(
                target,
                PALETTE.pupil,
                (signature.centerx + shift, eye_y + 1),
                max(2, eye_r // 4),
            )
        pygame.draw.lines(
            target,
            PALETTE.eye_line,
            False,
            [
                (signature.centerx - eye_r // 3, eye_y + int(eye_r * 0.68)),
                (signature.centerx, eye_y + int(eye_r * 0.90)),
                (signature.centerx + eye_r // 3, eye_y + int(eye_r * 0.68)),
            ],
            max(1, eye_r // 6),
        )
