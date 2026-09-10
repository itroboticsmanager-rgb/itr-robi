"""A small coherent icon set drawn with cached pygame primitives.

The renderer accepts semantic keys from content and always falls back safely.
Icons are supersampled once, then reused as ordinary surfaces in the frame loop.
"""

from __future__ import annotations

from functools import lru_cache

import pygame

from .theme import Color, PALETTE
from .typography import ui_font

ICON_NAMES = frozenset({
    "courses", "events", "clubs", "store", "gallery", "video",
    "payment", "form", "contacts", "help", "generic",
})


def resolve_icon(name: str = "", *, key: str = "", label: str = "") -> str:
    explicit = name.strip().lower()
    if explicit in ICON_NAMES:
        return explicit
    probe = f"{key} {label}".casefold()
    aliases = (
        (("course", "курс", "навчан"), "courses"),
        (("event", "поді", "календар"), "events"),
        (("club", "гурт", "group", "груп"), "clubs"),
        (("product", "store", "shop", "товар", "магаз"), "store"),
        (("gallery", "photo", "галере", "фото"), "gallery"),
        (("video", "відео"), "video"),
        (("payment", "pay", "оплат", "цін"), "payment"),
        (("form", "survey", "анкет", "заяв"), "form"),
        (("contact", "контакт"), "contacts"),
        (("help", "support", "допом"), "help"),
    )
    for needles, result in aliases:
        if any(needle in probe for needle in needles):
            return result
    return "generic"


def _rect(values: tuple[float, float, float, float], size: int) -> pygame.Rect:
    return pygame.Rect(*(int(v * size) for v in values))


@lru_cache(maxsize=96)
def render_icon(
    name: str,
    size: int,
    color: Color | None = None,
    accent: Color | None = None,
) -> pygame.Surface:
    name = resolve_icon(name)
    color = color or PALETTE.primary
    accent = accent or PALETTE.accent_yellow
    size = max(18, int(size))
    scale = 3
    big = size * scale
    surf = pygame.Surface((big, big), pygame.SRCALPHA)
    c = color
    a = accent
    width = max(4, int(big * 0.075))

    def pt(x: float, y: float) -> tuple[int, int]:
        return int(x * big), int(y * big)

    def rr(values, radius=0.12, fill=c, line=0):
        rect = _rect(values, big)
        pygame.draw.rect(surf, fill, rect, width=line, border_radius=int(big * radius))
        return rect

    if name == "courses":
        pygame.draw.polygon(surf, c, [pt(.12, .40), pt(.50, .19), pt(.88, .40), pt(.50, .61)])
        pygame.draw.polygon(surf, PALETTE.primary_soft, [pt(.26, .49), pt(.50, .63), pt(.74, .49), pt(.72, .70), pt(.50, .80), pt(.28, .70)])
        pygame.draw.line(surf, a, pt(.84, .42), pt(.84, .72), width)
        pygame.draw.circle(surf, a, pt(.84, .78), max(3, width))
    elif name == "events":
        rr((.18, .24, .64, .59), fill=PALETTE.primary_soft)
        rr((.18, .24, .64, .20), fill=c)
        for x in (.34, .66):
            pygame.draw.line(surf, PALETTE.surface, pt(x, .16), pt(x, .32), width)
        pygame.draw.circle(surf, a, pt(.66, .62), int(big * .14))
    elif name == "clubs":
        for x, y, r in ((.50, .34, .13), (.28, .43, .10), (.72, .43, .10)):
            pygame.draw.circle(surf, c, pt(x, y), int(big * r))
        rr((.33, .50, .34, .29), radius=.15, fill=c)
        rr((.12, .56, .22, .22), radius=.11, fill=PALETTE.primary_soft)
        rr((.66, .56, .22, .22), radius=.11, fill=PALETTE.primary_soft)
        pygame.draw.circle(surf, a, pt(.72, .30), int(big * .06))
    elif name == "store":
        rr((.20, .30, .60, .53), radius=.10, fill=c)
        pygame.draw.arc(surf, c, _rect((.34, .14, .32, .36), big), 0, 3.1416, width)
        robot = _rect((.36, .47, .28, .20), big)
        pygame.draw.rect(surf, PALETTE.surface, robot, border_radius=int(big * .05))
        pygame.draw.circle(surf, PALETTE.hud, pt(.44, .56), int(big * .025))
        pygame.draw.circle(surf, PALETTE.hud, pt(.56, .56), int(big * .025))
        pygame.draw.circle(surf, a, pt(.78, .70), int(big * .07))
    elif name == "gallery":
        rr((.15, .20, .70, .61), radius=.09, fill=PALETTE.primary_soft)
        pygame.draw.circle(surf, a, pt(.70, .36), int(big * .08))
        pygame.draw.polygon(surf, c, [pt(.22, .72), pt(.40, .48), pt(.53, .62), pt(.64, .51), pt(.79, .72)])
    elif name == "video":
        rr((.16, .20, .68, .61), radius=.13, fill=c)
        pygame.draw.polygon(surf, PALETTE.surface, [pt(.43, .35), pt(.43, .68), pt(.69, .515)])
        pygame.draw.circle(surf, a, pt(.78, .24), int(big * .055))
    elif name == "payment":
        rr((.14, .28, .72, .50), radius=.11, fill=c)
        rr((.24, .18, .48, .22), radius=.08, fill=PALETTE.primary_soft)
        rr((.58, .43, .34, .23), radius=.08, fill=PALETTE.surface)
        pygame.draw.circle(surf, a, pt(.69, .545), int(big * .04))
    elif name == "form":
        rr((.24, .20, .52, .65), radius=.08, fill=PALETTE.primary_soft)
        rr((.38, .13, .24, .16), radius=.07, fill=c)
        for y in (.43, .58, .73):
            pygame.draw.circle(surf, c, pt(.37, y), int(big * .025))
            pygame.draw.line(surf, c, pt(.45, y), pt(.65, y), width)
        pygame.draw.circle(surf, a, pt(.74, .73), int(big * .10))
    elif name == "contacts":
        rr((.20, .18, .60, .66), radius=.08, fill=c)
        pygame.draw.line(surf, PALETTE.primary_soft, pt(.36, .18), pt(.36, .84), width)
        pygame.draw.circle(surf, PALETTE.surface, pt(.58, .43), int(big * .10))
        rr((.45, .57, .27, .15), radius=.08, fill=PALETTE.surface)
        for y in (.32, .47, .62, .76):
            pygame.draw.line(surf, a, pt(.16, y), pt(.24, y), width)
    elif name == "help":
        rr((.15, .17, .70, .58), radius=.22, fill=c)
        pygame.draw.polygon(surf, c, [pt(.34, .70), pt(.30, .88), pt(.50, .73)])
        font = ui_font(int(big * .42), weight="bold")
        glyph = font.render("?", True, PALETTE.surface)
        surf.blit(glyph, glyph.get_rect(center=pt(.50, .47)))
        pygame.draw.circle(surf, a, pt(.77, .24), int(big * .06))
    else:
        for x, y in ((.32, .32), (.68, .32), (.32, .68), (.68, .68)):
            pygame.draw.circle(surf, c, pt(x, y), int(big * .105))
        pygame.draw.circle(surf, a, pt(.68, .32), int(big * .045))

    return pygame.transform.smoothscale(surf, (size, size))
