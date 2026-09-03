"""Екран контент-меню: список і картка (D-048).

Геометрія рахується в одному місці — `item_rects` і `back_rect`. Ними
користується і малювання, і перевірка влучань. Це не економія коду: якщо
кнопка намальована в одному місці, а натискається в іншому, помилка не
видно на екрані розробника й виявляється вже на стійці.

Прокрутки немає навмисно. `MAX_ITEMS` у `content` обмежує меню вісьмома
пунктами, які вміщаються цілком: список, який доводиться гортати, вже не
є меню, а розмір пункту важливіший за їхню кількість, коли натискають
пальцем, а не мишею.
"""

from __future__ import annotations

import pygame

from .theme import PALETTE

#: Частки екрана. Смуга заголовка згори, під нею — пункти.
HEADER_H = 0.16
SIDE = 0.06
GAP = 0.018
BACK_W = 0.14


class MenuScreen:
    def __init__(self, size: tuple[int, int]) -> None:
        self.size = size
        self._build_fonts()

    def resize(self, size: tuple[int, int]) -> None:
        self.size = size
        self._build_fonts()

    def _build_fonts(self) -> None:
        h = self.size[1]
        self.font_title = pygame.font.Font(None, max(24, int(h * 0.075)))
        self.font_item = pygame.font.Font(None, max(20, int(h * 0.055)))
        self.font_body = pygame.font.Font(None, max(16, int(h * 0.040)))
        self.font_price = pygame.font.Font(None, max(18, int(h * 0.052)))

    # -- геометрія ---------------------------------------------------------

    def back_rect(self) -> pygame.Rect:
        w, h = self.size
        side = int(w * SIDE)
        top = int(h * 0.035)
        return pygame.Rect(side, top, int(w * BACK_W), int(h * HEADER_H * 0.55))

    def item_rects(self, count: int) -> list[pygame.Rect]:
        if count <= 0:
            return []
        w, h = self.size
        side = int(w * SIDE)
        gap = int(h * GAP)
        top = int(h * HEADER_H)
        usable = h - top - int(h * 0.05)
        row = (usable - gap * (count - 1)) // count
        return [
            pygame.Rect(side, top + i * (row + gap), w - side * 2, row)
            for i in range(count)
        ]

    # -- влучання ----------------------------------------------------------

    def hit_back(self, x: float, y: float) -> bool:
        """`x`/`y` нормалізовані 0..1, як їх віддає `Touch`."""
        return self.back_rect().collidepoint(int(x * self.size[0]), int(y * self.size[1]))

    def hit_item(self, x: float, y: float, count: int) -> int | None:
        point = (int(x * self.size[0]), int(y * self.size[1]))
        for index, rect in enumerate(self.item_rects(count)):
            if rect.collidepoint(point):
                return index
        return None

    # -- малювання ---------------------------------------------------------

    def _chrome(self, target: pygame.Surface, title: str, show_back: bool) -> None:
        target.fill(PALETTE.face_top)
        if show_back:
            back = self.back_rect()
            pygame.draw.rect(target, PALETTE.qr_paper, back, border_radius=back.height // 3)
            label = self.font_item.render("‹", True, PALETTE.hud)
            target.blit(label, label.get_rect(center=back.center))

        heading = self.font_title.render(title, True, PALETTE.hud)
        w, _ = self.size
        target.blit(heading, heading.get_rect(midtop=(w // 2, int(self.size[1] * 0.04))))

    def draw_menu(self, target: pygame.Surface, title: str, labels: list[str], show_back: bool) -> None:
        self._chrome(target, title, show_back)
        for label, rect in zip(labels, self.item_rects(len(labels))):
            pygame.draw.rect(target, PALETTE.qr_paper, rect, border_radius=int(rect.height * 0.28))
            text = self.font_item.render(label, True, PALETTE.hud)
            target.blit(text, text.get_rect(midleft=(rect.left + int(rect.width * 0.05), rect.centery)))

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
        card = pygame.Rect(side, top, w - side * 2, h - top - int(h * 0.05))
        pygame.draw.rect(target, PALETTE.qr_paper, card, border_radius=int(h * 0.03))

        inner = card.inflate(-int(w * 0.05), -int(h * 0.06))
        cursor = inner.top

        # Відсутня картинка — не порожній екран, а картка без картинки
        # (D-048 вимагає fallback). Текст просто піднімається вище.
        if image is not None:
            scaled = self._fit(image, inner.width, int(inner.height * 0.45))
            target.blit(scaled, (inner.centerx - scaled.get_width() // 2, cursor))
            cursor += scaled.get_height() + int(h * 0.03)

        if price:
            label = self.font_price.render(price, True, PALETTE.face_edge)
            target.blit(label, (inner.left, cursor))
            cursor += label.get_height() + int(h * 0.02)

        for line in self._wrap(body, inner.width):
            if cursor + self.font_body.get_height() > inner.bottom:
                break
            target.blit(self.font_body.render(line, True, PALETTE.hud_muted), (inner.left, cursor))
            cursor += int(self.font_body.get_height() * 1.25)

    # -- допоміжне ---------------------------------------------------------

    @staticmethod
    def _fit(image: pygame.Surface, max_w: int, max_h: int) -> pygame.Surface:
        scale = min(max_w / image.get_width(), max_h / image.get_height(), 1.0)
        size = (max(1, int(image.get_width() * scale)), max(1, int(image.get_height() * scale)))
        return pygame.transform.smoothscale(image, size)

    def _wrap(self, text: str, width: int) -> list[str]:
        if not text:
            return []
        lines: list[str] = []
        current = ""
        for word in text.split():
            probe = f"{current} {word}".strip()
            if self.font_body.size(probe)[0] <= width or not current:
                current = probe
            else:
                lines.append(current)
                current = word
        if current:
            lines.append(current)
        return lines
