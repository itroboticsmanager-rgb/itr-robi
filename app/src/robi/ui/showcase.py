"""Вітрина: смужка з очима, карусель банерів і ряд кнопок (`D-058`).

Це те, що бачить хол більшу частину дня, тож головна вимога — не
привертати увагу до себе, а показувати справу. ROBI лишається зверху
вузькою смужкою: він упізнаваний, але не займає екран, поки з ним не
почали взаємодіяти.

Геометрія рахується в одному місці — `layout()`. Ним користується і
малювання, і перевірка влучань: якщо кнопка намальована в одному місці,
а натискається в іншому, помилки не видно на екрані розробника, вона
виявляється пальцем на стійці.
"""

from __future__ import annotations

from dataclasses import dataclass

import pygame

from ..banners import Banner
from .theme import PALETTE

#: Частки висоти екрана.
STRIP_H = 0.20
BUTTONS_H = 0.13
GAP = 0.015
SIDE = 0.04

#: У скільки разів поверхня обличчя вища за смужку. Обличчя малюється
#: цілим, а показується лише верх — тому ROBI визирає з-за краю, а не
#: виглядає обрізаним посередині.
FACE_OVERSHOOT = 1.62

#: Скільки один банер тримається на екрані.
SLIDE_S = 7.0
#: Скільки триває перехід між банерами.
FADE_S = 0.6


@dataclass(frozen=True, slots=True)
class Layout:
    strip: pygame.Rect
    carousel: pygame.Rect
    buttons: pygame.Rect


