"""Typography helpers for the kiosk UI.

pygame's bundled default font is useful for diagnostics but looks visibly like
a prototype and has uneven Cyrillic coverage. The device already ships with
Segoe UI, so the product UI uses that local family without adding a network or
packaging dependency.
"""

from __future__ import annotations

from functools import lru_cache

import pygame


@lru_cache(maxsize=8)
def _font_path(weight: str) -> str | None:
    if weight == "bold":
        candidates = (("Segoe UI", True), ("Arial", True), ("DejaVu Sans", True))
    elif weight == "semibold":
        candidates = (
            ("Segoe UI Semibold", False),
            ("Segoe UI", True),
            ("Arial", True),
            ("DejaVu Sans", True),
        )
    else:
        candidates = (
            ("Segoe UI Variable", False),
            ("Segoe UI", False),
            ("Arial", False),
            ("DejaVu Sans", False),
        )
    for family, bold in candidates:
        path = pygame.font.match_font(family, bold=bold)
        if path:
            return path
    return None


def ui_font(size: int, *, weight: str = "regular") -> pygame.font.Font:
    """Return a fresh font object with predictable Unicode coverage."""
    if not pygame.font.get_init():
        pygame.font.init()
    path = _font_path(weight)
    return pygame.font.Font(path, max(10, int(size)))


def wrap_text(
    font: pygame.font.Font,
    text: str,
    max_width: int,
    *,
    max_lines: int | None = None,
) -> list[str]:
    """Wrap words to width, adding an ellipsis when a line cap is reached."""
    if not text:
        return []
    words = text.split()
    lines: list[str] = []
    current = ""
    for word in words:
        probe = f"{current} {word}".strip()
        if not current or font.size(probe)[0] <= max_width:
            current = probe
            continue
        lines.append(current)
        current = word
        if max_lines is not None and len(lines) >= max_lines:
            break
    if current and (max_lines is None or len(lines) < max_lines):
        lines.append(current)

    if max_lines is not None and len(lines) == max_lines:
        consumed = " ".join(lines)
        if len(consumed) < len(" ".join(words)):
            last = lines[-1]
            while last and font.size(last + "…")[0] > max_width:
                last = last[:-1].rstrip()
            lines[-1] = (last or "") + "…"
    return lines


def fit_font(
    text: str,
    max_width: int,
    preferred_size: int,
    minimum_size: int,
    *,
    weight: str = "semibold",
) -> pygame.font.Font:
    """Choose the largest font in a small bounded range that fits one line."""
    size = max(minimum_size, preferred_size)
    while size > minimum_size:
        candidate = ui_font(size, weight=weight)
        if candidate.size(text)[0] <= max_width:
            return candidate
        size -= 2
    return ui_font(minimum_size, weight=weight)
