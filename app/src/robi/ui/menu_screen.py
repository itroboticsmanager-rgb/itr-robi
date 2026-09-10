"""Modern touch-first content navigation and editorial detail pages."""

from __future__ import annotations

import math

import pygame

from .icons import render_icon, resolve_icon
from .primitives import draw_panel, ease_out_quart
from .theme import PALETTE
from .typography import fit_font, ui_font, wrap_text

HEADER_H = 0.145
SIDE = 0.045
GAP = 0.016
BACK_W = 0.145
ENTER_S = 0.24


class MenuScreen:
    def __init__(self, size: tuple[int, int]) -> None:
        self.size = size
        self._motion = 1.0
        self._motion_direction = 1
        self._image_cache: dict[tuple[int, tuple[int, int]], pygame.Surface] = {}
        self._build_fonts()

    def resize(self, size: tuple[int, int]) -> None:
        self.size = size
        self._image_cache.clear()
        self._build_fonts()

    def _build_fonts(self) -> None:
        h = self.size[1]
        self.font_title = ui_font(max(26, int(h * 0.054)), weight="bold")
        self.font_item = ui_font(max(18, int(h * 0.031)), weight="semibold")
        self.font_body = ui_font(max(16, int(h * 0.027)))
        self.font_price = ui_font(max(18, int(h * 0.034)), weight="semibold")
        self.font_back = ui_font(max(16, int(h * 0.024)), weight="semibold")

    def animate_in(self, direction: int = 1) -> None:
        self._motion = 0.0
        self._motion_direction = 1 if direction >= 0 else -1

    def update(self, dt: float) -> None:
        self._motion = min(1.0, self._motion + dt / ENTER_S)

    def _offset(self) -> int:
        remaining = 1.0 - ease_out_quart(self._motion)
        return int(self.size[0] * 0.028 * remaining * self._motion_direction)

    # -- shared geometry -------------------------------------------------

    def back_rect(self) -> pygame.Rect:
        w, h = self.size
        side = int(w * SIDE)
        top = int(h * 0.032)
        return pygame.Rect(side, top, int(w * BACK_W), int(h * HEADER_H * 0.56))

    def item_rects(self, count: int) -> list[pygame.Rect]:
        if count <= 0:
            return []
        count = min(10, count)
        w, h = self.size
        side = int(w * SIDE)
        gap_x = max(8, int(w * GAP))
        gap_y = max(8, int(h * GAP))
        top = int(h * HEADER_H)
        bottom = int(h * 0.045)
        content = pygame.Rect(side, top, w - side * 2, h - top - bottom)

        columns = 1 if count == 1 else 2
        rows = math.ceil(count / columns)
        cell_w = (content.width - gap_x * (columns - 1)) // columns
        cell_h = (content.height - gap_y * (rows - 1)) // rows
        rects: list[pygame.Rect] = []
        for index in range(count):
            row, column = divmod(index, columns)
            rects.append(
                pygame.Rect(
                    content.left + column * (cell_w + gap_x),
                    content.top + row * (cell_h + gap_y),
                    cell_w,
                    cell_h,
                )
            )
        return rects

    def hit_back(self, x: float, y: float) -> bool:
        return self.back_rect().collidepoint(int(x * self.size[0]), int(y * self.size[1]))

    def hit_item(self, x: float, y: float, count: int) -> int | None:
        point = (int(x * self.size[0]), int(y * self.size[1]))
        for index, rect in enumerate(self.item_rects(count)):
            if rect.collidepoint(point):
                return index
        return None

    # -- chrome ----------------------------------------------------------

    def _chrome(self, target: pygame.Surface, title: str, show_back: bool) -> None:
        target.fill(PALETTE.canvas)
        w, h = self.size

        if show_back:
            back = self.back_rect()
            draw_panel(
                target,
                back,
                fill=PALETTE.surface,
                radius=back.height // 2,
                border=PALETTE.border,
                shadow=False,
            )
            arrow = self.font_back.render("‹", True, PALETTE.primary)
            label = self.font_back.render("Назад", True, PALETTE.hud)
            group_w = arrow.get_width() + label.get_width() + int(w * 0.008)
            x = back.centerx - group_w // 2
            target.blit(arrow, arrow.get_rect(midleft=(x, back.centery - 1)))
            target.blit(
                label,
                label.get_rect(midleft=(x + arrow.get_width() + int(w * 0.008), back.centery)),
            )

        title_left = self.back_rect().right + int(w * 0.025) if show_back else int(w * SIDE)
        # A tiny canonical face badge keeps ROBI present without turning every
        # page back into a full character screen.
        eye_y = int(h * 0.073)
        eye_x = w - int(w * SIDE)
        eye_r = max(8, int(h * 0.016))
        title_right = eye_x - eye_r * 4 - int(w * 0.018)
        title_font = fit_font(
            title,
            max(120, title_right - title_left),
            max(26, int(h * 0.054)),
            max(20, int(h * 0.032)),
            weight="bold",
        )
        heading = title_font.render(title, True, PALETTE.hud)
        target.blit(heading, heading.get_rect(midleft=(title_left, int(h * 0.075))))

        signature = pygame.Rect(0, 0, eye_r * 5, int(eye_r * 2.65))
        signature.midright = (eye_x + eye_r, eye_y)
        pygame.draw.rect(
            target,
            PALETTE.display_bottom,
            signature,
            border_radius=signature.height // 2,
        )
        pygame.draw.rect(
            target,
            PALETTE.display_glass,
            signature,
            width=max(1, eye_r // 7),
            border_radius=signature.height // 2,
        )
        for shift in (-eye_r * 2, 0):
            pygame.draw.circle(target, PALETTE.eye_white, (eye_x + shift, eye_y), int(eye_r * 0.72))
            pygame.draw.circle(target, PALETTE.pupil, (eye_x + shift, eye_y + 1), int(eye_r * 0.36))
        mouth_x = eye_x - eye_r
        pygame.draw.lines(
            target,
            PALETTE.eye_line,
            False,
            [
                (mouth_x - int(eye_r * 0.34), eye_y + int(eye_r * 0.72)),
                (mouth_x, eye_y + int(eye_r * 0.93)),
                (mouth_x + int(eye_r * 0.34), eye_y + int(eye_r * 0.72)),
            ],
            max(1, eye_r // 7),
        )

    # -- menu ------------------------------------------------------------

    def draw_menu(
        self,
        target: pygame.Surface,
        title: str,
        labels: list[str],
        show_back: bool,
        icons: list[str] | None = None,
    ) -> None:
        self._chrome(target, title, show_back)
        w, h = self.size
        offset = self._offset()
        icons = icons or [""] * len(labels)
        base_rects = self.item_rects(len(labels))
        if not base_rects:
            return

        panel = base_rects[0].unionall(base_rects[1:]).move(offset, 0)
        draw_panel(
            target,
            panel,
            fill=PALETTE.surface,
            radius=max(22, int(panel.height * 0.035)),
            border=PALETTE.border,
        )
        columns = 1 if len(labels) == 1 else 2
        plate_colors = (
            PALETTE.action_blue,
            PALETTE.action_lilac,
            PALETTE.action_yellow,
            PALETTE.action_mint,
            PALETTE.action_coral,
        )

        for index, (label, base_rect) in enumerate(zip(labels, base_rects)):
            rect = base_rect.move(offset, 0)
            if index >= columns:
                line_y = rect.top - max(4, int(h * GAP)) // 2
                pygame.draw.line(
                    target,
                    PALETTE.border,
                    (rect.left + int(rect.width * 0.04), line_y),
                    (rect.right - int(rect.width * 0.04), line_y),
                    1,
                )
            if columns == 2 and index % 2 == 1:
                line_x = rect.left - max(4, int(w * GAP)) // 2
                pygame.draw.line(
                    target,
                    PALETTE.border,
                    (line_x, rect.top + int(rect.height * 0.09)),
                    (line_x, rect.bottom - int(rect.height * 0.09)),
                    1,
                )

            icon_name = resolve_icon(icons[index] if index < len(icons) else "", label=label)
            plate_size = min(int(rect.height * 0.58), int(rect.width * 0.15))
            plate = pygame.Rect(0, 0, plate_size, plate_size)
            plate.midleft = (rect.left + int(rect.width * 0.055), rect.centery)
            pygame.draw.rect(
                target,
                plate_colors[index % len(plate_colors)],
                plate,
                border_radius=int(plate_size * 0.30),
            )
            icon_size = int(plate_size * 0.68)
            icon = render_icon(icon_name, icon_size)
            target.blit(icon, icon.get_rect(center=plate.center))

            text_left = plate.right + int(rect.width * 0.045)
            available = rect.right - text_left - int(rect.width * 0.12)
            font = fit_font(
                label,
                available,
                self.font_item.get_height(),
                max(14, int(self.size[1] * 0.021)),
            )
            glyph = font.render(label, True, PALETTE.hud)
            target.blit(glyph, glyph.get_rect(midleft=(text_left, rect.centery)))

            chevron_x = rect.right - int(rect.width * 0.055)
            chevron = self.font_item.render("›", True, PALETTE.primary_soft)
            target.blit(chevron, chevron.get_rect(center=(chevron_x, rect.centery)))

    # -- detail card -----------------------------------------------------

    def draw_card(
        self,
        target: pygame.Surface,
        title: str,
        body: str,
        price: str,
        image: pygame.Surface | None,
    ) -> None:
        self._chrome(target, title, show_back=True)
        w, h = self.size
        side = int(w * SIDE)
        top = int(h * HEADER_H)
        bottom = int(h * 0.055)
        content = pygame.Rect(side, top, w - side * 2, h - top - bottom)
        offset = self._offset()

        if image is not None:
            image_rect = pygame.Rect(
                content.left + offset,
                content.top,
                int(content.width * 0.46),
                content.height,
            )
            draw_panel(
                target,
                image_rect,
                fill=PALETTE.surface_alt,
                radius=max(18, int(h * 0.032)),
                border=PALETTE.border,
            )
            inset = max(6, int(h * 0.010))
            fitted = self._rounded_cover(
                image,
                (image_rect.width - inset * 2, image_rect.height - inset * 2),
                max(12, int(h * 0.026)),
            )
            target.blit(fitted, (image_rect.left + inset, image_rect.top + inset))
            text_left = image_rect.right + int(w * 0.04)
            text_width = content.right - text_left
        else:
            text_left = content.left + int(content.width * 0.10) + offset
            text_width = int(content.width * 0.80)
            self._draw_empty_art(target, content.move(offset, 0))

        cursor = content.top + int(h * 0.045)
        if price:
            price_surface = self.font_price.render(price, True, PALETTE.primary_pressed)
            pill = pygame.Rect(
                text_left,
                cursor,
                price_surface.get_width() + int(w * 0.035),
                price_surface.get_height() + int(h * 0.020),
            )
            draw_panel(
                target,
                pill,
                fill=PALETTE.surface_alt,
                radius=pill.height // 2,
                border=None,
                shadow=False,
            )
            target.blit(price_surface, price_surface.get_rect(center=pill.center))
            cursor = pill.bottom + int(h * 0.045)

        max_lines = max(1, (content.bottom - cursor) // int(self.font_body.get_linesize() * 1.35))
        for line in wrap_text(self.font_body, body, text_width, max_lines=max_lines):
            glyph = self.font_body.render(line, True, PALETTE.hud_muted)
            target.blit(glyph, (text_left, cursor))
            cursor += int(self.font_body.get_linesize() * 1.35)

    def _draw_empty_art(self, target: pygame.Surface, rect: pygame.Rect) -> None:
        center = (rect.right - int(rect.width * 0.09), rect.bottom - int(rect.height * 0.18))
        radius = int(rect.height * 0.11)
        pygame.draw.circle(target, PALETTE.surface_alt, center, radius)
        icon = render_icon("generic", int(radius * 1.15))
        target.blit(icon, icon.get_rect(center=center))

    def _rounded_cover(
        self,
        image: pygame.Surface,
        size: tuple[int, int],
        radius: int,
    ) -> pygame.Surface:
        key = (id(image), size)
        cached = self._image_cache.get(key)
        if cached is not None:
            return cached
        width, height = size
        scale = max(width / image.get_width(), height / image.get_height())
        scaled = pygame.transform.smoothscale(
            image,
            (
                max(1, int(image.get_width() * scale)),
                max(1, int(image.get_height() * scale)),
            ),
        )
        result = pygame.Surface(size, pygame.SRCALPHA)
        result.blit(scaled, scaled.get_rect(center=result.get_rect().center))
        mask = pygame.Surface(size, pygame.SRCALPHA)
        pygame.draw.rect(mask, (255, 255, 255, 255), mask.get_rect(), border_radius=radius)
        result.blit(mask, (0, 0), special_flags=pygame.BLEND_RGBA_MIN)
        self._image_cache[key] = result
        return result
