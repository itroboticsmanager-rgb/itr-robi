"""Reusable, cached drawing primitives for the product UI."""

from __future__ import annotations

from functools import lru_cache

import pygame

from .theme import Color, PALETTE


def clamp01(value: float) -> float:
    return max(0.0, min(1.0, value))


def ease_out_quart(value: float) -> float:
    t = clamp01(value)
    return 1.0 - (1.0 - t) ** 4


@lru_cache(maxsize=192)
def _panel_surface(
    width: int,
    height: int,
    fill: Color,
    radius: int,
    border: Color | None,
    shadow: bool,
) -> tuple[pygame.Surface, int]:
    pad = max(4, min(18, int(min(width, height) * 0.09))) if shadow else 1
    surface = pygame.Surface((width + pad * 2, height + pad * 2), pygame.SRCALPHA)
    rect = pygame.Rect(pad, pad, width, height)
    radius = max(2, min(radius, min(width, height) // 2))
    if shadow:
        for offset, alpha in ((pad // 3, 22), (pad * 2 // 3, 12), (pad, 5)):
            shadow_rect = rect.move(0, offset)
            pygame.draw.rect(
                surface,
                (*PALETTE.shadow, alpha),
                shadow_rect,
                border_radius=radius,
            )
    pygame.draw.rect(surface, fill, rect, border_radius=radius)
    if border is not None:
        pygame.draw.rect(surface, border, rect, width=1, border_radius=radius)
    return surface, pad


def draw_panel(
    target: pygame.Surface,
    rect: pygame.Rect,
    *,
    fill: Color | None = None,
    radius: int | None = None,
    border: Color | None = None,
    shadow: bool = True,
) -> None:
    """Draw a soft elevated surface without allocating in the frame loop."""
    fill = fill or PALETTE.surface
    radius = radius if radius is not None else max(12, int(rect.height * 0.12))
    panel, pad = _panel_surface(rect.width, rect.height, fill, radius, border, shadow)
    target.blit(panel, (rect.left - pad, rect.top - pad))


def draw_page_dots(
    target: pygame.Surface,
    center: tuple[int, int],
    count: int,
    active: int,
    *,
    radius: int,
) -> None:
    if count <= 1:
        return
    gap = radius * 3
    width = (count - 1) * gap
    start_x = center[0] - width // 2
    for index in range(count):
        color = PALETTE.primary if index == active else PALETTE.dot_muted
        dot_r = radius if index == active else max(2, radius - 1)
        pygame.draw.circle(target, color, (start_x + index * gap, center[1]), dot_r)

