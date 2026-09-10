"""The reception showcase: ROBI, one editorial banner and 2x5 actions."""

from __future__ import annotations

import math
from dataclasses import dataclass

import pygame

from ..banners import Banner
from .icons import render_icon, resolve_icon
from .primitives import draw_page_dots, draw_panel, ease_out_quart
from .theme import PALETTE
from .typography import fit_font, ui_font, wrap_text

# The approved 3:2 composition.
STRIP_H = 0.16
BUTTONS_H = 0.35
GAP = 0.014
SIDE = 0.03
MAX_ACTIONS = 10
FACE_OVERSHOOT = 1.50

SLIDE_S = 7.0
FADE_S = 0.34


@dataclass(frozen=True, slots=True)
class Layout:
    strip: pygame.Rect
    carousel: pygame.Rect
    buttons: pygame.Rect


@dataclass(frozen=True, slots=True)
class NavAction:
    label: str
    key: str = ""
    icon: str = ""

    @property
    def icon_name(self) -> str:
        return resolve_icon(self.icon, key=self.key, label=self.label)


def _coerce_action(value: NavAction | str | tuple) -> NavAction:
    """Keep the drawing API forgiving for tests and local tools."""
    if isinstance(value, NavAction):
        return value
    if isinstance(value, str):
        return NavAction(value)
    if len(value) >= 3:
        return NavAction(str(value[0]), str(value[1]), str(value[2]))
    return NavAction(str(value[0]), str(value[1]) if len(value) > 1 else "")