class Showcase:
    def __init__(self, size: tuple[int, int]) -> None:
        self.size = size
        self._images: dict[int, pygame.Surface] = {}
        self._index = 0
        self._elapsed = 0.0
        self._fonts: tuple[pygame.font.Font, ...] | None = None

    def resize(self, size: tuple[int, int]) -> None:
        self.size = size
        self._images.clear()
        self._fonts = None

    def _build_fonts(self) -> None:
        """Шрифти готуються при першому малюванні, а не в конструкторі.

        Так режим лишається конструйованим без ініціалізованого pygame —
        а це дозволяє перевіряти поведінку маскота без графіки взагалі.
        Геометрія й влучання шрифтів не потребують.
        """
        if self._fonts is not None:
            return
        h = self.size[1]
        self._fonts = (
            pygame.font.Font(None, max(22, int(h * 0.055))),
            pygame.font.Font(None, max(16, int(h * 0.034))),
            pygame.font.Font(None, max(18, int(h * 0.040))),
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

    # -- геометрія ---------------------------------------------------------

    def layout(self) -> Layout:
        w, h = self.size
        side = int(w * SIDE)
        gap = int(h * GAP)
        strip_h = int(h * STRIP_H)
        buttons_h = int(h * BUTTONS_H)

        strip = pygame.Rect(0, 0, w, strip_h)
        buttons = pygame.Rect(side, h - buttons_h - gap, w - side * 2, buttons_h)
        carousel = pygame.Rect(
            side, strip_h + gap, w - side * 2, buttons.top - strip_h - gap * 2
        )
        return Layout(strip=strip, carousel=carousel, buttons=buttons)

    def button_rects(self, count: int) -> list[pygame.Rect]:
        if count <= 0:
            return []
        row = self.layout().buttons
        gap = int(self.size[0] * 0.012)
        width = (row.width - gap * (count - 1)) // count
        return [
            pygame.Rect(row.left + i * (width + gap), row.top, width, row.height)
            for i in range(count)
        ]

    # -- влучання ----------------------------------------------------------

    def hit_strip(self, x: float, y: float) -> bool:
        """Чи почався жест на смужці ROBI — саме за неї його й тягнуть."""
        return self.layout().strip.collidepoint(
            int(x * self.size[0]), int(y * self.size[1])
        )

    def hit_button(self, x: float, y: float, count: int) -> int | None:
        point = (int(x * self.size[0]), int(y * self.size[1]))
        for index, rect in enumerate(self.button_rects(count)):
            if rect.collidepoint(point):
                return index
        return None

    # -- карусель ----------------------------------------------------------

    def update(self, dt: float, count: int) -> None:
        if count <= 1:
            self._index = 0
            self._elapsed = 0.0
            return
        self._elapsed += dt
        if self._elapsed >= SLIDE_S:
            self._elapsed = 0.0
            self._index = (self._index + 1) % count

    @property
    def index(self) -> int:
        return self._index

    def _alpha(self) -> int:
        """Плавна поява замість різкої зміни: смикання ловить око збоку."""
        if self._elapsed >= FADE_S:
            return 255
        return max(0, min(255, int(255 * self._elapsed / FADE_S)))

    # -- малювання ---------------------------------------------------------

    def draw(
        self,
        target: pygame.Surface,
        face: pygame.Surface,
        banners: list[Banner],
        labels: list[str],
        image_for,
    ) -> None:
        target.fill(PALETTE.face_edge)
        box = self.layout()

        # Смужка: обличчя малюється цілим, а показується лише верх.
        target.blit(face, (0, 0), pygame.Rect(0, 0, box.strip.width, box.strip.height))

        self._draw_carousel(target, box.carousel, banners, image_for)
        self._draw_buttons(target, labels)

    def _draw_carousel(self, target, rect, banners: list[Banner], image_for) -> None:
        pygame.draw.rect(target, PALETTE.qr_paper, rect, border_radius=int(rect.height * 0.06))
        if not banners:
            # Порожня вітрина — не аварія: банерів для стійки може не бути.
            label = self.font_caption.render("", True, PALETTE.hud_muted)
            target.blit(label, label.get_rect(center=rect.center))
            return

        banner = banners[self._index % len(banners)]
        surface = self._image(banner, rect, image_for)
        if surface is not None:
            surface.set_alpha(self._alpha())
            target.blit(surface, surface.get_rect(center=rect.center))

        # Підпис поверх нижньої частини: заголовок має читатися і на
        # світлій, і на темній картинці, тому під ним лежить підкладка.
        caption_h = int(rect.height * 0.24)
        caption = pygame.Rect(rect.left, rect.bottom - caption_h, rect.width, caption_h)
        veil = pygame.Surface(caption.size, pygame.SRCALPHA)
        veil.fill((*PALETTE.pupil, 150))
        target.blit(veil, caption.topleft)

        title = self.font_title.render(banner.title, True, PALETTE.qr_paper)
        target.blit(title, (caption.left + int(rect.width * 0.03), caption.top + int(caption_h * 0.12)))
        if banner.description:
            text = self.font_caption.render(banner.description, True, PALETTE.qr_paper)
            target.blit(text, (caption.left + int(rect.width * 0.03), caption.top + int(caption_h * 0.58)))

    def _image(self, banner: Banner, rect: pygame.Rect, image_for):
        cached = self._images.get(banner.id)
        if cached is not None:
            return cached
        raw = image_for(banner)
        if raw is None:
            return None
        scale = min(rect.width / raw.get_width(), rect.height / raw.get_height())
        size = (max(1, int(raw.get_width() * scale)), max(1, int(raw.get_height() * scale)))
        scaled = pygame.transform.smoothscale(raw, size)
        self._images[banner.id] = scaled
        return scaled

    def _draw_buttons(self, target: pygame.Surface, labels: list[str]) -> None:
        for label, rect in zip(labels, self.button_rects(len(labels))):
            pygame.draw.rect(
                target, PALETTE.qr_paper, rect, border_radius=int(rect.height * 0.34)
            )
            text = self.font_button.render(label, True, PALETTE.hud)
            target.blit(text, text.get_rect(center=rect.center))

    # -- допоміжне ---------------------------------------------------------

    def face_size(self) -> tuple[int, int]:
        """Розмір поверхні для обличчя у смужці.

        Вища за смужку, щоб у видимій частині опинилися саме очі, а не
        маківка: обличчя не масштабується, воно підрізається.
        """
        w, h = self.size
        return (w, max(2, int(h * STRIP_H * FACE_OVERSHOOT)))