class Showcase:
    def __init__(self, size: tuple[int, int]) -> None:
        self.size = size
        self._index = 0
        self._previous_index: int | None = None
        self._elapsed = 0.0
        self._transition = FADE_S
        self._banner_cache: dict[tuple, pygame.Surface] = {}
        self._fonts: tuple[pygame.font.Font, ...] | None = None
        self._build_strip_assets()

    def resize(self, size: tuple[int, int]) -> None:
        self.size = size
        self._banner_cache.clear()
        self._fonts = None
        self._build_strip_assets()

    def _build_strip_assets(self) -> None:
        w, h = self.size
        strip_h = max(2, int(h * STRIP_H))
        self._strip_background = pygame.Surface((w, strip_h))
        for y in range(strip_h):
            t = y / max(1, strip_h - 1)
            color = tuple(
                int(
                    PALETTE.primary_soft[i]
                    + (PALETTE.primary[i] - PALETTE.primary_soft[i]) * t
                )
                for i in range(3)
            )
            pygame.draw.line(self._strip_background, color, (0, y), (w, y))
        glow = pygame.Surface((w, strip_h), pygame.SRCALPHA)
        pygame.draw.circle(
            glow,
            (*PALETTE.highlight, 70),
            (w // 2, int(strip_h * 0.50)),
            int(w * 0.23),
        )
        ring_color = (*PALETTE.highlight, 42)
        for side in (-1, 1):
            center_x = int(w * (0.13 if side < 0 else 0.87))
            for scale in (0.22, 0.34, 0.48):
                radius = int(w * scale)
                rect = pygame.Rect(0, 0, radius, radius)
                rect.center = (center_x, strip_h // 2)
                pygame.draw.arc(
                    glow,
                    ring_color,
                    rect,
                    -0.65 if side < 0 else math.pi - 0.65,
                    0.65 if side < 0 else math.pi + 0.65,
                    max(1, int(h * 0.0018)),
                )
        for x, y, radius in (
            (int(w * 0.075), int(strip_h * 0.34), 3),
            (int(w * 0.17), int(strip_h * 0.70), 2),
            (int(w * 0.83), int(strip_h * 0.27), 2),
            (int(w * 0.93), int(strip_h * 0.62), 3),
        ):
            pygame.draw.circle(glow, (*PALETTE.highlight, 105), (x, y), radius)
        self._strip_background.blit(glow, (0, 0))

    def _build_fonts(self) -> None:
        if self._fonts is not None:
            return
        h = self.size[1]
        self._fonts = (
            ui_font(max(28, int(h * 0.048)), weight="bold"),
            ui_font(max(17, int(h * 0.022))),
            ui_font(max(18, int(h * 0.021)), weight="semibold"),
        )

    @property
    def font_title(self) -> pygame.font.Font:
        self._build_fonts()
        return self._fonts[0]

    @property
    def font_caption(self) -> pygame.font.Font:
        self._build_fonts()
        return self._fonts[1]

    @property
    def font_button(self) -> pygame.font.Font:
        self._build_fonts()
        return self._fonts[2]

    def layout(self) -> Layout:
        w, h = self.size
        side = int(w * SIDE)
        gap = max(8, int(h * GAP))
        strip_h = int(h * STRIP_H)
        buttons_h = int(h * BUTTONS_H)
        strip = pygame.Rect(0, 0, w, strip_h)
        buttons = pygame.Rect(side, h - buttons_h, w - side * 2, buttons_h - gap)
        carousel = pygame.Rect(
            side,
            strip_h + gap,
            w - side * 2,
            buttons.top - strip_h - gap * 2,
        )
        return Layout(strip=strip, carousel=carousel, buttons=buttons)

    @staticmethod
    def _row_counts(count: int) -> list[int]:
        count = max(0, min(MAX_ACTIONS, count))
        if count <= 5:
            return [count] if count else []
        return [math.ceil(count / 2), count // 2]

    def button_rects(self, count: int) -> list[pygame.Rect]:
        row = self.layout().buttons
        rows = self._row_counts(count)
        if not rows:
            return []

        gap_x = max(10, int(self.size[0] * 0.010))
        gap_y = max(10, int(self.size[1] * 0.012))
        max_cols = max(rows)
        cell_w = min(
            (row.width - gap_x * (max_cols - 1)) // max_cols,
            int(self.size[0] * 0.178),
        )
        if len(rows) == 1:
            cell_h = min(int(self.size[1] * 0.145), row.height)
            start_y = row.centery - cell_h // 2
        else:
            cell_h = (row.height - gap_y) // 2
            start_y = row.top

        rects: list[pygame.Rect] = []
        for row_index, columns in enumerate(rows):
            total_w = columns * cell_w + (columns - 1) * gap_x
            start_x = row.centerx - total_w // 2
            y = start_y + row_index * (cell_h + gap_y)
            rects.extend(
                pygame.Rect(start_x + column * (cell_w + gap_x), y, cell_w, cell_h)
                for column in range(columns)
            )
        return rects

    def hit_strip(self, x: float, y: float) -> bool:
        return self.layout().strip.collidepoint(
            int(x * self.size[0]), int(y * self.size[1])
        )

    def hit_button(self, x: float, y: float, count: int) -> int | None:
        point = (int(x * self.size[0]), int(y * self.size[1]))
        for index, rect in enumerate(self.button_rects(count)):
            if rect.collidepoint(point):
                return index
        return None

    def update(self, dt: float, count: int) -> None:
        self._transition = min(FADE_S, self._transition + dt)
        if count <= 1:
            self._index = 0
            self._previous_index = None
            self._elapsed = 0.0
            return
        self._elapsed += dt
        if self._elapsed >= SLIDE_S:
            self._elapsed %= SLIDE_S
            self._previous_index = self._index
            self._index = (self._index + 1) % count
            self._transition = 0.0

    @property
    def index(self) -> int:
        return self._index

    def draw(
        self,
        target: pygame.Surface,
        face: pygame.Surface,
        banners: list[Banner],
        actions: list[NavAction | str | tuple],
        image_for,
    ) -> None:
        target.fill(PALETTE.canvas)
        box = self.layout()
        target.blit(self._strip_background, box.strip.topleft)
        target.set_clip(box.strip)
        # The logical portrait is taller than the strip. We reveal its face
        # and crop the lower shell instead of recomputing or flattening ROBI.
        crop = max(0, face.get_height() - box.strip.height)
        face_rect = face.get_rect(
            midtop=(box.strip.centerx, -int(crop * 0.20))
        )
        target.blit(face, face_rect)
        handle_w = max(38, int(self.size[0] * 0.052))
        handle_h = max(4, int(self.size[1] * 0.004))
        handle = pygame.Rect(0, 0, handle_w, handle_h)
        handle.midbottom = (
            int(box.strip.width * 0.92),
            box.strip.bottom - max(4, handle_h),
        )
        pygame.draw.rect(target, PALETTE.face_glow, handle, border_radius=handle_h // 2)
        target.set_clip(None)
        pygame.draw.line(
            target,
            PALETTE.border,
            (0, box.strip.bottom),
            (box.strip.right, box.strip.bottom),
            1,
        )
        self._draw_carousel(target, box.carousel, banners, image_for)
        self._draw_buttons(target, [_coerce_action(a) for a in actions[:MAX_ACTIONS]])

    def _draw_carousel(self, target, rect: pygame.Rect, banners: list[Banner], image_for) -> None:
        # Лише банери з CRM. Коли їх немає, місце лишається тихим: вигадане
        # привітання від імені школи тут не з'являється.
        if not banners:
            return

        draw_panel(
            target,
            rect,
            fill=PALETTE.surface,
            radius=max(18, int(rect.height * 0.055)),
            border=PALETTE.border,
        )

        current = self._index % len(banners)
        progress = ease_out_quart(self._transition / FADE_S) if FADE_S else 1.0
        if self._previous_index is not None and self._transition < FADE_S:
            previous = banners[self._previous_index % len(banners)]
            old = self._banner_layer(previous, rect.size, image_for)
            old.set_alpha(int(255 * (1.0 - progress)))
            target.blit(old, rect.topleft)
            old.set_alpha(255)

        layer = self._banner_layer(banners[current], rect.size, image_for)
        layer.set_alpha(max(24, int(255 * progress)))
        target.blit(layer, rect.topleft)
        layer.set_alpha(255)

        draw_page_dots(
            target,
            (rect.centerx, rect.bottom - max(9, int(rect.height * 0.025))),
            len(banners),
            current,
            radius=max(3, int(self.size[1] * 0.0045)),
        )

    def _banner_layer(self, banner: Banner, size: tuple[int, int], image_for) -> pygame.Surface:
        raw = image_for(banner)
        image_key = (raw.get_width(), raw.get_height()) if raw is not None else None
        key = (banner.id, banner.title, banner.description, size, image_key)
        cached = self._banner_cache.get(key)
        if cached is not None:
            return cached

        w, h = size
        layer = pygame.Surface(size, pygame.SRCALPHA)
        text_w = int(w * (0.42 if raw is not None else 0.56))
        pad_x = int(w * 0.035)
        pad_y = int(h * 0.12)
        title_width = text_w - pad_x * 2
        title_lines = wrap_text(self.font_title, banner.title, title_width, max_lines=2)
        y = pad_y
        for line in title_lines:
            glyph = self.font_title.render(line, True, PALETTE.hud)
            layer.blit(glyph, (pad_x, y))
            y += int(self.font_title.get_linesize() * 0.95)

        accent_y = min(y + int(h * 0.025), int(h * 0.58))
        pygame.draw.line(
            layer,
            PALETTE.accent_yellow,
            (pad_x, accent_y),
            (pad_x + int(w * 0.055), accent_y),
            max(4, int(h * 0.012)),
        )
        y = accent_y + int(h * 0.055)
        for line in wrap_text(self.font_caption, banner.description, title_width, max_lines=3):
            glyph = self.font_caption.render(line, True, PALETTE.hud_muted)
            layer.blit(glyph, (pad_x, y))
            y += int(self.font_caption.get_linesize() * 1.15)

        if raw is not None:
            image_rect = pygame.Rect(text_w, 0, w - text_w, h)
            rounded = self._rounded_cover(raw, image_rect.size, max(12, int(h * 0.05)))
            layer.blit(rounded, image_rect.topleft)
        else:
            # Intentional offline/empty artwork built from the icon language.
            art_center = (int(w * 0.79), int(h * 0.48))
            pygame.draw.circle(layer, PALETTE.surface_alt, art_center, int(h * 0.31))
            pygame.draw.circle(
                layer,
                PALETTE.accent_yellow,
                (art_center[0] + int(h * 0.22), art_center[1] - int(h * 0.20)),
                int(h * 0.035),
            )
            icon = render_icon(
                "generic", int(h * 0.32), PALETTE.primary, PALETTE.accent_yellow
            )
            layer.blit(icon, icon.get_rect(center=art_center))

        self._banner_cache[key] = layer
        return layer

    @staticmethod
    def _rounded_cover(image: pygame.Surface, size: tuple[int, int], radius: int) -> pygame.Surface:
        width, height = size
        scale = max(width / image.get_width(), height / image.get_height())
        scaled_size = (
            max(1, int(image.get_width() * scale)),
            max(1, int(image.get_height() * scale)),
        )
        scaled = pygame.transform.smoothscale(image, scaled_size)
        result = pygame.Surface(size, pygame.SRCALPHA)
        result.blit(scaled, scaled.get_rect(center=result.get_rect().center))
        mask = pygame.Surface(size, pygame.SRCALPHA)
        pygame.draw.rect(mask, (255, 255, 255, 255), mask.get_rect(), border_radius=radius)
        result.blit(mask, (0, 0), special_flags=pygame.BLEND_RGBA_MIN)
        return result

    def _draw_buttons(self, target: pygame.Surface, actions: list[NavAction]) -> None:
        rects = self.button_rects(len(actions))
        if not rects:
            return
        pressed_index: int | None = None
        try:
            if pygame.mouse.get_pressed(num_buttons=3)[0]:
                pressed_index = next(
                    (
                        i
                        for i, rect in enumerate(rects)
                        if rect.collidepoint(pygame.mouse.get_pos())
                    ),
                    None,
                )
        except pygame.error:
            pressed_index = None

        dock = rects[0].unionall(rects[1:]).inflate(
            max(18, int(self.size[0] * 0.014)),
            max(16, int(self.size[1] * 0.014)),
        )
        dock.clamp_ip(self.layout().buttons)
        draw_panel(
            target,
            dock,
            fill=PALETTE.surface,
            radius=max(22, int(dock.height * 0.065)),
            border=PALETTE.border,
        )

        plate_colors = (
            PALETTE.action_blue,
            PALETTE.action_lilac,
            PALETTE.action_yellow,
            PALETTE.action_mint,
            PALETTE.action_coral,
        )
        accent_colors = (
            PALETTE.accent_yellow,
            PALETTE.accent_coral,
            PALETTE.primary_soft,
            PALETTE.ok,
            PALETTE.accent_yellow,
        )
        for index, (action, base_rect) in enumerate(zip(actions, rects)):
            pressed = index == pressed_index
            rect = base_rect.inflate(-8, -8) if pressed else base_rect
            if pressed:
                draw_panel(
                    target,
                    rect,
                    fill=PALETTE.surface_pressed,
                    radius=max(14, int(rect.height * 0.14)),
                    border=None,
                    shadow=False,
                )

            plate_size = min(int(rect.height * 0.48), int(rect.width * 0.30))
            plate = pygame.Rect(0, 0, plate_size, plate_size)
            plate.midtop = (rect.centerx, rect.top + int(rect.height * 0.075))
            pygame.draw.rect(
                target,
                plate_colors[index % len(plate_colors)],
                plate,
                border_radius=int(plate_size * 0.31),
            )
            pygame.draw.rect(
                target,
                (*PALETTE.highlight, 155),
                plate.inflate(-int(plate_size * 0.12), -int(plate_size * 0.12)),
                width=max(1, int(plate_size * 0.025)),
                border_radius=int(plate_size * 0.24),
            )
            icon_size = int(plate_size * 0.68)
            icon = render_icon(
                action.icon_name,
                icon_size,
                PALETTE.primary,
                accent_colors[index % len(accent_colors)],
            )
            target.blit(icon, icon.get_rect(center=plate.center))

            preferred = self.font_button.get_height()
            font = fit_font(
                action.label,
                int(rect.width * 0.86),
                preferred,
                max(15, int(self.size[1] * 0.016)),
            )
            label = font.render(action.label, True, PALETTE.hud)
            target.blit(
                label,
                label.get_rect(
                    midbottom=(rect.centerx, rect.bottom - int(rect.height * 0.075))
                ),
            )

    def face_size(self) -> tuple[int, int]:
        _, h = self.size
        face_h = max(220, int(h * STRIP_H * FACE_OVERSHOOT))
        return max(300, int(face_h * 1.60)), face_h
